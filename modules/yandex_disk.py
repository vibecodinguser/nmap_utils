"""Модуль для работы с Яндекс.Диском"""
import os
import json
import requests
from datetime import datetime
from config import BASE_FOLDER_PATH, YANDEX_DISK_API_KEY

LOCAL_DATA_FOLDER = "./data"
DATE_FORMAT = "%Y-%m-%d"

API_BASE = "https://cloud-api.yandex.net/v1/disk"


def _get_headers():
    """Возвращает заголовки для запросов к API"""
    return {"Authorization": f"OAuth {YANDEX_DISK_API_KEY}"}


def _get_today_folder():
    """Возвращает путь к папке текущей даты"""
    today = datetime.now().strftime(DATE_FORMAT)
    return f"{BASE_FOLDER_PATH}/{today}"


def ensure_folder_exists():
    """Проверяет и создаёт папку на Яндекс.Диске"""
    folder_path = _get_today_folder()
    url = f"{API_BASE}/resources"
    params = {"path": folder_path}
    
    try:
        response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
        
        if response.status_code == 404:
            # Папка не существует, создаём
            url = f"{API_BASE}/resources"
            params = {"path": folder_path}
            response = requests.put(url, headers=_get_headers(), params=params, timeout=10)
            if response.status_code not in [201, 409]:
                error_msg = response.text
                try:
                    error_json = response.json()
                    error_msg = error_json.get("description", error_json.get("message", error_msg))
                except:
                    pass
                raise Exception(f"Не удалось создать папку на Яндекс.Диске: {error_msg}")
        elif response.status_code not in [200, 201]:
            error_msg = response.text
            try:
                error_json = response.json()
                error_msg = error_json.get("description", error_json.get("message", error_msg))
            except:
                pass
            raise Exception(f"Ошибка доступа к Яндекс.Диску: {error_msg}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Ошибка подключения к Яндекс.Диску: {str(e)}")
    
    return folder_path


def download_index_json(folder_path):
    """Скачивает index.json с Яндекс.Диска, если существует"""
    file_path = f"{folder_path}/index.json"
    url = f"{API_BASE}/resources/download"
    params = {"path": file_path}
    
    try:
        response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
        
        if response.status_code == 200:
            download_url = response.json().get("href")
            if download_url:
                file_response = requests.get(download_url, timeout=30)
                if file_response.status_code == 200:
                    os.makedirs(LOCAL_DATA_FOLDER, exist_ok=True)
                    local_path = os.path.join(LOCAL_DATA_FOLDER, "index.json")
                    with open(local_path, "wb") as f:
                        f.write(file_response.content)
                    return local_path
    except requests.exceptions.RequestException:
        # Игнорируем ошибки при скачивании - файл может не существовать
        pass
    
    return None


def upload_index_json(folder_path, local_file_path):
    """Загружает index.json на Яндекс.Диск"""
    file_path = f"{folder_path}/index.json"
    
    try:
        # Получаем URL для загрузки
        url = f"{API_BASE}/resources/upload"
        params = {"path": file_path, "overwrite": "true"}
        
        response = requests.get(url, headers=_get_headers(), params=params, timeout=10)
        
        if response.status_code == 200:
            upload_url = response.json().get("href")
            if upload_url:
                with open(local_file_path, "rb") as f:
                    file_data = f.read()
                    upload_response = requests.put(upload_url, data=file_data, timeout=30)
                    if upload_response.status_code == 201:
                        return True
                    else:
                        error_msg = upload_response.text
                        try:
                            error_json = upload_response.json()
                            error_msg = error_json.get("description", error_json.get("message", error_msg))
                        except:
                            pass
                        raise Exception(f"Не удалось загрузить файл на Яндекс.Диск: {error_msg}")
            else:
                raise Exception("Не получен URL для загрузки файла")
        else:
            error_msg = response.text
            try:
                error_json = response.json()
                error_msg = error_json.get("description", error_json.get("message", error_msg))
            except:
                pass
            raise Exception(f"Не удалось получить URL для загрузки: {error_msg}")
    except requests.exceptions.RequestException as e:
        raise Exception(f"Ошибка подключения к Яндекс.Диску при загрузке: {str(e)}")

