from flask import Flask, render_template, request, jsonify
import os
import logging
from yandex_disk import check_and_create_folder, download_index_json, upload_index_json
from file_processor import process_files
from settings import PROJECT_DIR

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = PROJECT_DIR
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB

def init_app():
    """Инициализация при запуске"""
    check_and_create_folder()
    download_index_json()

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert():
    """Обработка загрузки и конвертации файлов"""
    if 'files' not in request.files:
        return jsonify({"error": "Файлы не выбраны"}), 400
    
    files = request.files.getlist('files')
    if not files or files[0].filename == '':
        return jsonify({"error": "Файлы не выбраны"}), 400
    
    file_paths = []
    for file in files:
        if file.filename.endswith('.zip'):
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(file_path)
            file_paths.append(file_path)
    
    if not file_paths:
        return jsonify({"error": "Нет zip файлов"}), 400
    
    try:
        # Скачиваем актуальный index.json перед обработкой
        download_index_json()
        process_files(file_paths)
        if upload_index_json():
            # Удаляем zip-архивы после успешной загрузки
            for file_path in file_paths:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Удален архив: {file_path}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить архив {file_path}: {e}")
            return jsonify({"success": True, "message": "Файлы обработаны и загружены на Яндекс Диск"})
        else:
            return jsonify({"error": "Ошибка загрузки файла на Яндекс Диск. Проверьте логи."}), 500
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    os.makedirs(os.path.join(PROJECT_DIR, 'templates'), exist_ok=True)
    init_app()
    app.run(debug=True, host='0.0.0.0', port=5555)

