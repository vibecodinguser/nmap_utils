"""Точка входа Flask приложения"""
import os
import json
import uuid
import threading
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from werkzeug.utils import secure_filename
from config import YANDEX_DISK_API_KEY
from modules.yandex_disk import ensure_folder_exists, download_index_json, upload_index_json
from modules.shapefile_processing import process_shapefile
from modules.geojson_processing import process_geojson
from modules.gpx_processing import process_gpx
from modules.utils import allowed_file, allowed_geojson_file, allowed_gpx_file, check_file_size, load_index_json, merge_data, save_index_json, format_file_size

app = Flask(__name__)
UPLOAD_FOLDER = "./data/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Создаём необходимые директории
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Хранилище для прогресса обработки по session_id
processing_sessions = {}
session_lock = threading.Lock()


def is_token_configured():
    """Проверяет, настроен ли OAuth токен"""
    return YANDEX_DISK_API_KEY != "_your_OAuth_token_here_"


def send_sse_event(event_type, data):
    """Форматирует событие SSE"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def update_progress(session_id, progress_data):
    """Обновляет прогресс обработки для сессии"""
    with session_lock:
        if session_id in processing_sessions:
            processing_sessions[session_id].update(progress_data)


@app.route("/")
def index():
    """Главная страница"""
    return render_template("index.html", token_configured=is_token_configured())


def process_files_thread(session_id, files_data):
    """Обрабатывает файлы в отдельном потоке с отслеживанием прогресса"""
    start_time = datetime.now()
    processed_files = []
    failed_files = []
    # 3 этапа до обработки файлов + обработка каждого файла + 2 этапа после обработки
    total_steps = 3 + len(files_data) + 2
    current_step = 0
    
    try:
        with session_lock:
            processing_sessions[session_id] = {
                "status": "processing",
                "total": total_steps,
                "current": 0,
                "percentage": 0,
                "current_stage": "Инициализация...",
                "file_progress": {},
                "processed": [],
                "failed": [],
                "error": None
            }
        
        # Этап 1: Проверка/создание папки на Яндекс.Диске
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Проверка/создание папки на Яндекс.Диске..."
        })
        folder_path = ensure_folder_exists()

        # Этап 2: Скачивание существующего index.json
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Скачивание существующего index.json..."
        })
        download_index_json(folder_path)

        # Этап 3: Загрузка существующих данных
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Загрузка существующих данных..."
        })
        accumulated_data = load_index_json()

        # Этап 4: Обработка каждого файла
        for idx, file_info in enumerate(files_data, 1):
            filename = file_info["filename"]
            file_path = file_info["file_path"]
            
            current_step += 1
            
            with session_lock:
                current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                current_file_progress[filename] = {"status": "processing", "progress": 0}
            
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": f"Обработка файла {idx}/{len(files_data)}: {filename}",
                "file_progress": current_file_progress
            })

            try:
                # Обрабатываем shapefile
                result = process_shapefile(file_path)
                
                # Извлекаем category_t и title из результата перед объединением
                file_category = result.pop("category_t", "")
                file_title = result.pop("title", "")
                
                # Объединяем с накопленными данными
                accumulated_data = merge_data(accumulated_data, result)
                
                processed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)),
                    "category_t": file_category,
                    "title": file_title
                })
                
                with session_lock:
                    current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                    current_file_progress[filename] = {"status": "completed", "progress": 100}
                
                update_progress(session_id, {
                    "file_progress": current_file_progress
                })
                

            except Exception as e:
                logger.error(f"Ошибка при обработке файла {filename}: {str(e)}", exc_info=True)
                failed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)) if os.path.exists(file_path) else "0 B",
                    "error": str(e)
                })
                with session_lock:
                    current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                    current_file_progress[filename] = {"status": "failed", "progress": 0, "error": str(e)}
                
                update_progress(session_id, {
                    "file_progress": current_file_progress
                })
            finally:
                # Удаляем временный файл
                if os.path.exists(file_path):
                    os.remove(file_path)

        # Этап 5: Сохранение финального index.json
        if processed_files or accumulated_data.get("paths") or accumulated_data.get("points"):
            current_step += 1
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": "Сохранение финального index.json..."
            })
            local_index_path = save_index_json(accumulated_data)

            # Этап 6: Загрузка на Яндекс.Диск
            current_step += 1
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": "Загрузка index.json на Яндекс.Диск..."
            })
            try:
                upload_index_json(folder_path, local_index_path)
                # Удаляем локальный файл после успешной загрузки
                if os.path.exists(local_index_path):
                    os.remove(local_index_path)
            except Exception as e:
                logger.warning(f"Не удалось загрузить на Яндекс.Диск: {str(e)}")

        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Обработка завершена за {elapsed_time:.2f} сек. Успешно: {len(processed_files)}, Ошибок: {len(failed_files)}")
        
        update_progress(session_id, {
            "status": "completed",
            "current": total_steps,
            "percentage": 100,
            "current_stage": "Обработка завершена",
            "processed": processed_files,
            "failed": failed_files
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"Критическая ошибка обработки: {str(e)}", exc_info=True)
        update_progress(session_id, {
            "status": "error",
            "error": str(e),
            "current_stage": f"Ошибка: {str(e)}"
        })


def process_geojson_thread(session_id, files_data):
    """Обрабатывает GeoJSON файлы в отдельном потоке с отслеживанием прогресса"""
    start_time = datetime.now()
    processed_files = []
    failed_files = []
    # 3 этапа до обработки файлов + обработка каждого файла + 2 этапа после обработки
    total_steps = 3 + len(files_data) + 2
    current_step = 0
    
    try:
        with session_lock:
            processing_sessions[session_id] = {
                "status": "processing",
                "total": total_steps,
                "current": 0,
                "percentage": 0,
                "current_stage": "Инициализация...",
                "file_progress": {},
                "processed": [],
                "failed": [],
                "error": None
            }
        
        # Этап 1: Проверка/создание папки на Яндекс.Диске
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Проверка/создание папки на Яндекс.Диске..."
        })
        folder_path = ensure_folder_exists()

        # Этап 2: Скачивание существующего index.json
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Скачивание существующего index.json..."
        })
        download_index_json(folder_path)

        # Этап 3: Загрузка существующих данных
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Загрузка существующих данных..."
        })
        accumulated_data = load_index_json()

        # Этап 4: Обработка каждого файла
        for idx, file_info in enumerate(files_data, 1):
            filename = file_info["filename"]
            file_path = file_info["file_path"]
            
            current_step += 1
            
            with session_lock:
                current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                current_file_progress[filename] = {"status": "processing", "progress": 0}
            
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": f"Обработка файла {idx}/{len(files_data)}: {filename}",
                "file_progress": current_file_progress
            })
            
            try:
                # Обрабатываем GeoJSON
                result = process_geojson(file_path)

                # Извлекаем category_t и title из результата перед объединением
                file_category = result.pop("category_t", "")
                file_title = result.pop("title", "")
                
                # Объединяем с накопленными данными
                accumulated_data = merge_data(accumulated_data, result)
                
                processed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)),
                    "category_t": file_category,
                    "title": file_title
                })
                
                with session_lock:
                    current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                    current_file_progress[filename] = {"status": "completed", "progress": 100}
                
                update_progress(session_id, {
                    "file_progress": current_file_progress
                })
                

            except Exception as e:
                logger.error(f"Ошибка при обработке файла {filename}: {str(e)}", exc_info=True)
                failed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)) if os.path.exists(file_path) else "0 B",
                    "error": str(e)
                })
                with session_lock:
                    current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                    current_file_progress[filename] = {"status": "failed", "progress": 0, "error": str(e)}
                
                update_progress(session_id, {
                    "file_progress": current_file_progress
                })
            finally:
                # Удаляем временный файл
                if os.path.exists(file_path):
                    os.remove(file_path)

        # Этап 5: Сохранение финального index.json
        if processed_files or accumulated_data.get("paths") or accumulated_data.get("points"):
            current_step += 1
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": "Сохранение финального index.json..."
            })
            local_index_path = save_index_json(accumulated_data)

            # Этап 6: Загрузка на Яндекс.Диск
            current_step += 1
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": "Загрузка index.json на Яндекс.Диск..."
            })
            try:
                upload_index_json(folder_path, local_index_path)
                # Удаляем локальный файл после успешной загрузки
                if os.path.exists(local_index_path):
                    os.remove(local_index_path)
            except Exception as e:
                logger.warning(f"Не удалось загрузить на Яндекс.Диск: {str(e)}")

        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Обработка завершена за {elapsed_time:.2f} сек. Успешно: {len(processed_files)}, Ошибок: {len(failed_files)}")
        
        update_progress(session_id, {
            "status": "completed",
            "current": total_steps,
            "percentage": 100,
            "current_stage": "Обработка завершена",
            "processed": processed_files,
            "failed": failed_files
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"Критическая ошибка обработки: {str(e)}", exc_info=True)
        update_progress(session_id, {
            "status": "error",
            "error": str(e),
            "current_stage": f"Ошибка: {str(e)}"
        })


def process_gpx_thread(session_id, files_data):
    """Обрабатывает GPX файлы в отдельном потоке с отслеживанием прогресса"""
    start_time = datetime.now()
    processed_files = []
    failed_files = []
    # 3 этапа до обработки файлов + обработка каждого файла + 2 этапа после обработки
    total_steps = 3 + len(files_data) + 2
    current_step = 0
    
    try:
        with session_lock:
            processing_sessions[session_id] = {
                "status": "processing",
                "total": total_steps,
                "current": 0,
                "percentage": 0,
                "current_stage": "Инициализация...",
                "file_progress": {},
                "processed": [],
                "failed": [],
                "error": None
            }
        
        # Этап 1: Проверка/создание папки на Яндекс.Диске
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Проверка/создание папки на Яндекс.Диске..."
        })
        folder_path = ensure_folder_exists()

        # Этап 2: Скачивание существующего index.json
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Скачивание существующего index.json..."
        })
        download_index_json(folder_path)

        # Этап 3: Загрузка существующих данных
        current_step += 1
        update_progress(session_id, {
            "current": current_step,
            "percentage": int((current_step / total_steps) * 100),
            "current_stage": "Загрузка существующих данных..."
        })
        accumulated_data = load_index_json()

        # Этап 4: Обработка каждого файла
        for idx, file_info in enumerate(files_data, 1):
            filename = file_info["filename"]
            file_path = file_info["file_path"]
            
            current_step += 1
            
            with session_lock:
                current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                current_file_progress[filename] = {"status": "processing", "progress": 0}
            
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": f"Обработка файла {idx}/{len(files_data)}: {filename}",
                "file_progress": current_file_progress
            })
            
            try:
                # Обрабатываем GPX
                result = process_gpx(file_path)

                # Извлекаем category_t и title из результата перед объединением
                file_category = result.pop("category_t", "")
                file_title = result.pop("title", "")
                
                # Объединяем с накопленными данными
                accumulated_data = merge_data(accumulated_data, result)
                
                processed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)),
                    "category_t": file_category,
                    "title": file_title
                })
                
                with session_lock:
                    current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                    current_file_progress[filename] = {"status": "completed", "progress": 100}
                
                update_progress(session_id, {
                    "file_progress": current_file_progress
                })
                

            except Exception as e:
                logger.error(f"Ошибка при обработке файла {filename}: {str(e)}", exc_info=True)
                failed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)) if os.path.exists(file_path) else "0 B",
                    "error": str(e)
                })
                with session_lock:
                    current_file_progress = processing_sessions[session_id].get("file_progress", {}).copy()
                    current_file_progress[filename] = {"status": "failed", "progress": 0, "error": str(e)}
                
                update_progress(session_id, {
                    "file_progress": current_file_progress
                })
            finally:
                # Удаляем временный файл
                if os.path.exists(file_path):
                    os.remove(file_path)

        # Этап 5: Сохранение финального index.json
        if processed_files or accumulated_data.get("paths") or accumulated_data.get("points"):
            current_step += 1
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": "Сохранение финального index.json..."
            })
            local_index_path = save_index_json(accumulated_data)

            # Этап 6: Загрузка на Яндекс.Диск
            current_step += 1
            update_progress(session_id, {
                "current": current_step,
                "percentage": int((current_step / total_steps) * 100),
                "current_stage": "Загрузка index.json на Яндекс.Диск..."
            })
            try:
                upload_index_json(folder_path, local_index_path)
                # Удаляем локальный файл после успешной загрузки
                if os.path.exists(local_index_path):
                    os.remove(local_index_path)
            except Exception as e:
                logger.warning(f"Не удалось загрузить на Яндекс.Диск: {str(e)}")

        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Обработка завершена за {elapsed_time:.2f} сек. Успешно: {len(processed_files)}, Ошибок: {len(failed_files)}")
        
        update_progress(session_id, {
            "status": "completed",
            "current": total_steps,
            "percentage": 100,
            "current_stage": "Обработка завершена",
            "processed": processed_files,
            "failed": failed_files
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"Критическая ошибка обработки: {str(e)}", exc_info=True)
        update_progress(session_id, {
            "status": "error",
            "error": str(e),
            "current_stage": f"Ошибка: {str(e)}"
        })


@app.route("/upload", methods=["POST"])
def upload_files():
    """Обработка загрузки файлов - сохраняет файлы и запускает обработку"""
    if not is_token_configured():
        return jsonify({"error": "Получите OAuth-токен, вставьте его в config.py и перезапустите приложение"}), 400

    if "files" not in request.files:
        return jsonify({"error": "Файлы не найдены"}), 400

    files = request.files.getlist("files")

    if not files or files[0].filename == "":
        return jsonify({"error": "Файлы не выбраны"}), 400
    
    # Создаём session_id
    session_id = str(uuid.uuid4())
    files_data = []
    
    # Сохраняем файлы
    for file in files:
        if not allowed_file(file.filename):
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            continue

        if not check_file_size(file):
            continue
            
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{session_id}_{filename}")
        file.save(file_path)
        files_data.append({"filename": filename, "file_path": file_path})
    
    if not files_data:
        return jsonify({"error": "Нет валидных файлов для обработки"}), 400
    
    # Запускаем обработку в отдельном потоке
    thread = threading.Thread(target=process_files_thread, args=(session_id, files_data))
    thread.daemon = True
    thread.start()
    
    return jsonify({"session_id": session_id})


@app.route("/upload-geojson", methods=["POST"])
def upload_geojson_files():
    """Обработка загрузки GeoJSON файлов - сохраняет файлы и запускает обработку"""
    logger.info(f"POST /upload-geojson - Начало загрузки GeoJSON файлов с IP: {request.remote_addr}")
    
    if not is_token_configured():
        logger.warning("Попытка загрузки без настроенного OAuth токена")
        return jsonify({"error": "Получите OAuth-токен, вставьте его в config.py и перезапустите приложение"}), 400

    if "files" not in request.files:
        logger.warning("Запрос без файлов")
        return jsonify({"error": "Файлы не найдены"}), 400

    files = request.files.getlist("files")

    if not files or files[0].filename == "":
        logger.warning("Файлы не выбраны")
        return jsonify({"error": "Файлы не выбраны"}), 400

    logger.info(f"Получено GeoJSON файлов для обработки: {len(files)}")
    
    # Создаём session_id
    session_id = str(uuid.uuid4())
    files_data = []
    
    # Сохраняем файлы
    for file in files:
        if not allowed_geojson_file(file.filename):
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            continue

        if not check_file_size(file):
            continue
            
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{session_id}_{filename}")
        file.save(file_path)
        files_data.append({"filename": filename, "file_path": file_path})
    
    if not files_data:
        return jsonify({"error": "Нет валидных GeoJSON файлов для обработки"}), 400
    
    # Запускаем обработку в отдельном потоке
    thread = threading.Thread(target=process_geojson_thread, args=(session_id, files_data))
    thread.daemon = True
    thread.start()
    
    return jsonify({"session_id": session_id})


@app.route("/upload-gpx", methods=["POST"])
def upload_gpx_files():
    """Обработка загрузки GPX файлов - сохраняет файлы и запускает обработку"""
    logger.info(f"POST /upload-gpx - Начало загрузки GPX файлов с IP: {request.remote_addr}")
    
    if not is_token_configured():
        logger.warning("Попытка загрузки без настроенного OAuth токена")
        return jsonify({"error": "Получите OAuth-токен, вставьте его в config.py и перезапустите приложение"}), 400

    if "files" not in request.files:
        logger.warning("Запрос без файлов")
        return jsonify({"error": "Файлы не найдены"}), 400

    files = request.files.getlist("files")

    if not files or files[0].filename == "":
        logger.warning("Файлы не выбраны")
        return jsonify({"error": "Файлы не выбраны"}), 400

    logger.info(f"Получено GPX файлов для обработки: {len(files)}")
    
    # Создаём session_id
    session_id = str(uuid.uuid4())
    files_data = []
    
    # Сохраняем файлы
    for file in files:
        if not allowed_gpx_file(file.filename):
            file.seek(0, os.SEEK_END)
            file_size = file.tell()
            file.seek(0)
            continue

        if not check_file_size(file):
            continue
            
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], f"{session_id}_{filename}")
        file.save(file_path)
        files_data.append({"filename": filename, "file_path": file_path})
    
    if not files_data:
        return jsonify({"error": "Нет валидных GPX файлов для обработки"}), 400
    
    # Запускаем обработку в отдельном потоке
    thread = threading.Thread(target=process_gpx_thread, args=(session_id, files_data))
    thread.daemon = True
    thread.start()
    
    return jsonify({"session_id": session_id})


@app.route("/progress/<session_id>")
def progress_stream(session_id):
    """SSE поток для отслеживания прогресса обработки"""
    def generate():
        import time
        last_sent = {}
        
        while True:
            with session_lock:
                session_data = processing_sessions.get(session_id)
            
            if session_data is None:
                # Сессия ещё не создана, ждём
                yield send_sse_event("progress", {
                    "status": "waiting",
                    "message": "Ожидание начала обработки..."
                })
                time.sleep(0.5)
                continue
            
            status = session_data.get("status")
            current_data = {
                "status": status,
                "current": session_data.get("current", 0),
                "total": session_data.get("total", 0),
                "percentage": session_data.get("percentage", 0),
                "current_stage": session_data.get("current_stage", ""),
                "file_progress": session_data.get("file_progress", {}),
                "processed": session_data.get("processed", []),
                "failed": session_data.get("failed", []),
                "error": session_data.get("error")
            }
            
            # Отправляем только если данные изменились
            data_key = json.dumps(current_data, sort_keys=True)
            if data_key != last_sent.get(session_id):
                yield send_sse_event("progress", current_data)
                last_sent[session_id] = data_key
            
            if status in ["completed", "error"]:
                # Очищаем сессию через 5 секунд после завершения
                time.sleep(5)
                with session_lock:
                    if session_id in processing_sessions:
                        del processing_sessions[session_id]
                break
            
            time.sleep(0.3)  # Обновление каждые 300мс
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555, debug=True)
