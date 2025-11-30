import unittest
import tempfile
import os
import json
from io import BytesIO
from unittest.mock import patch, MagicMock, Mock
from app import app, allowed_file


class TestApp(unittest.TestCase):

    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def test_allowed_file_valid_extensions(self):
        # Проверка допустимых расширений файлов
        valid_files = [
            'test.zip',
            'test.geojson',
            'test.gpx',
            'test.kml',
            'test.kmz',
            'test.topojson',
            'test.wkt'
        ]
        for filename in valid_files:
            self.assertTrue(allowed_file(filename), f"{filename} should be allowed")

    def test_allowed_file_invalid_extensions(self):
        # Проверка недопустимых расширений файлов
        invalid_files = [
            'test.txt',
            'test.pdf',
            'test.jpg',
            'test.csv',
            'test',
            'test.'
        ]
        for filename in invalid_files:
            self.assertFalse(allowed_file(filename), f"{filename} should not be allowed")

    def test_allowed_file_case_insensitive(self):
        # Проверка, что проверка расширения файла не зависит от регистра
        self.assertTrue(allowed_file('test.ZIP'))
        self.assertTrue(allowed_file('test.GeoJSON'))
        self.assertTrue(allowed_file('test.GPX'))

    def test_index_get_request(self):
        # Проверка GET-запроса на главную страницу
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'<!DOCTYPE html>', response.data)

    @patch('app.ensure_folder')
    @patch('app.download_index_json')
    @patch('app.upload_index_json')
    @patch('app.process_gpx')
    def test_index_post_with_gpx_file(self, mock_process_gpx, mock_upload, mock_download, mock_ensure):
        # Проверка POST-запроса с файлом GPX
        mock_ensure.return_value = None
        mock_download.return_value = {"paths": {}, "points": {}}
        mock_upload.return_value = None
        mock_process_gpx.return_value = {
            "paths": {"uuid1": [[37.6173, 55.7558]]},
            "points": {"uuid1": {"coords": [37.6173, 55.7558], "desc": "Test"}},
            "metadata": ["Test Track"]
        }
        data = {
            'files': (BytesIO(b'<?xml version="1.0"?><gpx></gpx>'), 'test.gpx')
        }

        response = self.client.post('/', data=data, content_type='multipart/form-data')

        self.assertEqual(response.status_code, 200)
        mock_process_gpx.assert_called_once()
        mock_upload.assert_called_once()

    def test_index_post_no_files(self):
        # Проверка POST-запроса без файлов
        response = self.client.post('/', data={}, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'No files selected', response.data)

    @patch('app.ensure_folder')
    def test_index_post_yandex_disk_error(self, mock_ensure):
        # Проверка POST-запроса с ошибкой Yandex Disk
        from modules.prcs_flow import ProcessingError, ERR_NETWORK
        mock_ensure.side_effect = ProcessingError(ERR_NETWORK, "Connection failed")

        data = {
            'files': (BytesIO(b'test'), 'test.gpx')
        }

        response = self.client.post('/', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Yandex.Disk Error', response.data)

    @patch('app.ensure_folder')
    @patch('app.download_index_json')
    def test_index_post_download_error(self, mock_download, mock_ensure):
        # Проверка POST-запроса с ошибкой загрузки index.json
        from modules.prcs_flow import ProcessingError, ERR_NETWORK
        mock_ensure.return_value = None
        mock_download.side_effect = ProcessingError(ERR_NETWORK, "Download failed")

        data = {
            'files': (BytesIO(b'test'), 'test.gpx')
        }

        response = self.client.post('/', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Failed to retrieve index.json', response.data)

    @patch('app.ensure_folder')
    @patch('app.download_index_json')
    @patch('app.upload_index_json')
    @patch('app.process_gpx')
    def test_index_post_processing_error(self, mock_process_gpx, mock_upload, mock_download, mock_ensure):
        # Проверка POST-запроса с ошибкой обработки файла
        from modules.prcs_flow import ProcessingError, ERR_SHAPEFILE
        mock_ensure.return_value = None
        mock_download.return_value = {"paths": {}, "points": {}}
        mock_process_gpx.side_effect = ProcessingError(ERR_SHAPEFILE, "Invalid file")

        data = {
            'files': (BytesIO(b'test'), 'test.gpx')
        }

        response = self.client.post('/', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        # File should be skipped
        self.assertIn(b'Invalid file', response.data)

    def test_index_post_invalid_file_type(self):
        # Проверка POST-запроса с недопустимым типом файла
        data = {
            'files': (BytesIO(b'test'), 'test.txt')
        }

        response = self.client.post('/', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Invalid file type', response.data)

    @patch('app.ensure_folder')
    @patch('app.download_index_json')
    @patch('app.upload_index_json')
    @patch('app.process_geojson')
    @patch('app.process_gpx')
    def test_index_post_multiple_files(self, mock_gpx, mock_geojson, mock_upload, mock_download, mock_ensure):
        # Проверка POST-запроса с несколькими файлами
        mock_ensure.return_value = None
        mock_download.return_value = {"paths": {}, "points": {}}
        mock_upload.return_value = None

        mock_gpx.return_value = {
            "paths": {"uuid1": [[37.6173, 55.7558]]},
            "points": {"uuid1": {"coords": [37.6173, 55.7558], "desc": "GPX"}},
            "metadata": []
        }

        mock_geojson.return_value = {
            "paths": {"uuid2": [[37.6200, 55.7600]]},
            "points": {"uuid2": {"coords": [37.6200, 55.7600], "desc": "GeoJSON"}},
            "metadata": []
        }

        data = {
            'files': [
                (BytesIO(b'gpx'), 'test.gpx'),
                (BytesIO(b'geojson'), 'test.geojson')
            ]
        }

        response = self.client.post('/', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        mock_gpx.assert_called_once()
        mock_geojson.assert_called_once()

    def test_stream_logs_endpoint(self):
        # Проверка SSE stream logs endpoint
        response = self.client.get('/stream-logs/test-session-id')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/event-stream; charset=utf-8')

    @patch('app.allowed_file')
    def test_upload_async_endpoint(self, mock_allowed):
        # Проверка async upload endpoint
        mock_allowed.return_value = True

        data = {
            'files': (BytesIO(b'test'), 'test.gpx')
        }

        response = self.client.post('/upload-async', data=data, content_type='multipart/form-data')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertIn('session_id', response_data)
        self.assertTrue(len(response_data['session_id']) > 0)

    def test_upload_async_no_files(self):
        # Проверка async upload с неподдерживаемым типом файла
        response = self.client.post('/upload-async', data={}, content_type='multipart/form-data')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertIn('session_id', response_data)

    @patch('app.allowed_file')
    def test_upload_async_multiple_files(self, mock_allowed):
        # Проверка async upload с несколькими файлами
        mock_allowed.return_value = True

        data = {
            'files': [
                (BytesIO(b'test1'), 'test1.gpx'),
                (BytesIO(b'test2'), 'test2.geojson')
            ]
        }

        response = self.client.post('/upload-async', data=data, content_type='multipart/form-data')

        self.assertEqual(response.status_code, 200)
        response_data = json.loads(response.data)
        self.assertIn('session_id', response_data)

    @patch('app.ensure_folder')
    @patch('app.download_index_json')
    @patch('app.upload_index_json')
    @patch('app.process_gpx')
    def test_index_post_upload_error(self, mock_process_gpx, mock_upload, mock_download, mock_ensure):
        # Проверка POST-запроса с ошибкой загрузки index.json
        from modules.prcs_flow import ProcessingError, ERR_NETWORK
        mock_ensure.return_value = None
        mock_download.return_value = {"paths": {}, "points": {}}
        mock_process_gpx.return_value = {
            "paths": {"uuid1": [[37.6173, 55.7558]]},
            "points": {"uuid1": {"coords": [37.6173, 55.7558], "desc": "Test"}},
            "metadata": []
        }
        mock_upload.side_effect = ProcessingError(ERR_NETWORK, "Upload failed")

        data = {
            'files': (BytesIO(b'test'), 'test.gpx')
        }

        response = self.client.post('/', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Failed to save results to Yandex.Disk', response.data)

    @patch('app.ensure_folder')
    @patch('app.download_index_json')
    @patch('app.upload_index_json')
    @patch('app.process_gpx')
    def test_index_post_creates_new_index_if_none(self, mock_process_gpx, mock_upload, mock_download, mock_ensure):
        # Проверка POST-запроса с созданием нового index.json
        mock_ensure.return_value = None
        mock_download.return_value = None
        mock_upload.return_value = None
        mock_process_gpx.return_value = {
            "paths": {"uuid1": [[37.6173, 55.7558]]},
            "points": {"uuid1": {"coords": [37.6173, 55.7558], "desc": "Test"}},
            "metadata": []
        }

        data = {
            'files': (BytesIO(b'test'), 'test.gpx')
        }

        response = self.client.post('/', data=data, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        mock_upload.assert_called_once()


if __name__ == '__main__':
    unittest.main()
