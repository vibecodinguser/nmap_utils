import os
import logging
import json
from datetime import datetime
from queue import Queue
from typing import List, Tuple, Dict, Any, Callable, Generator
from flask import Response
from modules.prcs_flow import create_nmap_output_template, merge_nmap_output_template, ProcessingError
from modules.prcs_shp import process_zip
from modules.prcs_geojson import process_geojson
from modules.prcs_gpx import process_gpx
from modules.prcs_kml import process_kml
from modules.prcs_topojson import process_topojson
from modules.prcs_wkt import process_wkt
from modules.prcs_nspd_locality import process_nspd_locality
from modules.prcs_nspd_border import process_nspd_border
from modules.prcs_upload import (
    download_index_json,
    upload_index_json,
    ensure_folder,
    get_current_day_folder_path,
    BASE_FOLDER_PATH
)

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'zip', 'geojson', 'gpx', 'kml', 'kmz', 'topojson', 'wkt'}

FILE_PROCESSORS: Dict[str, Tuple[Callable[[str], Dict[str, Any]], str]] = {
    '.zip': (process_zip, 'Shapefile'),
    '.geojson': (process_geojson, 'GeoJSON'),
    '.gpx': (process_gpx, 'GPX'),
    '.kml': (process_kml, 'KML/KMZ'),
    '.kmz': (process_kml, 'KML/KMZ'),
    '.topojson': (process_topojson, 'TopoJSON'),
    '.wkt': (process_wkt, 'WKT'),
}


class QueueHandler(logging.Handler):

    def __init__(self, log_queue: Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record: logging.LogRecord) -> None:
        log_entry = {
            'time': datetime.now().strftime('%H:%M:%S'),
            'level': record.levelname.lower(),
            'message': self.format(record)
        }
        self.log_queue.put(log_entry)


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_file_extension(filename: str) -> str:
    return '.' + filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


def _setup_logging(log_queue: Queue) -> QueueHandler:
    queue_handler = QueueHandler(log_queue)
    queue_handler.setLevel(logging.INFO)
    queue_handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(queue_handler)
    return queue_handler


def _ensure_storage_folders() -> None:
    logger.info("Проверка наличия базовой папки в Блокноте картографа")
    ensure_folder(BASE_FOLDER_PATH)
    logger.info("✓ Базовая папка есть")

    logger.info("Проверка наличия папки для текущей даты")
    ensure_folder(get_current_day_folder_path())
    logger.info("✓ Папка для текущей даты есть")


def _load_current_index() -> Dict[str, Any]:
    logger.info("Загрузка текущего файла index.json")
    current_index = download_index_json()

    if current_index is None:
        current_index = create_nmap_output_template()
        logger.info("Создан новый файл index.json")
    else:
        logger.info("✓ Загружен")

    return current_index


def _process_single_file(temp_path: str, filename: str) -> Dict[str, Any]:
    extension = _get_file_extension(filename)

    if extension not in FILE_PROCESSORS:
        raise ValueError(f"Неподдерживаемый тип файла: {extension}")

    processor, format_name = FILE_PROCESSORS[extension]
    logger.info(f"Парсинг и конвертация {format_name}")

    return processor(temp_path)


def process_upload_async(log_queue: Queue, session_id: str, temp_files: List[Tuple[str, str]]) -> None:
    queue_handler = _setup_logging(log_queue)

    try:
        if not temp_files:
            logger.error("Не выбраны файлы для загрузки")
            return

        try:
            _ensure_storage_folders()
        except ProcessingError as e:
            logger.error(f"Добавьте свой OAuth-токен Яндекс.Диска в config.py")
            return

        try:
            current_index = _load_current_index()
        except ProcessingError as e:
            logger.error(f"Не удалось загрузить файл index.json: {e.message}")
            return

        new_data = create_nmap_output_template()
        logger.info(f"Обработка {len(temp_files)} файл(ов)")

        processed_count = 0
        skipped_count = 0

        for temp_path, filename in temp_files:
            logger.info(f"📄 Обработка: {filename}")

            try:
                result = _process_single_file(temp_path, filename)
                new_data = merge_nmap_output_template(new_data, result)
                logger.info(f"✓ {filename} сконвертирован в index.json")
                processed_count += 1

            except ProcessingError as e:
                logger.error(f"✗ {filename}: {e.message}")
                skipped_count += 1
            except ValueError as e:
                logger.error(f"✗ {filename}: {str(e)}")
                skipped_count += 1
            except Exception as e:
                logger.error(f"✗ {filename}: Неожиданная ошибка - {str(e)}")
                skipped_count += 1
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        if processed_count > 0:
            logger.info("Загрузка результатов в Блокнот картографа")
            try:
                final_index = merge_nmap_output_template(current_index, new_data)
                upload_index_json(final_index)
                logger.info("✓ Загружен")
            except ProcessingError as e:
                logger.error(f"Ошибка сохранения: {e.message}")

        logger.info(f"Завершено: {processed_count} успешно, {skipped_count} пропущено")

    finally:
        logger.removeHandler(queue_handler)
        log_queue.put(None)


def create_sse_stream(session_id: str, log_queues: Dict[str, Queue]) -> Response:
    def generate() -> Generator[str, None, None]:
        if session_id not in log_queues:
            return

        log_queue = log_queues[session_id]

        while True:
            log_entry = log_queue.get()

            if log_entry is None:
                if session_id in log_queues:
                    del log_queues[session_id]
                break

            yield f"data: {json.dumps(log_entry)}\n\n"

    return Response(generate(), mimetype='text/event-stream')

def process_nspd_async(log_queue: Queue, session_id: str, registry_number: str) -> None:
    queue_handler = _setup_logging(log_queue)

    try:
        if not registry_number:
            logger.error("Не указан реестровый номер")
            return

        try:
            _ensure_storage_folders()
        except ProcessingError as e:
            logger.error(f"Добавьте свой OAuth-токен Яндекс.Диска в config.py")
            return

        try:
            current_index = _load_current_index()
        except ProcessingError as e:
            logger.error(f"Не удалось загрузить файл index.json: {e.message}")
            return

        new_data = create_nmap_output_template()
        logger.info(f"Обработка реестрового номера: {registry_number}")

        try:
            result = process_nspd_locality(registry_number)
            new_data = merge_nmap_output_template(new_data, result)
            logger.info(f"✓ Данные для {registry_number} получены и сконвертированы")
            
            logger.info("Загрузка результатов в Блокнот картографа")
            try:
                final_index = merge_nmap_output_template(current_index, new_data)
                upload_index_json(final_index)
                logger.info("✓ Загружен")
            except ProcessingError as e:
                logger.error(f"Ошибка сохранения: {e.message}")

        except ProcessingError as e:
            logger.error(f"✗ Ошибка: {e.message}")
        except Exception as e:
            logger.error(f"✗ Неожиданная ошибка: {str(e)}")

    finally:
        logger.removeHandler(queue_handler)
        log_queue.put(None)


def process_nspd_border_async(log_queue: Queue, session_id: str, registry_number: str) -> None:
    queue_handler = _setup_logging(log_queue)

    try:
        if not registry_number:
            logger.error("Не указан реестровый номер")
            return

        try:
            _ensure_storage_folders()
        except ProcessingError as e:
            logger.error(f"Добавьте свой OAuth-токен Яндекс.Диска в config.py")
            return

        try:
            current_index = _load_current_index()
        except ProcessingError as e:
            logger.error(f"Не удалось загрузить файл index.json: {e.message}")
            return

        new_data = create_nmap_output_template()
        logger.info(f"Обработка муниципального образования: {registry_number}")

        try:
            result = process_nspd_border(registry_number)
            new_data = merge_nmap_output_template(new_data, result)
            logger.info(f"✓ Данные МО для {registry_number} получены и сконвертированы")
            
            logger.info("Загрузка результатов в Блокнот картографа")
            try:
                final_index = merge_nmap_output_template(current_index, new_data)
                upload_index_json(final_index)
                logger.info("✓ Загружен")
            except ProcessingError as e:
                logger.error(f"Ошибка сохранения: {e.message}")

        except ProcessingError as e:
            logger.error(f"✗ Ошибка: {e.message}")
        except Exception as e:
            logger.error(f"✗ Неожиданная ошибка: {str(e)}")

    finally:
        logger.removeHandler(queue_handler)
        log_queue.put(None)
