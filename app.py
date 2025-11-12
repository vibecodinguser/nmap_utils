"""Точка входа Flask приложения"""
import os
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from config import YANDEX_DISK_API_KEY
from modules.yandex_disk import ensure_folder_exists, download_index_json, upload_index_json
from modules.geometry_processing import process_shapefile
from modules.utils import allowed_file, check_file_size, load_index_json, merge_data, save_index_json, format_file_size

app = Flask(__name__)
UPLOAD_FOLDER = "./data/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB

# Создаём необходимые директории
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def is_token_configured():
    """Проверяет, настроен ли OAuth токен"""
    return YANDEX_DISK_API_KEY != "_your_OAuth_token_here_"


@app.route("/")
def index():
    """Главная страница"""
    return render_template("index.html", token_configured=is_token_configured())


@app.route("/upload", methods=["POST"])
def upload_files():
    """Обработка загрузки файлов"""
    if not is_token_configured():
        return jsonify({"error": "Получите OAuth-токен, вставьте его в config.py и перезапустите приложение"}), 400

    if "files" not in request.files:
        return jsonify({"error": "Файлы не найдены"}), 400

    files = request.files.getlist("files")

    if not files or files[0].filename == "":
        return jsonify({"error": "Файлы не выбраны"}), 400

    processed_files = []
    failed_files = []

    try:
        # Проверяем и создаём папку на Яндекс.Диске
        folder_path = ensure_folder_exists()

        # Скачиваем существующий index.json, если есть
        download_index_json(folder_path)

        # Загружаем существующие данные или создаём пустой шаблон
        accumulated_data = load_index_json()

        # Обрабатываем каждый файл
        for file in files:
            if not allowed_file(file.filename):
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)
                failed_files.append({
                    "name": file.filename,
                    "size": format_file_size(file_size),
                    "error": "Недопустимое расширение файла"
                })
                continue

            if not check_file_size(file):
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)
                failed_files.append({
                    "name": file.filename,
                    "size": format_file_size(file_size),
                    "error": "Файл слишком большой"
                })
                continue
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

            try:
                # Обрабатываем shapefile
                result = process_shapefile(file_path)

                # Объединяем с накопленными данными
                accumulated_data = merge_data(accumulated_data, result)

                processed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path))
                })

            except Exception as e:
                failed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)),
                    "error": str(e)
                })
            finally:
                # Удаляем временный файл
                if os.path.exists(file_path):
                    os.remove(file_path)

        # Сохраняем финальный index.json только если есть обработанные файлы или существующие данные
        if processed_files or accumulated_data.get("paths") or accumulated_data.get("points"):
            local_index_path = save_index_json(accumulated_data)

            # Загружаем финальный index.json на Яндекс.Диск
            try:
                upload_index_json(folder_path, local_index_path)
                # Удаляем локальный файл после успешной загрузки
                if os.path.exists(local_index_path):
                    os.remove(local_index_path)
            except Exception as e:
                # Если не удалось загрузить на Яндекс.Диск, всё равно возвращаем успех
                # так как файл сохранён локально
                print(f"Предупреждение: не удалось загрузить на Яндекс.Диск: {str(e)}")

        return jsonify({
            "success": True,
            "processed": processed_files,
            "failed": failed_files
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Ошибка обработки: {str(e)}\n{error_details}")
        return jsonify({"error": f"Ошибка обработки: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555, debug=True)
