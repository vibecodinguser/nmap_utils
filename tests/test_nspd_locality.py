import sys
import os
import unittest

sys.path.append(os.getcwd())

from unittest.mock import MagicMock, patch

mock_pynspd = MagicMock()
sys.modules['pynspd'] = mock_pynspd
sys.modules['pynspd.schemas'] = MagicMock()

from modules.prcs_nspd_locality import process_nspd_locality
from modules.prcs_flow import ProcessingError


class TestNspdLocality(unittest.TestCase):

    @patch('modules.prcs_nspd_locality.Nspd')
    @patch('modules.prcs_nspd_locality.process_geojson')
    @patch('modules.prcs_nspd_locality.Layer36281Feature')
    def test_process_nspd_locality_success(self, mock_layer_cls, mock_process_geojson, mock_nspd_cls):
        # Создание клиента и поиск результатов
        mock_nspd_instance = MagicMock()
        mock_nspd_cls.return_value = mock_nspd_instance

        # Проверка результата поиска как списка содержащего объект
        mock_feature = MagicMock()
        mock_feature.model_dump.return_value = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [37.6173, 55.7558]
            },
            "properties": {"name": "Test Locality"}
        }
        mock_nspd_instance.search_in_layer.return_value = [mock_feature]

        # Парсинг GeoJSON
        mock_process_geojson.return_value = {
            "paths": {},
            "points": {"uuid1": {"coords": [37.6173, 55.7558], "desc": "Old Desc"}},
            "metadata": []
        }

        registry_number = "77:01:0002009:2525"
        result = process_nspd_locality(registry_number)

        # Проверка, что поиск НСПД был вызван
        mock_nspd_instance.search_in_layer.assert_called_with(registry_number, mock_layer_cls)

        # Проверка, что process_geojson был вызван
        self.assertTrue(mock_process_geojson.called)

        # Проверка результатов парсинга
        self.assertEqual(result['points']['uuid1']['desc'], f"НСПД: {registry_number}")
        self.assertIn(f"НСПД: {registry_number}", result['metadata'])

    @patch('modules.prcs_nspd_locality.Nspd')
    def test_process_nspd_locality_not_found(self, mock_nspd_cls):
        mock_nspd_instance = MagicMock()
        mock_nspd_cls.return_value = mock_nspd_instance
        mock_nspd_instance.search_in_layer.return_value = []

        with self.assertRaises(ProcessingError) as cm:
            process_nspd_locality("invalid_number")

        self.assertIn("не найден", str(cm.exception))


if __name__ == '__main__':
    unittest.main()
