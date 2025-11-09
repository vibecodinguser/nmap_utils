import unittest
from unittest.mock import patch, MagicMock, mock_open
import os
import tempfile
from datetime import datetime
import requests

# Импортируем модуль для тестирования
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tools.yandex_disk import (
    get_target_folder_path,
    check_and_create_folder,
    download_index_json,
    upload_index_json
)


class TestGetTargetFolderPath(unittest.TestCase):
    """Тесты для функции get_target_folder_path"""

    @patch('tools.yandex_disk.BASE_FOLDER_PATH', 'test/path')
    @patch('tools.yandex_disk.datetime')
    def test_get_target_folder_path(self, mock_datetime):
        """Тест получения пути к папке с текущей датой"""
        # Настраиваем mock для datetime
        mock_now = MagicMock()
        mock_now.strftime.return_value = '2024-01-15'
        mock_datetime.now.return_value = mock_now

        result = get_target_folder_path()
        
        self.assertEqual(result, 'test/path/2024-01-15')
        mock_now.strftime.assert_called_once_with('%Y-%m-%d')

    @patch('tools.yandex_disk.BASE_FOLDER_PATH', 'Приложения/Блокнот')
    def test_get_target_folder_path_real_date(self):
        """Тест с реальной датой"""
        result = get_target_folder_path()
        expected_date = datetime.now().strftime('%Y-%m-%d')
        self.assertEqual(result, f'Приложения/Блокнот/{expected_date}')


class TestCheckAndCreateFolder(unittest.TestCase):
    """Тесты для функции check_and_create_folder"""

    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    @patch('tools.yandex_disk.requests.put')
    def test_folder_exists(self, mock_put, mock_get, mock_get_path):
        """Тест когда папка уже существует"""
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        result = check_and_create_folder()

        self.assertEqual(result, 'test/path/2024-01-15')
        mock_get.assert_called_once()
        mock_put.assert_not_called()

    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    @patch('tools.yandex_disk.requests.put')
    def test_folder_created_successfully(self, mock_put, mock_get, mock_get_path):
        """Тест создания новой папки"""
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        # Первый запрос - папка не найдена
        mock_get_response = MagicMock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response

        # Второй запрос - папка создана
        mock_put_response = MagicMock()
        mock_put_response.status_code = 201
        mock_put.return_value = mock_put_response

        result = check_and_create_folder()

        self.assertEqual(result, 'test/path/2024-01-15')
        mock_get.assert_called_once()
        mock_put.assert_called_once()

    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    @patch('tools.yandex_disk.requests.put')
    def test_folder_already_exists_409(self, mock_put, mock_get, mock_get_path):
        """Тест когда папка уже существует (409)"""
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        mock_get_response = MagicMock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response

        mock_put_response = MagicMock()
        mock_put_response.status_code = 409  # Конфликт - папка уже существует
        mock_put.return_value = mock_put_response

        result = check_and_create_folder()

        self.assertEqual(result, 'test/path/2024-01-15')
        mock_put.assert_called_once()

    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    def test_request_exception(self, mock_get, mock_get_path):
        """Тест обработки исключения при запросе"""
        mock_get_path.return_value = 'test/path/2024-01-15'
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        with self.assertRaises(requests.exceptions.RequestException):
            check_and_create_folder()


class TestDownloadIndexJson(unittest.TestCase):
    """Тесты для функции download_index_json"""

    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    @patch('tools.yandex_disk.INDEX_JSON_PATH', '/tmp/test_index.json')
    def test_download_success(self, mock_get, mock_get_path):
        """Тест успешного скачивания файла"""
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        # Первый запрос - получение URL для скачивания
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = {'href': 'https://download.url/file'}
        mock_response1.raise_for_status = MagicMock()

        # Второй запрос - скачивание файла
        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.content = b'{"test": "data"}'
        mock_response2.raise_for_status = MagicMock()

        mock_get.side_effect = [mock_response1, mock_response2]

        with patch('builtins.open', mock_open()) as mock_file:
            result = download_index_json()

        self.assertTrue(result)
        mock_file.assert_called_once_with('/tmp/test_index.json', 'wb')
        mock_file().write.assert_called_once_with(b'{"test": "data"}')

    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    def test_download_no_href(self, mock_get, mock_get_path):
        """Тест когда не получен URL для скачивания"""
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Нет href
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = download_index_json()

        self.assertFalse(result)

    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    def test_download_request_exception(self, mock_get, mock_get_path):
        """Тест обработки исключения при скачивании"""
        mock_get_path.return_value = 'test/path/2024-01-15'
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        result = download_index_json()

        self.assertFalse(result)

    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    def test_download_http_error(self, mock_get, mock_get_path):
        """Тест обработки HTTP ошибки"""
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("Not found")
        mock_get.return_value = mock_response

        result = download_index_json()

        self.assertFalse(result)


class TestUploadIndexJson(unittest.TestCase):
    """Тесты для функции upload_index_json"""

    @patch('tools.yandex_disk.os.path.exists')
    @patch('tools.yandex_disk.os.path.getsize')
    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    @patch('tools.yandex_disk.requests.put')
    @patch('tools.yandex_disk.INDEX_JSON_PATH', '/tmp/test_index.json')
    def test_upload_success(self, mock_put, mock_get, mock_get_path, mock_getsize, mock_exists):
        """Тест успешной загрузки файла"""
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        # Запрос URL для загрузки
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = {'href': 'https://upload.url/file'}
        mock_response1.raise_for_status = MagicMock()
        mock_get.return_value = mock_response1

        # Запрос загрузки файла
        mock_response2 = MagicMock()
        mock_response2.status_code = 201
        mock_put.return_value = mock_response2

        with patch('builtins.open', mock_open(read_data=b'{"test": "data"}')):
            with patch('tools.yandex_disk.os.remove') as mock_remove:
                result = upload_index_json()

        self.assertTrue(result)
        mock_remove.assert_called_once_with('/tmp/test_index.json')

    @patch('tools.yandex_disk.os.path.exists')
    @patch('tools.yandex_disk.INDEX_JSON_PATH', '/tmp/test_index.json')
    def test_upload_file_not_exists(self, mock_exists):
        """Тест когда файл не существует"""
        mock_exists.return_value = False

        result = upload_index_json()

        self.assertFalse(result)

    @patch('tools.yandex_disk.os.path.exists')
    @patch('tools.yandex_disk.os.path.getsize')
    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    @patch('tools.yandex_disk.INDEX_JSON_PATH', '/tmp/test_index.json')
    def test_upload_no_href(self, mock_get, mock_get_path, mock_getsize, mock_exists):
        """Тест когда не получен URL для загрузки"""
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Нет href
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = upload_index_json()

        self.assertFalse(result)

    @patch('tools.yandex_disk.os.path.exists')
    @patch('tools.yandex_disk.os.path.getsize')
    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    @patch('tools.yandex_disk.requests.put')
    @patch('tools.yandex_disk.INDEX_JSON_PATH', '/tmp/test_index.json')
    def test_upload_failed_status(self, mock_put, mock_get, mock_get_path, mock_getsize, mock_exists):
        """Тест когда загрузка не удалась"""
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_get_path.return_value = 'test/path/2024-01-15'
        
        mock_response1 = MagicMock()
        mock_response1.status_code = 200
        mock_response1.json.return_value = {'href': 'https://upload.url/file'}
        mock_response1.raise_for_status = MagicMock()
        mock_get.return_value = mock_response1

        mock_response2 = MagicMock()
        mock_response2.status_code = 500
        mock_response2.text = 'Internal Server Error'
        mock_put.return_value = mock_response2

        with patch('builtins.open', mock_open(read_data=b'{"test": "data"}')):
            result = upload_index_json()

        self.assertFalse(result)

    @patch('tools.yandex_disk.os.path.exists')
    @patch('tools.yandex_disk.os.path.getsize')
    @patch('tools.yandex_disk.get_target_folder_path')
    @patch('tools.yandex_disk.requests.get')
    @patch('tools.yandex_disk.INDEX_JSON_PATH', '/tmp/test_index.json')
    def test_upload_request_exception(self, mock_get, mock_get_path, mock_getsize, mock_exists):
        """Тест обработки исключения при загрузке"""
        mock_exists.return_value = True
        mock_getsize.return_value = 1024
        mock_get_path.return_value = 'test/path/2024-01-15'
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        result = upload_index_json()

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()

