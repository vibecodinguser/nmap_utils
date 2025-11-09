import logging
import os

from flask import Flask, render_template, request, jsonify
from settings import PROJECT_DIR, YANDEX_DISK_API_KEY
from tools.file_processor import process_files
from tools.yandex_disk import check_and_create_folder, download_index_json, upload_index_json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = PROJECT_DIR
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

DEFAULT_TOKEN = "your_token_here"
ERROR_MESSAGE_TOKEN = "Добавьте ваш OAuth-токен в settings.py и перезапустите приложение."


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

    try:
        # Скачиваем актуальный index.json перед обработкой
        download_index_json()
        process_files(file_paths)

        if upload_index_json():
            cleanup_files(file_paths)
            return jsonify({
                "success": True,
                "message": "Файлы обработаны и загружены на Яндекс Диск"
            })
        else:
            return jsonify({
                "error": "Ошибка загрузки файла на Яндекс Диск. Проверьте логи."
            }), 500

    except Exception as e:
        logger.error(f"Ошибка обработки: {e}", exc_info=True)
        cleanup_files(file_paths)  # Очистка при ошибке
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    os.makedirs(os.path.join(PROJECT_DIR, 'templates'), exist_ok=True)
    init_app()
    app.run(debug=True, host='0.0.0.0', port=5555)
