import unittest
import json
from unittest.mock import patch, Mock, MagicMock
from datetime import datetime
from modules.prcs_upload import (
    get_headers,
    get_current_day_folder_path,
    ensure_folder,
    download_index_json,
    upload_index_json,
    BASE_FOLDER_PATH,
    API_BASE_URL
)
from modules.prcs_flow import ProcessingError, ERR_NETWORK


class TestPrcsUpload(unittest.TestCase):

    def test_get_headers(self):
        # Проверка формирования http заголовков
        headers = get_headers()

        self.assertIn('Authorization', headers)
        self.assertIn('Content-Type', headers)
        self.assertTrue(headers['Authorization'].startswith('OAuth '))
        self.assertEqual(headers['Content-Type'], 'application/json')

    @patch('modules.prcs_upload.datetime')
    def test_get_current_day_folder_path(self, mock_datetime):
        # Генерация пути к папке текущего дня
        mock_datetime.now.return_value = datetime(2025, 11, 30, 14, 0, 0)
        path = get_current_day_folder_path()
        expected = f"{BASE_FOLDER_PATH}/2025-11-30"

        self.assertEqual(path, expected)

    @patch('modules.prcs_upload.requests.get')
    def test_ensure_folder_already_exists(self, mock_get):
        # Проверка создания папки, если она уже существует
        mock_response = Mock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        ensure_folder("test/path")
        mock_get.assert_called_once()

    @patch('modules.prcs_upload.requests.put')
    @patch('modules.prcs_upload.requests.get')
    def test_ensure_folder_creates_new(self, mock_get, mock_put):
        # Проверка создания новой папки
        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_put.return_value = mock_put_response
        ensure_folder("test/path")
        mock_get.assert_called_once()
        mock_put.assert_called_once()

    @patch('modules.prcs_upload.requests.put')
    @patch('modules.prcs_upload.requests.get')
    def test_ensure_folder_conflict(self, mock_get, mock_put):
        # Проверка обработки конфликта (409)
        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response
        mock_put_response = Mock()
        mock_put_response.status_code = 409
        mock_put.return_value = mock_put_response
        ensure_folder("test/path")
        mock_put.assert_called_once()

    @patch('modules.prcs_upload.requests.put')
    @patch('modules.prcs_upload.requests.get')
    def test_ensure_folder_create_fails(self, mock_get, mock_put):
        # Проверка ошибки при создании папки
        mock_get_response = Mock()
        mock_get_response.status_code = 404
        mock_get.return_value = mock_get_response
        mock_put_response = Mock()
        mock_put_response.status_code = 500
        mock_put_response.text = "Server error"
        mock_put.return_value = mock_put_response

        with self.assertRaises(ProcessingError) as context:
            ensure_folder("test/path")

        self.assertEqual(context.exception.code, ERR_NETWORK)
        self.assertIn("Failed to create folder", context.exception.message)

    @patch('modules.prcs_upload.requests.get')
    def test_ensure_folder_check_fails(self, mock_get):
        # Проверка ошибки при проверке папки
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_get.return_value = mock_response

        with self.assertRaises(ProcessingError) as context:
            ensure_folder("test/path")

        self.assertEqual(context.exception.code, ERR_NETWORK)
        self.assertIn("Failed to check folder", context.exception.message)

    @patch('modules.prcs_upload.requests.get')
    def test_download_index_json_success(self, mock_get):
        # Успешная загрузка index.json
        test_data = {"paths": {"id1": [[0, 0]]}, "points": {"id1": {"coords": [0, 0], "desc": "test"}}}

        # Первый вызов: получение ссылки на загрузку
        mock_link_response = Mock()
        mock_link_response.status_code = 200
        mock_link_response.json.return_value = {"href": "http://download.url"}
        # Первый вызов: скачивание файла
        mock_file_response = Mock()
        mock_file_response.status_code = 200
        mock_file_response.json.return_value = test_data
        mock_get.side_effect = [mock_link_response, mock_file_response]

        result = download_index_json()

        self.assertEqual(result, test_data)
        self.assertEqual(mock_get.call_count, 2)

    @patch('modules.prcs_upload.requests.get')
    def test_download_index_json_not_found(self, mock_get):
        # Загрузка index.json, когда файл не существует
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response
        result = download_index_json()

        self.assertIsNone(result)

    @patch('modules.prcs_upload.requests.get')
    def test_download_index_json_no_href(self, mock_get):
        # Отсутствует ссылка для скачивания
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # No href
        mock_get.return_value = mock_response

        with self.assertRaises(ProcessingError) as context:
            download_index_json()

        self.assertIn("Failed to get download link", context.exception.message)

    @patch('modules.prcs_upload.requests.get')
    def test_download_index_json_download_fails(self, mock_get):
        # Загрузка index.json, когда загрузка файла не удалась
        # Первый вызов: получение ссылки на загрузку
        mock_link_response = Mock()
        mock_link_response.status_code = 200
        mock_link_response.json.return_value = {"href": "http://download.url"}
        # Второй вызов: загрузка файла не удалась
        mock_file_response = Mock()
        mock_file_response.status_code = 500
        mock_get.side_effect = [mock_link_response, mock_file_response]

        with self.assertRaises(ProcessingError) as context:
            download_index_json()

        self.assertIn("Failed to download index.json content", context.exception.message)

    @patch('modules.prcs_upload.requests.get')
    def test_download_index_json_invalid_json(self, mock_get):
        # Загрузка index.json, когда JSON некорректен
        # Первый вызов: получение ссылки на загрузку
        mock_link_response = Mock()
        mock_link_response.status_code = 200
        mock_link_response.json.return_value = {"href": "http://download.url"}
        # Второй вызов: некорректный JSON
        mock_file_response = Mock()
        mock_file_response.status_code = 200
        mock_file_response.json.side_effect = json.JSONDecodeError("Invalid", "", 0)
        mock_get.side_effect = [mock_link_response, mock_file_response]

        with self.assertRaises(ProcessingError) as context:
            download_index_json()

        self.assertIn("Failed to parse existing index.json", context.exception.message)

    @patch('modules.prcs_upload.requests.get')
    def test_download_index_json_check_fails(self, mock_get):
        # Загрузка index.json, когда проверка не удалась
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_get.return_value = mock_response

        with self.assertRaises(ProcessingError) as context:
            download_index_json()

        self.assertIn("Failed to check index.json", context.exception.message)

    @patch('modules.prcs_upload.requests.put')
    @patch('modules.prcs_upload.requests.get')
    @patch('modules.prcs_upload.ensure_folder')
    def test_upload_index_json_success(self, mock_ensure, mock_get, mock_put):
        # Успешная загрузка index.json
        test_data = {"paths": {}, "points": {}}
        # GET: Получение ссылки на загрузку
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"href": "http://upload.url"}
        mock_get.return_value = mock_get_response
        # PUT: Загрузка файла
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_put.return_value = mock_put_response
        upload_index_json(test_data)
        mock_ensure.assert_called_once()
        mock_get.assert_called_once()
        mock_put.assert_called_once()

    @patch('modules.prcs_upload.requests.put')
    @patch('modules.prcs_upload.requests.get')
    @patch('modules.prcs_upload.ensure_folder')
    def test_upload_index_json_no_href(self, mock_ensure, mock_get, mock_put):
        # Загрузка index.json, когда нет ссылки на загрузку
        test_data = {"paths": {}, "points": {}}

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {}
        mock_get.return_value = mock_get_response

        with self.assertRaises(ProcessingError) as context:
            upload_index_json(test_data)

        self.assertIn("Failed to get upload link", context.exception.message)

    @patch('modules.prcs_upload.requests.put')
    @patch('modules.prcs_upload.requests.get')
    @patch('modules.prcs_upload.ensure_folder')
    def test_upload_index_json_upload_fails(self, mock_ensure, mock_get, mock_put):
        # Загрузка index.json, когда загрузка не удалась
        test_data = {"paths": {}, "points": {}}
        # GET: Получение ссылки на загрузку
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"href": "http://upload.url"}
        mock_get.return_value = mock_get_response
        # PUT: Загрузка не удалась
        mock_put_response = Mock()
        mock_put_response.status_code = 500
        mock_put.return_value = mock_put_response

        with self.assertRaises(ProcessingError) as context:
            upload_index_json(test_data)

        self.assertIn("Failed to upload index.json content", context.exception.message)

    @patch('modules.prcs_upload.requests.get')
    @patch('modules.prcs_upload.ensure_folder')
    def test_upload_index_json_get_link_fails(self, mock_ensure, mock_get):
        # Загрузка index.json, когда получение ссылки на загрузку не удалась
        test_data = {"paths": {}, "points": {}}

        mock_get_response = Mock()
        mock_get_response.status_code = 500
        mock_get_response.text = "Server error"
        mock_get.return_value = mock_get_response

        with self.assertRaises(ProcessingError) as context:
            upload_index_json(test_data)

        self.assertIn("Failed to get upload link", context.exception.message)

    @patch('modules.prcs_upload.requests.put')
    @patch('modules.prcs_upload.requests.get')
    @patch('modules.prcs_upload.ensure_folder')
    def test_upload_index_json_accepts_202(self, mock_ensure, mock_get, mock_put):
        # Загрузка index.json, когда загрузка принимает 202 статус
        test_data = {"paths": {}, "points": {}}

        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"href": "http://upload.url"}
        mock_get.return_value = mock_get_response

        mock_put_response = Mock()
        mock_put_response.status_code = 202  # Accepted
        mock_put.return_value = mock_put_response

        # Should not raise exception
        upload_index_json(test_data)

    @patch('modules.prcs_upload.requests.put')
    @patch('modules.prcs_upload.requests.get')
    @patch('modules.prcs_upload.ensure_folder')
    def test_upload_index_json_utf8_encoding(self, mock_ensure, mock_get, mock_put):
        # Проверка, что загрузка корректно кодирует UTF-8 данные
        test_data = {"paths": {}, "points": {"id1": {"coords": [0, 0], "desc": "Тест"}}}
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = {"href": "http://upload.url"}
        mock_get.return_value = mock_get_response
        mock_put_response = Mock()
        mock_put_response.status_code = 201
        mock_put.return_value = mock_put_response
        upload_index_json(test_data)
        call_args = mock_put.call_args
        uploaded_data = call_args[1]['data']

        self.assertIsInstance(uploaded_data, bytes)
        self.assertIn('Тест'.encode('utf-8'), uploaded_data)  # Поддержка Русского языка в UTF-8


if __name__ == '__main__':
    unittest.main()
