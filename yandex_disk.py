import logging
import os
from datetime import datetime

import requests

from settings import YANDEX_DISK_API_KEY, BASE_FOLDER_PATH, INDEX_JSON_PATH

HEADERS = {"Authorization": f"OAuth {YANDEX_DISK_API_KEY}"}
logger = logging.getLogger(__name__)

def get_target_folder_path():
    """Возвращает полный путь к папке с текущей датой"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    return f"{BASE_FOLDER_PATH}/{date_str}"

def check_and_create_folder():
    """Проверяет существование папки, создает если нет"""
    folder_path = get_target_folder_path()
    url = f"https://cloud-api.yandex.net/v1/disk/resources"
    params = {"path": folder_path}
    
    response = requests.get(url, headers=HEADERS, params=params)
    
    if response.status_code == 404:
        params = {"path": folder_path}
        response = requests.put(f"https://cloud-api.yandex.net/v1/disk/resources", headers=HEADERS, params=params)
        if response.status_code not in [201, 409]:
            raise Exception(f"Ошибка создания папки: {response.text}")
    
    return folder_path

def download_index_json():
    """Скачивает index.json если существует"""
    folder_path = get_target_folder_path()
    file_path = f"{folder_path}/index.json"
    url = f"https://cloud-api.yandex.net/v1/disk/resources/download"
    params = {"path": file_path}
    
    response = requests.get(url, headers=HEADERS, params=params)
    
    if response.status_code == 200:
        download_url = response.json().get("href")
        file_response = requests.get(download_url)
        if file_response.status_code == 200:
            with open(INDEX_JSON_PATH, "wb") as f:
                f.write(file_response.content)
            return True
    
    return False

def upload_index_json():
    """Загружает index.json на Яндекс Диск"""
    if not os.path.exists(INDEX_JSON_PATH):
        logger.error(f"Файл {INDEX_JSON_PATH} не существует")
        return False
    
    file_size = os.path.getsize(INDEX_JSON_PATH)
    print(f"Размер файла: {file_size} байт")
    
    folder_path = get_target_folder_path()
    file_path = f"{folder_path}/index.json"
    
    url = f"https://cloud-api.yandex.net/v1/disk/resources/upload"
    params = {"path": file_path, "overwrite": "true"}
    
    response = requests.get(url, headers=HEADERS, params=params)
    
    if response.status_code != 200:
        logger.error(f"Ошибка получения URL для загрузки: {response.status_code} - {response.text}")
        return False
    
    upload_url = response.json().get("href")
    if not upload_url:
        logger.error("Не получен URL для загрузки")
        return False
    
    with open(INDEX_JSON_PATH, "rb") as f:
        upload_response = requests.put(upload_url, data=f.read())
    
    if upload_response.status_code == 201:
        os.remove(INDEX_JSON_PATH)
        logger.info("Файл успешно загружен на Яндекс Диск")
        return True
    else:
        logger.error(f"Ошибка загрузки файла: {upload_response.status_code} - {upload_response.text}")
        return False

