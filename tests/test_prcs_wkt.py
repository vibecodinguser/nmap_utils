import unittest
import tempfile
import os
from modules.prcs_wkt import process_wkt
from modules.prcs_flow import ProcessingError


class TestPrcsWkt(unittest.TestCase):

    def create_wkt_file(self, content):
        # Создание временного WKT файла
        fd, path = tempfile.mkstemp(suffix='.wkt')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_process_wkt_with_point(self):
        # Парсинг WKT с точкой
        content = "POINT (37.6173 55.7558)"

        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertIn('paths', result)
            self.assertIn('points', result)
            self.assertIn('metadata', result)
            self.assertEqual(len(result['paths']), 1)  # Должен быть один путь
            self.assertEqual(len(result['points']), 1)  # Должна быть одна точка
            path_coords = list(result['paths'].values())[0]  # Проверка координат
            self.assertEqual(path_coords, [[37.6173, 55.7558]])
            point = list(result['points'].values())[0]  # Проверка описания (имя файла)
            self.assertTrue(point['desc'].endswith('.wkt'))

        finally:
            os.remove(wkt_path)

    def test_process_wkt_with_linestring(self):
        # Парсинг WKT с линией
        content = "LINESTRING (37.6173 55.7558, 37.6200 55.7600, 37.6250 55.7650)"

        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 1)
            self.assertEqual(len(result['points']), 1)
            path_coords = list(result['paths'].values())[0]  # Проверка координат
            self.assertEqual(len(path_coords), 3)

        finally:
            os.remove(wkt_path)

    def test_process_wkt_with_polygon(self):
        # Парсинг WKT с полигоном
        content = "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))"
        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 1)
            self.assertEqual(len(result['points']), 1)
            point = list(result['points'].values())[0]  # Точка должна быть центроидом
            self.assertAlmostEqual(point['coords'][0], 0.5, places=5)
            self.assertAlmostEqual(point['coords'][1], 0.5, places=5)

        finally:
            os.remove(wkt_path)

    def test_process_wkt_with_multipoint(self):
        # Парсинг WKT с множеством точек
        content = "MULTIPOINT ((37.6173 55.7558), (37.6200 55.7600))"
        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 2)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(wkt_path)

    def test_process_wkt_with_multipolygon(self):
        # Парсинг WKT с множеством полигонов
        content = "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 1, 0 0)), ((2 2, 3 2, 3 3, 2 3, 2 2)))"
        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 2)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(wkt_path)

    def test_process_wkt_with_multilinestring(self):
        # Парсинг WKT с множеством линий
        content = "MULTILINESTRING ((0 0, 1 1), (2 2, 3 3))"
        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 2)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(wkt_path)

    def test_process_wkt_with_geometrycollection(self):
        # Парсинг WKT с геометрией
        content = "GEOMETRYCOLLECTION (POINT (37.6173 55.7558), LINESTRING (0 0, 1 1))"
        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 2)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(wkt_path)

    def test_process_wkt_multiple_lines(self):
        # Парсинг WKT с несколькими строками
        content = """POINT (37.6173 55.7558)
POINT (37.6200 55.7600)"""
        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 2)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(wkt_path)

    def test_process_wkt_comments_and_empty_lines(self):
        # Парсинг WKT с комментариями и пустыми строками
        content = """# This is a comment

POINT (37.6173 55.7558)

# Another comment"""
        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 1)

        finally:
            os.remove(wkt_path)

    def test_process_wkt_empty_file(self):
        # Парсинг пустого
        content = ""
        wkt_path = self.create_wkt_file(content)
        try:
            with self.assertRaises(ProcessingError) as context:
                process_wkt(wkt_path)

            self.assertIn('WKT пуст', str(context.exception.message))

        finally:
            os.remove(wkt_path)

    def test_process_wkt_invalid_lines(self):
        # Парсинг WKT с некорректными строками
        content = """POINT (37.6173 55.7558)
INVALID WKT
POINT (37.6200 55.7600)"""
        wkt_path = self.create_wkt_file(content)
        try:
            result = process_wkt(wkt_path)

            self.assertEqual(len(result['paths']), 2)  # Обработка допустимых строк и пропуск недопустимых

        finally:
            os.remove(wkt_path)

    def test_process_wkt_all_invalid(self):
        # Парсинг WKT с некорректными строками
        content = "INVALID WKT"
        wkt_path = self.create_wkt_file(content)
        try:
            with self.assertRaises(ProcessingError) as context:
                process_wkt(wkt_path)

            self.assertIn('Геометрия WKT файла не валидна', str(context.exception.message))

        finally:
            os.remove(wkt_path)

    def test_process_wkt_nonexistent_file(self):
        # Парсинг несуществующего файла
        with self.assertRaises(ProcessingError) as context:
            process_wkt('/nonexistent/file.wkt')

        self.assertIn('Ошибка чтения файла', str(context.exception.message))


if __name__ == '__main__':
    unittest.main()
