import sys
import os
import unittest

sys.path.append(os.getcwd())

from unittest.mock import MagicMock, patch

mock_pynspd = MagicMock()
sys.modules['pynspd'] = mock_pynspd
sys.modules['pynspd.schemas'] = MagicMock()

from modules.prcs_nspd_border import process_nspd_border
from modules.prcs_flow import ProcessingError


class TestNspdBorder(unittest.TestCase):

    @patch('modules.prcs_nspd_border.Nspd')
    @patch('modules.prcs_nspd_border.process_geojson')
    @patch('modules.prcs_nspd_border.Layer36278Feature')
    def test_process_nspd_border_success(self, mock_layer_cls, mock_process_geojson, mock_nspd_cls):
        # Создание клиента и поиск результатов
        mock_nspd_instance = MagicMock()
        mock_nspd_cls.return_value = mock_nspd_instance

        # Проверка результата поиска как списка содержащего объект
        mock_feature = MagicMock()
        mock_feature.model_dump.return_value = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[37.6173, 55.7558], [37.6200, 55.7600], [37.6150, 55.7550], [37.6173, 55.7558]]]
            },
            "properties": {"name": "Test Municipal Border"}
        }
        mock_nspd_instance.search_in_layer.return_value = [mock_feature]

        # Парсинг GeoJSON
        mock_process_geojson.return_value = {
            "paths": {"path1": {"coords": [[37.6173, 55.7558], [37.6200, 55.7600]]}},
            "points": {"uuid1": {"coords": [37.6173, 55.7558], "desc": "Old Desc"}},
            "metadata": []
        }

        registry_number = "23:01-6.1"
        result = process_nspd_border(registry_number)

        # Проверка, что поиск НСПД был вызван
        mock_nspd_instance.search_in_layer.assert_called_with(registry_number, mock_layer_cls)

        # Проверка, что process_geojson был вызван
        self.assertTrue(mock_process_geojson.called)

        # Проверка результатов парсинга — описание должно содержать "МО НСПД:"
        self.assertEqual(result['points']['uuid1']['desc'], f"МО НСПД: {registry_number}")
        self.assertIn(f"МО НСПД: {registry_number}", result['metadata'])

    @patch('modules.prcs_nspd_border.Nspd')
    def test_process_nspd_border_not_found(self, mock_nspd_cls):
        mock_nspd_instance = MagicMock()
        mock_nspd_cls.return_value = mock_nspd_instance
        mock_nspd_instance.search_in_layer.return_value = []

        with self.assertRaises(ProcessingError) as cm:
            process_nspd_border("invalid_number")

        self.assertIn("не найдено", str(cm.exception))

    @patch('modules.prcs_nspd_border.Nspd')
    @patch('modules.prcs_nspd_border.process_geojson')
    @patch('modules.prcs_nspd_border.Layer36278Feature')
    def test_process_nspd_border_with_dict_method(self, mock_layer_cls, mock_process_geojson, mock_nspd_cls):
        """Тест для объекта с методом dict() вместо model_dump()"""
        mock_nspd_instance = MagicMock()
        mock_nspd_cls.return_value = mock_nspd_instance

        # Создаём объект без model_dump, но с dict
        mock_feature = MagicMock(spec=[])
        mock_feature.dict = MagicMock(return_value={
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[37.0, 55.0], [37.1, 55.1], [37.0, 55.0]]]
            },
            "properties": {"name": "Test Border"}
        })
        # Убираем model_dump
        del mock_feature.model_dump
        mock_nspd_instance.search_in_layer.return_value = [mock_feature]

        mock_process_geojson.return_value = {
            "paths": {},
            "points": {"uuid1": {"coords": [37.0, 55.0], "desc": "Old"}},
            "metadata": []
        }

        registry_number = "77:00-1.1"
        result = process_nspd_border(registry_number)

        # Проверка, что dict был вызван
        mock_feature.dict.assert_called_once()
        self.assertEqual(result['points']['uuid1']['desc'], f"МО НСПД: {registry_number}")

    @patch('modules.prcs_nspd_border.Nspd')
    @patch('modules.prcs_nspd_border.process_geojson')
    @patch('modules.prcs_nspd_border.Layer36278Feature')
    def test_process_nspd_border_multiple_points(self, mock_layer_cls, mock_process_geojson, mock_nspd_cls):
        """Тест обработки нескольких точек в результате"""
        mock_nspd_instance = MagicMock()
        mock_nspd_cls.return_value = mock_nspd_instance

        mock_feature = MagicMock()
        mock_feature.model_dump.return_value = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[]]},
            "properties": {}
        }
        mock_nspd_instance.search_in_layer.return_value = [mock_feature]

        # Несколько точек в результате
        mock_process_geojson.return_value = {
            "paths": {},
            "points": {
                "uuid1": {"coords": [37.0, 55.0], "desc": "Point 1"},
                "uuid2": {"coords": [37.1, 55.1], "desc": "Point 2"},
                "uuid3": {"coords": [37.2, 55.2], "desc": "Point 3"}
            },
            "metadata": ["existing_meta"]
        }

        registry_number = "23:02-5.5"
        result = process_nspd_border(registry_number)

        # Все точки должны получить обновлённое описание
        for point in result['points'].values():
            self.assertEqual(point['desc'], f"МО НСПД: {registry_number}")

        # Метаданные должны содержать новую запись в начале
        self.assertEqual(result['metadata'][0], f"МО НСПД: {registry_number}")
        self.assertIn("existing_meta", result['metadata'])


if __name__ == '__main__':
    unittest.main()
