"""Вспомогательные функции"""
import os
import json

LOCAL_DATA_FOLDER = "./data"
ALLOWED_EXTENSIONS = {"zip"}
ALLOWED_GEOJSON_EXTENSIONS = {"geojson", "json"}
ALLOWED_GPX_EXTENSIONS = {"gpx"}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def allowed_file(filename):
    """Проверяет, разрешено ли расширение файла"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_geojson_file(filename):
    """Проверяет, разрешено ли расширение файла для GeoJSON"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_GEOJSON_EXTENSIONS


def allowed_gpx_file(filename):
    """Проверяет, разрешено ли расширение файла для GPX"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_GPX_EXTENSIONS


def check_file_size(file):
    """Проверяет размер файла"""
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    return size <= MAX_FILE_SIZE


def load_index_json():
    """Загружает существующий index.json или возвращает пустой шаблон"""
    local_path = os.path.join(LOCAL_DATA_FOLDER, "index.json")
    
    if os.path.exists(local_path):
        try:
            with open(local_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
                # Проверяем, что данные являются словарем
                if not isinstance(data, dict):
                    # Если это не словарь (например, список), возвращаем пустой шаблон
                    return {"paths": {}, "points": {}}
                
                # Убеждаемся, что структура правильная
                if "paths" not in data or not isinstance(data.get("paths"), dict):
                    data["paths"] = {}
                if "points" not in data or not isinstance(data.get("points"), dict):
                    data["points"] = {}
                return data
        except (json.JSONDecodeError, IOError, TypeError, ValueError) as e:
            # Если ошибка при чтении или парсинге, возвращаем пустой шаблон
            print(f"Предупреждение: ошибка при чтении index.json: {str(e)}")
            pass
    
    # Если файла нет или ошибка чтения, возвращаем пустой шаблон
    return {"paths": {}, "points": {}}


def merge_data(existing_data, new_data):
    """Объединяет новые данные с существующими"""
    existing_data["paths"].update(new_data.get("paths", {}))
    existing_data["points"].update(new_data.get("points", {}))
    return existing_data


def save_index_json(data):
    """Сохраняет index.json в локальную папку"""
    os.makedirs(LOCAL_DATA_FOLDER, exist_ok=True)
    local_path = os.path.join(LOCAL_DATA_FOLDER, "index.json")
    
    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return local_path


def format_file_size(size_bytes):
    """Форматирует размер файла в читаемый вид"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

