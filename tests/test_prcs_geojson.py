import unittest
import tempfile
import os
import json
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiPolygon, MultiLineString
import geopandas as gpd
from modules.prcs_geojson import process_geojson
from modules.prcs_flow import ProcessingError


class TestPrcsGeojson(unittest.TestCase):

    def create_geojson_file(self, geometries, attributes=None):
        # Создание временного файла GeoJSON
        if attributes is None:
            attributes = [{}] * len(geometries)
        gdf = gpd.GeoDataFrame(attributes, geometry=geometries)
        fd, path = tempfile.mkstemp(suffix='.geojson')
        os.close(fd)
        gdf.to_file(path, driver='GeoJSON')
        return path

    def test_process_geojson_with_point(self):
        # Парсинг GeoJSON с точкой
        geometries = [Point(37.6173, 55.7558)]
        attributes = [{'category_t': 'Test Category', 'title': 'Test Point'}]
        geojson_path = self.create_geojson_file(geometries, attributes)
        try:
            result = process_geojson(geojson_path)

            self.assertIn('paths', result)
            self.assertIn('points', result)
            self.assertIn('metadata', result)
            self.assertEqual(len(result['paths']), 1)  # Должен быть один путь
            self.assertEqual(len(result['points']), 1)  # Должна быть одна точка
            self.assertIn('Test Category Test Point', result['metadata'])  # Проверка метаданных
            path_coords = list(result['paths'].values())[0]  # Проверка координат
            self.assertEqual(path_coords, [[37.6173, 55.7558]])
            point = list(result['points'].values())[0]  # Проверка описания (должно быть имя файла)
            self.assertTrue(point['desc'].endswith('.geojson'))

        finally:
            os.remove(geojson_path)

    def test_process_geojson_with_linestring(self):
        # Парсинг GeoJSON с линией
        geometries = [LineString([(37.6173, 55.7558), (37.6200, 55.7600), (37.6250, 55.7650)])]
        geojson_path = self.create_geojson_file(geometries)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['paths']), 1)
            self.assertEqual(len(result['points']), 1)
            path_coords = list(result['paths'].values())[0]  # Проверка, что путь содержит все координаты
            self.assertEqual(len(path_coords), 3)
            point = list(result['points'].values())[0]  # Точка должна быть первой координатой
            self.assertEqual(point['coords'], [37.6173, 55.7558])

        finally:
            os.remove(geojson_path)

    def test_process_geojson_with_polygon(self):
        # Парсинг GeoJSON с полигоном
        geometries = [Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])]
        geojson_path = self.create_geojson_file(geometries)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['paths']), 1)
            self.assertEqual(len(result['points']), 1)
            point = list(result['points'].values())[0]  # Точка должна быть центроидом полигона
            self.assertAlmostEqual(point['coords'][0], 0.5, places=5)
            self.assertAlmostEqual(point['coords'][1], 0.5, places=5)

        finally:
            os.remove(geojson_path)

    def test_process_geojson_with_multipoint(self):
        # Парсинг GeoJSON с мультиточкой
        geometries = [MultiPoint([(37.6173, 55.7558), (37.6200, 55.7600)])]
        geojson_path = self.create_geojson_file(geometries)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два пути (один для каждой точки)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(geojson_path)

    def test_process_geojson_with_multipolygon(self):
        # Парсинг GeoJSON с мультиполигоном
        poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        poly2 = Polygon([(2, 2), (3, 2), (3, 3), (2, 3), (2, 2)])
        geometries = [MultiPolygon([poly1, poly2])]
        geojson_path = self.create_geojson_file(geometries)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два пути (один для каждого полигона)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(geojson_path)

    def test_process_geojson_with_multilinestring(self):
        # Парсинг GeoJSON с мультилинией
        line1 = LineString([(0, 0), (1, 1)])
        line2 = LineString([(2, 2), (3, 3)])
        geometries = [MultiLineString([line1, line2])]
        geojson_path = self.create_geojson_file(geometries)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два пути
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(geojson_path)

    def test_process_geojson_empty_file(self):
        # Парсинг пустого GeoJSON
        geometries = []
        geojson_path = self.create_geojson_file(geometries)
        try:
            with self.assertRaises(ProcessingError) as context:
                process_geojson(geojson_path)

            self.assertIn('GeoJSON пуст', str(context.exception.message))

        finally:
            os.remove(geojson_path)

    def test_process_geojson_invalid_file(self):
        # Парсинг некорректного GeoJSON
        fd, geojson_path = tempfile.mkstemp(suffix='.geojson')
        with os.fdopen(fd, 'w') as f:
            f.write('This is not a valid GeoJSON file')
        try:
            with self.assertRaises(ProcessingError) as context:
                process_geojson(geojson_path)

            self.assertIn('Ошибка чтения файла', str(context.exception.message))

        finally:
            os.remove(geojson_path)

    def test_process_geojson_nonexistent_file(self):
        # Парсинг несуществующего файла
        with self.assertRaises(ProcessingError) as context:
            process_geojson('/nonexistent/file.geojson')

        self.assertIn('Ошибка чтения файла', str(context.exception.message))

    def test_process_geojson_polygon_with_hole(self):
        # Парсинг полигона с дыркой
        exterior = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]
        interior = [(1, 1), (3, 1), (3, 3), (1, 3), (1, 1)]
        geometries = [Polygon(exterior, [interior])]
        geojson_path = self.create_geojson_file(geometries)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два пути: внешний и внутренний

        finally:
            os.remove(geojson_path)

    def test_process_geojson_skip_empty_geometry(self):
        # Парсинг с пропуском пустых геометрий
        geometries = [
            Point(37.6173, 55.7558),
            Point(),
            Point(37.6200, 55.7600)
        ]

        geojson_path = self.create_geojson_file(geometries)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть обработано 2 точки
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(geojson_path)

    def test_process_geojson_multiple_features(self):
        # Парсинг GeoJSON с несколькими объектами
        geometries = [
            Point(37.6173, 55.7558),
            Point(37.6200, 55.7600)
        ]
        attributes = [
            {'category_t': 'Cat1', 'title': 'Title1'},
            {'category_t': 'Cat2', 'title': 'Title2'}
        ]

        geojson_path = self.create_geojson_file(geometries, attributes)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['paths']), 2)
            self.assertEqual(len(result['points']), 2)
            self.assertIn('Cat1 Title1', result['metadata'])
            self.assertIn('Cat2 Title2', result['metadata'])

        finally:
            os.remove(geojson_path)

    def test_process_geojson_duplicate_metadata(self):
        # Парсинг с пропуском дублей метаданных
        geometries = [
            Point(37.6173, 55.7558),
            Point(37.6200, 55.7600)
        ]
        attributes = [
            {'category_t': 'Cat1', 'title': 'Title1'},
            {'category_t': 'Cat1', 'title': 'Title1'}
        ]

        geojson_path = self.create_geojson_file(geometries, attributes)
        try:
            result = process_geojson(geojson_path)

            self.assertEqual(len(result['metadata']), 1)
            self.assertIn('Cat1 Title1', result['metadata'])

        finally:
            os.remove(geojson_path)


if __name__ == '__main__':
    unittest.main()
