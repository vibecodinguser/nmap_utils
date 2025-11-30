import unittest
import tempfile
import os
import json
from modules.prcs_topojson import process_topojson
from modules.prcs_flow import ProcessingError


class TestPrcsTopojson(unittest.TestCase):

    def create_topojson_file(self, content):
        # Создание временного TopoJSON
        fd, path = tempfile.mkstemp(suffix='.topojson')

        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(json.dumps(content))
        return path

    def test_process_topojson_with_point(self):
        # Парсинг TopoJSON с точкой
        content = {
            "type": "Topology",
            "objects": {
                "example": {
                    "type": "GeometryCollection",
                    "geometries": [
                        {
                            "type": "Point",
                            "coordinates": [37.6173, 55.7558],
                            "properties": {
                                "category_t": "Test Category",
                                "title": "Test Point"
                            }
                        }
                    ]
                }
            },
            "arcs": []
        }

        topojson_path = self.create_topojson_file(content)
        try:
            result = process_topojson(topojson_path)

            self.assertIn('paths', result)
            self.assertIn('points', result)
            self.assertIn('metadata', result)
            self.assertEqual(len(result['paths']), 1)  # Должен быть один путь
            self.assertEqual(len(result['points']), 1)  # Должна быть одна точка
            self.assertIn('Test Category Test Point', result['metadata'])  # Проверка метаданных
            path_coords = list(result['paths'].values())[0]  # Проверка координат
            self.assertEqual(path_coords, [[37.6173, 55.7558]])

        finally:
            os.remove(topojson_path)

    def test_process_topojson_with_linestring(self):
        # Парсинг TopoJSON с линией
        content = {
            "type": "Topology",
            "objects": {
                "example": {
                    "type": "LineString",
                    "arcs": [0]
                }
            },
            "arcs": [
                [[37.6173, 55.7558], [37.6200, 55.7600], [37.6250, 55.7650]]
            ]
        }

        topojson_path = self.create_topojson_file(content)
        try:
            result = process_topojson(topojson_path)

            self.assertEqual(len(result['paths']), 1)
            self.assertEqual(len(result['points']), 1)
            path_coords = list(result['paths'].values())[0]  # Проверка, что путь содержит все координаты
            self.assertEqual(len(path_coords), 3)

        finally:
            os.remove(topojson_path)

    def test_process_topojson_with_polygon(self):
        # Парсинг TopoJSON с полигоном
        content = {
            "type": "Topology",
            "objects": {
                "example": {
                    "type": "Polygon",
                    "arcs": [[0]]
                }
            },
            "arcs": [
                [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
            ]
        }

        topojson_path = self.create_topojson_file(content)
        try:
            result = process_topojson(topojson_path)

            self.assertEqual(len(result['paths']), 1)
            self.assertEqual(len(result['points']), 1)
            point = list(result['points'].values())[0]  # Точка должна быть центроидом
            self.assertAlmostEqual(point['coords'][0], 0.5, places=5)
            self.assertAlmostEqual(point['coords'][1], 0.5, places=5)

        finally:
            os.remove(topojson_path)

    def test_process_topojson_empty_file(self):
        # Парсинг пустого файла TopoJSON
        content = {
            "type": "Topology",
            "objects": {},
            "arcs": []
        }

        topojson_path = self.create_topojson_file(content)
        try:
            with self.assertRaises(ProcessingError) as context:
                process_topojson(topojson_path)

            error_msg = str(context.exception.message)
            self.assertTrue('TopoJSON пуст' in error_msg or 'Ошибка чтения файла' in error_msg)

        finally:
            os.remove(topojson_path)

    def test_process_topojson_invalid_file(self):
        # Парсинг некорректного файла TopoJSON
        fd, topojson_path = tempfile.mkstemp(suffix='.topojson')

        with os.fdopen(fd, 'w') as f:
            f.write('This is not a valid JSON')

        try:
            with self.assertRaises(ProcessingError) as context:
                process_topojson(topojson_path)

            self.assertIn('Ошибка чтения файла', str(context.exception.message))

        finally:
            os.remove(topojson_path)

    def test_process_topojson_nonexistent_file(self):
        # Парсинг несуществующего файла TopoJSON
        with self.assertRaises(ProcessingError) as context:
            process_topojson('/nonexistent/file.topojson')

        self.assertIn('Ошибка чтения файла', str(context.exception.message))

    def test_process_topojson_multiple_features(self):
        # Парсинг TopoJSON с несколькими объектами
        content = {
            "type": "Topology",
            "objects": {
                "collection": {
                    "type": "GeometryCollection",
                    "geometries": [
                        {
                            "type": "Point",
                            "coordinates": [37.6173, 55.7558],
                            "properties": {"title": "Point 1"}
                        },
                        {
                            "type": "Point",
                            "coordinates": [37.6200, 55.7600],
                            "properties": {"title": "Point 2"}
                        }
                    ]
                }
            },
            "arcs": []
        }

        topojson_path = self.create_topojson_file(content)
        try:
            result = process_topojson(topojson_path)

            self.assertEqual(len(result['paths']), 2)
            self.assertEqual(len(result['points']), 2)
            self.assertIn('Point 1', result['metadata'])
            self.assertIn('Point 2', result['metadata'])

        finally:
            os.remove(topojson_path)


if __name__ == '__main__':
    unittest.main()
