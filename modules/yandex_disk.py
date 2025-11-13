"""Модуль для работы с Яндекс.Диском"""
import os
import json
import requests
import time
from datetime import datetime
from config import BASE_FOLDER_PATH, YANDEX_DISK_API_KEY

LOCAL_DATA_FOLDER = "./data"
DATE_FORMAT = "%Y-%m-%d"

API_BASE = "https://cloud-api.yandex.net/v1/disk"

# Таймауты: (connect_timeout, read_timeout)
TIMEOUT_API = (10, 30)  # Для API запросов
TIMEOUT_UPLOAD = (10, 60)  # Для загрузки файлов
TIMEOUT_DOWNLOAD = (10, 60)  # Для скачивания файлов

MAX_RETRIES = 3
RETRY_DELAY = 2  # секунды


def _get_headers():
    """Возвращает заголовки для запросов к API"""
    return {"Authorization": f"OAuth {YANDEX_DISK_API_KEY}"}


def _make_request_with_retry(method, url, max_retries=MAX_RETRIES, **kwargs):
    """Выполняет запрос с повторными попытками при ошибках таймаута"""
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            if method.upper() == "GET":
                response = requests.get(url, **kwargs)
            elif method.upper() == "PUT":
                response = requests.put(url, **kwargs)
            elif method.upper() == "POST":
                response = requests.post(url, **kwargs)
            else:
                raise ValueError(f"Неподдерживаемый метод: {method}")
            
            return response
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout, requests.exceptions.Timeout) as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = RETRY_DELAY * (2 ** attempt)  # Экспоненциальная задержка
                time.sleep(wait_time)
                continue
            else:
                raise
        except requests.exceptions.RequestException as e:
            # Для других ошибок не делаем retry
            raise
    
    if last_exception:
        raise last_exception


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
        response = _make_request_with_retry(
            "GET", 
            url, 
            headers=_get_headers(), 
            params=params, 
            timeout=TIMEOUT_API
        )
        
        if response.status_code == 404:
            # Папка не существует, создаём
            url = f"{API_BASE}/resources"
            params = {"path": folder_path}
            response = _make_request_with_retry(
                "PUT", 
                url, 
                headers=_get_headers(), 
                params=params, 
                timeout=TIMEOUT_API
            )
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
        response = _make_request_with_retry(
            "GET", 
            url, 
            headers=_get_headers(), 
            params=params, 
            timeout=TIMEOUT_API
        )
        
        if response.status_code == 200:
            download_url = response.json().get("href")
            if download_url:
                file_response = _make_request_with_retry(
                    "GET", 
                    download_url, 
                    timeout=TIMEOUT_DOWNLOAD
                )
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
        
        response = _make_request_with_retry(
            "GET", 
            url, 
            headers=_get_headers(), 
            params=params, 
            timeout=TIMEOUT_API
        )
        
        if response.status_code == 200:
            upload_url = response.json().get("href")
            if upload_url:
                with open(local_file_path, "rb") as f:
                    file_data = f.read()
                    upload_response = _make_request_with_retry(
                        "PUT", 
                        upload_url, 
                        data=file_data, 
                        timeout=TIMEOUT_UPLOAD
                    )
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

