import os
from datetime import datetime

# Яндекс Диск
YANDEX_DISK_API_KEY = "your_token_here"
YANDEX_DISK_API_URL = "https://cloud-api.yandex.net/v1/disk"
BASE_FOLDER_PATH = "Приложения/Блокнот картографа Народной карты"
DATE_FORMAT = "%Y-%m-%d"

def get_target_folder_path():
    """Возвращает полный путь к папке с текущей датой"""
    date_str = datetime.now().strftime(DATE_FORMAT)
    return f"{BASE_FOLDER_PATH}/{date_str}"

# Локальные файлы
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_JSON_PATH = os.path.join(PROJECT_DIR, "index.json")

# Структура выходного JSON
OUTPUT_TEMPLATE = {
    "paths": {},
    "points": {}
}

