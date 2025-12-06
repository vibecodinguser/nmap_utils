import os
import logging
import uuid
import threading
from queue import Queue
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from modules.prcs_flow import create_nmap_output_template, merge_nmap_output_template, ProcessingError
from modules.prcs_shp import process_zip
from modules.prcs_geojson import process_geojson
from modules.prcs_gpx import process_gpx
from modules.prcs_kml import process_kml
from modules.prcs_topojson import process_topojson
from modules.prcs_wkt import process_wkt
from modules.prcs_upload import download_index_json, upload_index_json, ensure_folder, get_current_day_folder_path, \
    BASE_FOLDER_PATH
from modules.prcs_async_log import create_sse_stream, process_upload_async, allowed_file as async_allowed_file, \
    process_nspd_async

app = Flask(__name__, template_folder='web/templates', static_folder='web/static')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'zip', 'geojson', 'gpx', 'kml', 'kmz', 'topojson', 'wkt'}

# Session-based log queues
log_queues = {}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        uploaded_files = request.files.getlist('files')
        uploaded_files = [f for f in uploaded_files if f.filename != '']

        if not uploaded_files:
            return render_template('index.html', error="No files selected")

        processed_files = []
        skipped_files = []
        logs = []

        class LogCollector(logging.Handler):
            def emit(self, record):
                from datetime import datetime
                logs.append({
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'level': record.levelname.lower(),
                    'message': self.format(record)
                })

        log_collector = LogCollector()
        log_collector.setLevel(logging.INFO)
        log_collector.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(log_collector)

        try:
            logger.info("Проверка наличия базовой папки в Блокноте картографа")
            try:
                ensure_folder(BASE_FOLDER_PATH)
                logger.info("✓ Базовая папка есть")

                logger.info("Проверка наличия папки для текущей даты")
                ensure_folder(get_current_day_folder_path())
                logger.info("✓ Папка для текущей даты есть")
            except ProcessingError as e:
                logger.error(f"Ошибка Яндекс.Диска: {e.message}")
                return render_template('index.html', error=f"Yandex.Disk Error: {e.message}", logs=logs)

            logger.info("Загрузка текущего файла index.json")
            try:
                current_index = download_index_json()
                if current_index is None:
                    current_index = create_nmap_output_template()
                    logger.info("Создан новый файл index.json")
                else:
                    logger.info("✓ Загружен")
            except ProcessingError as e:
                logger.error(f"Не удалось загрузить обновленный файл index.json: {e.message}")
                return render_template('index.html', error=f"Failed to retrieve index.json: {e.message}", logs=logs)

            new_data_to_merge = create_nmap_output_template()
            logger.info(f"Обработка {len(uploaded_files)} выбранных файл(ов)")

            for file in uploaded_files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    logger.info(f"✓ Обработали: {filename}")
                    temp_path = os.path.join("/tmp", filename)
                    try:
                        file.save(temp_path)
                        logger.info(f"✓ Сохранили во временную папку")

                        if filename.endswith('.zip'):
                            logger.info(f"Парсинг и конвертация Shapefile")
                            result = process_zip(temp_path)
                        elif filename.endswith('.geojson'):
                            logger.info(f"Парсинг и конвертация GeoJSON")
                            result = process_geojson(temp_path)
                        elif filename.endswith('.gpx'):
                            logger.info(f"Парсинг и конвертация GPX")
                            result = process_gpx(temp_path)
                        elif filename.endswith('.kml') or filename.endswith('.kmz'):
                            logger.info(f"Парсинг и конвертация KML/KMZ")
                            result = process_kml(temp_path)
                        elif filename.endswith('.topojson'):
                            logger.info(f"Парсинг и конвертация TopoJSON")
                            result = process_topojson(temp_path)
                        elif filename.endswith('.wkt'):
                            logger.info(f"Парсинг и конвертация WKT")
                            result = process_wkt(temp_path)

                        new_data_to_merge = merge_nmap_output_template(new_data_to_merge, result)
                        display_items = result.get('metadata', [])
                        desc_str = "; ".join(display_items) if display_items else "No description"

                        processed_files.append({"name": filename, "desc": desc_str})
                        logger.info(f"✓ {filename} сконвертирован в файл index.json")

                    except ProcessingError as e:
                        skipped_files.append({"name": filename, "reason": e.message})
                        logger.error(f"✗ {filename}: {e.message}")
                    except Exception as e:
                        skipped_files.append({"name": filename, "reason": f"Unexpected error: {str(e)}"})
                        logger.error(f"✗ {filename}: Неожиданная ошибка - {str(e)}")
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                else:
                    skipped_files.append({"name": file.filename,
                                          "reason": "Invalid file type (must be .zip, .geojson, .gpx, .kml, .kmz, .topojson, .wkt)"})
                    logger.warning(f"Пропущен {file.filename}: неверный тип файла")
            if processed_files:
                logger.info("Загрузка результатов в Блокнот картографа")
                try:
                    final_index = merge_nmap_output_template(current_index, new_data_to_merge)
                    upload_index_json(final_index)
                    logger.info("✓ Загружен")
                except ProcessingError as e:
                    logger.error(f"Ошибка сохранения: {e.message}")
                    return render_template('index.html', error=f"Failed to save results to Yandex.Disk: {e.message}",
                                           processed=processed_files, skipped=skipped_files, logs=logs)
            logger.info(f"Выбранные файлы загружены: {len(processed_files)} успешно, {len(skipped_files)} пропущено")
        finally:
            logger.removeHandler(log_collector)
        return render_template('index.html', processed=processed_files, skipped=skipped_files, logs=logs)
    return render_template('index.html')


@app.route('/stream-logs/<session_id>')
def stream_logs(session_id):
    """SSE endpoint for streaming logs in real-time"""
    return create_sse_stream(session_id, log_queues)


@app.route('/upload-async', methods=['POST'])
def upload_async():
    """Async upload endpoint that processes files and streams logs"""

    session_id = str(uuid.uuid4())
    log_queue = Queue()
    log_queues[session_id] = log_queue

    uploaded_files = request.files.getlist('files')
    uploaded_files = [f for f in uploaded_files if f.filename != '']

    # Save files to temp directory before background processing
    # File objects can't be used after request context ends
    temp_files = []
    for file in uploaded_files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            temp_path = os.path.join("/tmp", f"{session_id}_{filename}")
            file.save(temp_path)
            temp_files.append((temp_path, filename))

    # Start processing in background thread with file paths instead of file objects
    thread = threading.Thread(
        target=process_upload_async,
        args=(log_queue, session_id, temp_files)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'session_id': session_id})


@app.route('/upload-nspd-async', methods=['POST'])
def upload_nspd_async():
    """Async upload endpoint for NSPD registry number processing"""

    session_id = str(uuid.uuid4())
    log_queue = Queue()
    log_queues[session_id] = log_queue

    registry_number = request.form.get('registry_number')

    # Start processing in background thread
    thread = threading.Thread(
        target=process_nspd_async,
        args=(log_queue, session_id, registry_number)
    )
    thread.daemon = True
    thread.start()

    return jsonify({'session_id': session_id})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5555, debug=True)
