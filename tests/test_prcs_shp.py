import unittest
import tempfile
import os
import zipfile
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiPolygon, MultiLineString
import geopandas as gpd
from modules.prcs_shp import process_zip
from modules.prcs_flow import ProcessingError


class TestPrcsShp(unittest.TestCase):

    def create_shapefile_zip(self, geometries, attributes=None, crs='EPSG:4326'):
        # Создание временного шейп-файла запакованного в ZIP
        temp_dir = tempfile.mkdtemp()
        shp_path = os.path.join(temp_dir, 'test.shp')
        if attributes is None:
            attributes = [{}] * len(geometries)

        gdf = gpd.GeoDataFrame(attributes, geometry=geometries, crs=crs)
        gdf.to_file(shp_path)

        fd, zip_path = tempfile.mkstemp(suffix='.zip')  # Создание ZIP архива
        os.close(fd)

        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg']:
                file_path = shp_path.replace('.shp', ext)
                if os.path.exists(file_path):
                    zipf.write(file_path, os.path.basename(file_path))

        for ext in ['.shp', '.shx', '.dbf', '.prj', '.cpg']:  # Очистка временной директории
            file_path = shp_path.replace('.shp', ext)
            if os.path.exists(file_path):
                os.remove(file_path)
        os.rmdir(temp_dir)

        return zip_path

    def test_process_zip_with_point(self):
        # Парсинг шейп-файла с точкой
        geometries = [Point(37.6173, 55.7558)]
        attributes = [{'category_t': 'Test Category', 'title': 'Test Point'}]

        zip_path = self.create_shapefile_zip(geometries, attributes)
        try:
            result = process_zip(zip_path)

            self.assertIn('paths', result)
            self.assertIn('points', result)
            self.assertIn('metadata', result)
            self.assertEqual(len(result['paths']), 1)  # Должен быть один трек
            self.assertEqual(len(result['points']), 1)  # Должна быть одна точка
            self.assertIn('Test Category Test Point', result['metadata'])  # Проверка метаданных
            path_coords = list(result['paths'].values())[0]  # Проверка координат
            self.assertEqual(path_coords, [[37.6173, 55.7558]])

        finally:
            os.remove(zip_path)

    def test_process_zip_with_linestring(self):
        # Парсинг шейп-файла с линией
        geometries = [LineString([(37.6173, 55.7558), (37.6200, 55.7600), (37.6250, 55.7650)])]

        zip_path = self.create_shapefile_zip(geometries)
        try:
            result = process_zip(zip_path)

            self.assertEqual(len(result['paths']), 1)
            self.assertEqual(len(result['points']), 1)
            path_coords = list(result['paths'].values())[0]  # Проверка, что трек содержит все координаты
            self.assertEqual(len(path_coords), 3)
            point = list(result['points'].values())[0]  # Точка должна быть первой координатой
            self.assertEqual(point['coords'], [37.6173, 55.7558])

        finally:
            os.remove(zip_path)

    def test_process_zip_with_polygon(self):
        # Парсинг шейп-файла с полигоном
        geometries = [Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])]

        zip_path = self.create_shapefile_zip(geometries)
        try:
            result = process_zip(zip_path)

            self.assertEqual(len(result['paths']), 1)
            self.assertEqual(len(result['points']), 1)
            point = list(result['points'].values())[0]  # Точка должна быть центроидом полигона
            self.assertAlmostEqual(point['coords'][0], 0.5, places=5)
            self.assertAlmostEqual(point['coords'][1], 0.5, places=5)

        finally:
            os.remove(zip_path)

    def test_process_zip_with_multipoint(self):
        # Парсинг шейп-файла с мультиточкой
        geometries = [MultiPoint([(37.6173, 55.7558), (37.6200, 55.7600)])]

        zip_path = self.create_shapefile_zip(geometries)
        try:
            result = process_zip(zip_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два трека (один для каждой точки)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(zip_path)

    def test_process_zip_with_multipolygon(self):
        # Парсинг шейп-файла с мультиполигоном
        poly1 = Polygon([(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)])
        poly2 = Polygon([(2, 2), (3, 2), (3, 3), (2, 3), (2, 2)])
        geometries = [MultiPolygon([poly1, poly2])]

        zip_path = self.create_shapefile_zip(geometries)
        try:
            result = process_zip(zip_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два трека (один для каждого полигона)
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(zip_path)

    def test_process_zip_with_multilinestring(self):
        # Парсинг шейп-файла с мультилинией
        line1 = LineString([(0, 0), (1, 1)])
        line2 = LineString([(2, 2), (3, 3)])
        geometries = [MultiLineString([line1, line2])]

        zip_path = self.create_shapefile_zip(geometries)
        try:
            result = process_zip(zip_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два трека
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(zip_path)

    def test_process_zip_with_attributes(self):
        # Парсинг шейп-файла с атрибутами
        geometries = [Point(37.6173, 55.7558)]
        attributes = [{
            'nid': 12345,
            'status_tit': 'Федеральный',
            'sig': 'federal',
            'category_t': 'Заповедник',
            'title': 'Тестовый заповедник'
        }]

        zip_path = self.create_shapefile_zip(geometries, attributes)
        try:
            result = process_zip(zip_path)

            point = list(result['points'].values())[0]  # Проверка, что описание содержит все поля
            desc = point['desc']

            self.assertIn('Особо охраняемые природные территории России', desc)
            self.assertIn('Идентификатор ООПТ - 12345', desc)
            self.assertIn('Статус - Федеральный', desc)
            self.assertIn('Значение - федеральный', desc)
            self.assertIn('Категория - Заповедник', desc)
            self.assertIn('Название - Тестовый заповедник', desc)
            self.assertIn('Заповедник Тестовый заповедник', result['metadata'])  # Проверка метаданных

        finally:
            os.remove(zip_path)

    def test_process_zip_sig_translation(self):
        # Парсинг шейп-файла со значениями для замены
        geometries = [Point(0, 0), Point(1, 1)]
        attributes = [
            {'sig': 'regional', 'category_t': 'Test1'},
            {'sig': 'federal', 'category_t': 'Test2'}
        ]

        zip_path = self.create_shapefile_zip(geometries, attributes)
        try:
            result = process_zip(zip_path)
            points = list(result['points'].values())

            self.assertIn('региональный', points[0]['desc'])
            self.assertIn('федеральный', points[1]['desc'])

        finally:
            os.remove(zip_path)

    def test_process_zip_nid_formatting(self):
        # Парсинг шейп-файла со значениями 'nid' для форматирования
        geometries = [Point(0, 0)]
        attributes = [{'nid': 12345.0, 'category_t': 'Test'}]

        zip_path = self.create_shapefile_zip(geometries, attributes)
        try:
            result = process_zip(zip_path)
            point = list(result['points'].values())[0]
            desc = point['desc']

            self.assertIn('Идентификатор ООПТ - 12345', desc)  # Проверка, что идентификатор ООПТ целое число
            self.assertNotIn('12345.0', desc)

        finally:
            os.remove(zip_path)

    def test_process_zip_empty_attributes(self):
        # Парсинг шейп-файла без атрибутов
        geometries = [Point(37.6173, 55.7558)]

        zip_path = self.create_shapefile_zip(geometries)
        try:
            result = process_zip(zip_path)
            point = list(result['points'].values())[0]  # Описание должно быть именем файла, если нет атрибутов

            self.assertTrue(point['desc'].endswith('.zip'))

        finally:
            os.remove(zip_path)

    def test_process_zip_multiple_features(self):
        # Парсинг шейп-файла с несколькими геометриями
        geometries = [
            Point(37.6173, 55.7558),
            Point(37.6200, 55.7600),
            Point(37.6250, 55.7650)
        ]
        attributes = [
            {'category_t': 'Cat1', 'title': 'Title1'},
            {'category_t': 'Cat2', 'title': 'Title2'},
            {'category_t': 'Cat1', 'title': 'Title1'}
        ]

        zip_path = self.create_shapefile_zip(geometries, attributes)
        try:
            result = process_zip(zip_path)

            self.assertEqual(len(result['paths']), 3)
            self.assertEqual(len(result['points']), 3)
            self.assertEqual(len(result['metadata']), 2)  # Метаданные не должны содержать дубликаты
            self.assertIn('Cat1 Title1', result['metadata'])
            self.assertIn('Cat2 Title2', result['metadata'])

        finally:
            os.remove(zip_path)

    def test_process_zip_empty_shapefile(self):
        # Парсинг пустого шейп-файла
        geometries = []

        zip_path = self.create_shapefile_zip(geometries)
        try:
            with self.assertRaises(ProcessingError) as context:
                process_zip(zip_path)

            self.assertIn('Shapefile пуст', str(context.exception.message))

        finally:
            os.remove(zip_path)

    def test_process_zip_no_crs(self):
        # Парсинг шейп-файла без CRS
        geometries = [Point(37.6173, 55.7558)]

        zip_path = self.create_shapefile_zip(geometries, crs=None)
        try:
            with self.assertRaises(ProcessingError) as context:
                process_zip(zip_path)

            self.assertIn('Shapefile не имеет CRS', str(context.exception.message))

        finally:
            os.remove(zip_path)

    def test_process_zip_invalid_file(self):
        # Парсинг невалидного ZIP-файла
        fd, zip_path = tempfile.mkstemp(suffix='.zip')

        with os.fdopen(fd, 'w') as f:
            f.write('This is not a valid ZIP file')

        try:
            with self.assertRaises(ProcessingError) as context:
                process_zip(zip_path)

            self.assertIn('Ошибка чтения ZIP-файла', str(context.exception.message))

        finally:
            os.remove(zip_path)

    def test_process_zip_nonexistent_file(self):
        # Парсинг несуществующего файла
        with self.assertRaises(ProcessingError) as context:
            process_zip('/nonexistent/file.zip')

        self.assertIn('Ошибка чтения ZIP-файла', str(context.exception.message))

    def test_process_zip_polygon_with_hole(self):
        # Парсинг полигона с дыркой
        exterior = [(0, 0), (4, 0), (4, 4), (0, 4), (0, 0)]
        interior = [(1, 1), (3, 1), (3, 3), (1, 3), (1, 1)]
        geometries = [Polygon(exterior, [interior])]
        zip_path = self.create_shapefile_zip(geometries)
        try:
            result = process_zip(zip_path)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два контура: внешний и внутренний

        finally:
            os.remove(zip_path)

    def test_process_zip_skip_empty_geometry(self):
        # Парсинг пустых геометрий
        geometries = [
            Point(37.6173, 55.7558),
            Point(),  # Empty point
            Point(37.6200, 55.7600)
        ]

        zip_path = self.create_shapefile_zip(geometries)
        try:
            result = process_zip(zip_path)

            self.assertEqual(len(result['paths']), 2)  # Должно обработать только 2 валидных точки
            self.assertEqual(len(result['points']), 2)

        finally:
            os.remove(zip_path)


if __name__ == '__main__':
    unittest.main()
