import logging
import os
import uuid
import threading

from flask import Flask, render_template, request, jsonify
from settings import PROJECT_DIR, YANDEX_DISK_API_KEY, INDEX_JSON_PATH
from tools.file_processor import process_files
from tools.yandex_disk import check_and_create_folder, download_index_json, upload_index_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = PROJECT_DIR
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

DEFAULT_TOKEN = "your_token_here"
ERROR_MESSAGE_TOKEN = "Добавьте ваш OAuth-токен в settings.py и перезапустите приложение."

# Хранилище прогресса обработки (task_id -> progress_data)
progress_store = {}
progress_lock = threading.Lock()


def is_token_configured():
    """Проверяет, настроен ли токен Яндекс Диска"""
    return YANDEX_DISK_API_KEY != DEFAULT_TOKEN


def validate_files():
    """Валидация загруженных файлов"""
    if 'files' not in request.files:
        return None, "Файлы не выбраны"

    files_list = request.files.getlist('files')
    if not files_list or not files_list[0].filename:
        return None, "Файлы не выбраны"

    return files_list, None


def save_uploaded_files(files):
    """Сохраняет загруженные zip файлы"""
    file_paths = []
    for file in files:
        if file.filename and file.filename.endswith('.zip'):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            file_paths.append(file_path)
            logger.info(f"Сохранен файл: {file.filename}")
    return file_paths


def cleanup_files(file_paths):
    """Удаляет временные файлы"""
    for file_path in file_paths:
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Удален архив: {file_path}")
        except OSError as e:
            logger.warning(f"Не удалось удалить архив {file_path}: {e}")


def init_app():
    """Инициализация при запуске"""
    if not is_token_configured():
        logger.warning("YANDEX_DISK_API_KEY не настроен. Пропуск проверки папки на Яндекс Диске.")
        return

    try:
        logger.info("Проверка наличия папки на Яндекс Диске...")
        folder_path = check_and_create_folder()
        logger.info(f"Папка на Яндекс Диске проверена/создана: {folder_path}")
        download_index_json()
    except Exception as e:
        logger.error(f"Ошибка при проверке папки на Яндекс Диске: {e}")
        raise


@app.route('/')
def index():
    """Главная страница"""
    error_message = ERROR_MESSAGE_TOKEN if not is_token_configured() else None
    return render_template('index.html', error_message=error_message)


def process_files_with_progress(task_id, file_paths):
    """Обрабатывает файлы с обновлением прогресса"""
    # Распределение прогресса: 5% - скачивание, 85% - обработка файлов, 10% - загрузка
    DOWNLOAD_START = 0
    DOWNLOAD_END = 5
    PROCESS_START = 5
    PROCESS_END = 90
    UPLOAD_START = 90
    UPLOAD_END = 100
    
    def update_progress(percentage, message):
        with progress_lock:
            progress_store[task_id] = {
                "current": percentage,
                "total": 100,
                "percentage": percentage,
                "message": message,
                "status": "processing"
            }
    
    def process_progress_callback(current, total, message):
        """Преобразует прогресс обработки файлов в общий прогресс"""
        if total == 0:
            percentage = PROCESS_END
        else:
            process_percentage = (current / total) * 100
            percentage = PROCESS_START + int((process_percentage / 100) * (PROCESS_END - PROCESS_START))
        update_progress(percentage, message)
    
    try:
        update_progress(0, "Инициализация...")
        
        # Скачиваем актуальный index.json перед обработкой
        update_progress(DOWNLOAD_START, "Скачивание index.json...")
        download_index_json()
        update_progress(DOWNLOAD_END, "Скачивание завершено")
        
        # Обрабатываем файлы (5% - 90%)
        process_files(file_paths, process_progress_callback)
        
        # Загружаем на Яндекс Диск (90% - 100%)
        update_progress(UPLOAD_START, "Загрузка на Яндекс Диск...")
        
        # Получаем размер файла index.json перед загрузкой
        file_size_mb = 0
        if os.path.exists(INDEX_JSON_PATH):
            file_size_bytes = os.path.getsize(INDEX_JSON_PATH)
            file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
        
        if upload_index_json():
            cleanup_files(file_paths)
            message = f"Геометрия {file_size_mb} mb успешно выгружена!"
            update_progress(100, message)
            with progress_lock:
                progress_store[task_id]["status"] = "completed"
        else:
            update_progress(100, "Ошибка загрузки на Яндекс Диск")
            with progress_lock:
                progress_store[task_id]["status"] = "error"
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}", exc_info=True)
        cleanup_files(file_paths)
        update_progress(100, f"Ошибка: {str(e)}")
        with progress_lock:
            progress_store[task_id]["status"] = "error"


@app.route('/convert', methods=['POST'])
def convert():
    """Обработка загрузки и конвертации файлов"""
    # Валидация файлов
    files, error = validate_files()
    if error:
        return jsonify({"error": error}), 400

    # Сохранение файлов
    file_paths = save_uploaded_files(files)
    if not file_paths:
        return jsonify({"error": "Нет zip файлов"}), 400

    # Создаем task_id для отслеживания прогресса
    task_id = str(uuid.uuid4())
    
    # Запускаем обработку в отдельном потоке
    thread = threading.Thread(
        target=process_files_with_progress,
        args=(task_id, file_paths)
    )
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "success": True,
        "task_id": task_id,
        "message": "Обработка начата"
    })


@app.route('/progress/<task_id>', methods=['GET'])
def get_progress(task_id):
    """Получение прогресса обработки"""
    with progress_lock:
        progress = progress_store.get(task_id)
        if not progress:
            return jsonify({"error": "Task not found"}), 404
        return jsonify(progress)


if __name__ == '__main__':
    os.makedirs(os.path.join(PROJECT_DIR, 'templates'), exist_ok=True)
    init_app()
    app.run(debug=True, host='0.0.0.0', port=5555)
