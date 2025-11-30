import requests
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from config import YANDEX_DISK_API_KEY
from .prcs_flow import ProcessingError, ERR_NETWORK

BASE_FOLDER_PATH = "Приложения/Блокнот картографа Народной карты"
API_BASE_URL = "https://cloud-api.yandex.net/v1/disk/resources"

# Configure logging

logger = logging.getLogger(__name__)


def get_headers() -> Dict[str, str]:
    return {
        "Authorization": f"OAuth {YANDEX_DISK_API_KEY}",
        "Content-Type": "application/json"
    }


# Проверяем наличие папки для текущей даты
def get_current_day_folder_path() -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")
    return f"{BASE_FOLDER_PATH}/{today_str}"


def ensure_folder(path: str) -> None:
    headers = get_headers()

    # Проверяем есть ли папка
    check_url = f"{API_BASE_URL}?path={path}"
    response = requests.get(check_url, headers=headers)

    if response.status_code == 200:
        logger.info(f"Folder {path} already exists.")
        return
    elif response.status_code == 404:
        create_url = f"{API_BASE_URL}?path={path}"
        create_response = requests.put(create_url, headers=headers)

        if create_response.status_code == 201:
            logger.info(f"Folder {path} created.")
        elif create_response.status_code == 409:
            logger.info(f"Folder {path} already exists (conflict).")
        else:
            raise ProcessingError(ERR_NETWORK, f"Failed to create folder {path}: {create_response.text}")
    else:
        raise ProcessingError(ERR_NETWORK, f"Failed to check folder {path}: {response.text}")


# Скачиваем index.json если он есть в базовой папке диска
def download_index_json() -> Optional[Dict[str, Any]]:
    folder_path = get_current_day_folder_path()
    file_path = f"{folder_path}/index.json"
    headers = get_headers()

    # Получаем ссылку для скачивания
    download_url_req = f"{API_BASE_URL}/download?path={file_path}"
    response = requests.get(download_url_req, headers=headers)

    if response.status_code == 200:
        href = response.json().get("href")
        if not href:
            raise ProcessingError(ERR_NETWORK, "Failed to get download link for index.json")

        # Скачиваем файл
        file_response = requests.get(href)
        if file_response.status_code == 200:
            try:
                return file_response.json()
            except json.JSONDecodeError:
                raise ProcessingError(ERR_NETWORK, "Failed to parse existing index.json")
        else:
            raise ProcessingError(ERR_NETWORK, f"Failed to download index.json content: {file_response.status_code}")

    elif response.status_code == 404:
        logger.info("index.json not found, starting fresh.")
        return None
    else:
        raise ProcessingError(ERR_NETWORK, f"Failed to check index.json: {response.text}")


# Загружаем index.json в базовую папку диска
def upload_index_json(data: Dict[str, Any]) -> None:
    folder_path = get_current_day_folder_path()
    ensure_folder(folder_path)

    file_path = f"{folder_path}/index.json"
    headers = get_headers()

    # Получаем ссылку для загрузки
    upload_url_req = f"{API_BASE_URL}/upload?path={file_path}&overwrite=true"
    response = requests.get(upload_url_req, headers=headers)

    if response.status_code == 200:
        href = response.json().get("href")
        if not href:
            raise ProcessingError(ERR_NETWORK, "Failed to get upload link for index.json")

        # Загружаем и конвертируем файл
        json_data = json.dumps(data, ensure_ascii=False, indent=2)

        upload_response = requests.put(href, data=json_data.encode('utf-8'))

        if upload_response.status_code in [201, 202, 200]:
            logger.info("index.json uploaded successfully.")
        else:
            raise ProcessingError(ERR_NETWORK, f"Failed to upload index.json content: {upload_response.status_code}")
    else:
        raise ProcessingError(ERR_NETWORK, f"Failed to get upload link: {response.text}")
