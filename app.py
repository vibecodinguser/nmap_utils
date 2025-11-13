"""Точка входа Flask приложения"""
import os
import logging
from datetime import datetime
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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Создаём необходимые директории
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def is_token_configured():
    """Проверяет, настроен ли OAuth токен"""
    return YANDEX_DISK_API_KEY != "_your_OAuth_token_here_"


@app.route("/")
def index():
    """Главная страница"""
    logger.info(f"GET / - Главная страница запрошена с IP: {request.remote_addr}")
    return render_template("index.html", token_configured=is_token_configured())


@app.route("/upload", methods=["POST"])
def upload_files():
    """Обработка загрузки файлов"""
    start_time = datetime.now()
    logger.info(f"POST /upload - Начало обработки загрузки файлов с IP: {request.remote_addr}")
    
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

    logger.info(f"Получено файлов для обработки: {len(files)}")
    processed_files = []
    failed_files = []

    try:
        # Проверяем и создаём папку на Яндекс.Диске
        step_start = datetime.now()
        logger.info("Проверка/создание папки на Яндекс.Диске...")
        folder_path = ensure_folder_exists()
        step_time = (datetime.now() - step_start).total_seconds()
        logger.info(f"Папка на Яндекс.Диске: {folder_path} (заняло {step_time:.2f} сек)")

        # Скачиваем существующий index.json, если есть
        step_start = datetime.now()
        logger.info("Попытка скачать существующий index.json...")
        download_index_json(folder_path)
        step_time = (datetime.now() - step_start).total_seconds()
        logger.info(f"Скачивание index.json завершено (заняло {step_time:.2f} сек)")

        # Загружаем существующие данные или создаём пустой шаблон
        step_start = datetime.now()
        accumulated_data = load_index_json()
        step_time = (datetime.now() - step_start).total_seconds()
        logger.info(f"Загружено существующих данных: paths={len(accumulated_data.get('paths', {}))}, points={len(accumulated_data.get('points', {}))} (заняло {step_time:.3f} сек)")

        # Обрабатываем каждый файл
        for idx, file in enumerate(files, 1):
            logger.info(f"Обработка файла {idx}/{len(files)}: {file.filename}")
            
            if not allowed_file(file.filename):
                file.seek(0, os.SEEK_END)
                file_size = file.tell()
                file.seek(0)
                logger.warning(f"Файл отклонён (недопустимое расширение): {file.filename}")
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
                logger.warning(f"Файл отклонён (слишком большой): {file.filename} ({format_file_size(file_size)})")
                failed_files.append({
                    "name": file.filename,
                    "size": format_file_size(file_size),
                    "error": "Файл слишком большой"
                })
                continue
                
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)
            logger.debug(f"Файл сохранён во временную директорию: {file_path}")

            try:
                # Обрабатываем shapefile
                step_start = datetime.now()
                logger.info(f"Начало обработки shapefile: {filename}")
                result = process_shapefile(file_path)
                step_time = (datetime.now() - step_start).total_seconds()
                paths_count = len(result.get("paths", {}))
                points_count = len(result.get("points", {}))
                logger.info(f"Shapefile обработан успешно: paths={paths_count}, points={points_count} (заняло {step_time:.2f} сек)")

                # Извлекаем category_t и title из результата перед объединением
                file_category = result.pop("category_t", "")
                file_title = result.pop("title", "")
                
                # Объединяем с накопленными данными
                step_start = datetime.now()
                accumulated_data = merge_data(accumulated_data, result)
                step_time = (datetime.now() - step_start).total_seconds()
                logger.debug(f"Объединение данных завершено (заняло {step_time:.3f} сек)")
                
                processed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)),
                    "category_t": file_category,
                    "title": file_title
                })
                info_parts = []
                if file_category:
                    info_parts.append(f"category_t: {file_category}")
                if file_title:
                    info_parts.append(f"title: {file_title}")
                logger.info(f"Файл успешно обработан: {filename}" + (f" ({', '.join(info_parts)})" if info_parts else ""))

            except Exception as e:
                logger.error(f"Ошибка при обработке файла {filename}: {str(e)}", exc_info=True)
                failed_files.append({
                    "name": filename,
                    "size": format_file_size(os.path.getsize(file_path)),
                    "error": str(e)
                })
            finally:
                # Удаляем временный файл
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Временный файл удалён: {file_path}")

        # Сохраняем финальный index.json только если есть обработанные файлы или существующие данные
        if processed_files or accumulated_data.get("paths") or accumulated_data.get("points"):
            step_start = datetime.now()
            logger.info("Сохранение финального index.json...")
            local_index_path = save_index_json(accumulated_data)
            step_time = (datetime.now() - step_start).total_seconds()
            final_paths = len(accumulated_data.get("paths", {}))
            final_points = len(accumulated_data.get("points", {}))
            logger.info(f"Финальные данные сохранены: paths={final_paths}, points={final_points} (заняло {step_time:.2f} сек)")

            # Загружаем финальный index.json на Яндекс.Диск
            try:
                step_start = datetime.now()
                logger.info("Загрузка index.json на Яндекс.Диск...")
                upload_index_json(folder_path, local_index_path)
                step_time = (datetime.now() - step_start).total_seconds()
                logger.info(f"index.json успешно загружен на Яндекс.Диск (заняло {step_time:.2f} сек)")
                # Удаляем локальный файл после успешной загрузки
                if os.path.exists(local_index_path):
                    os.remove(local_index_path)
                    logger.debug("Локальный index.json удалён после успешной загрузки")
            except Exception as e:
                # Если не удалось загрузить на Яндекс.Диск, всё равно возвращаем успех
                # так как файл сохранён локально
                logger.warning(f"Не удалось загрузить на Яндекс.Диск: {str(e)}", exc_info=True)

        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Обработка завершена за {elapsed_time:.2f} сек. Успешно: {len(processed_files)}, Ошибок: {len(failed_files)}")
        
        return jsonify({
            "success": True,
            "processed": processed_files,
            "failed": failed_files
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        elapsed_time = (datetime.now() - start_time).total_seconds()
        logger.error(f"Критическая ошибка обработки за {elapsed_time:.2f} сек: {str(e)}\n{error_details}", exc_info=True)
        return jsonify({"error": f"Ошибка обработки: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5555, debug=True)
