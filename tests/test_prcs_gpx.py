import unittest
import tempfile
import os
from modules.prcs_gpx import process_gpx
from modules.prcs_flow import ProcessingError


class TestPrcsGpx(unittest.TestCase):

    def create_gpx_file(self, content):
        # Создание временного файла GPX
        fd, path = tempfile.mkstemp(suffix='.gpx')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_process_gpx_with_track(self):
        # Парсинг GPX с треком
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test">
    <trk>
        <name>Test Track</name>
        <trkseg>
            <trkpt lat="55.7558" lon="37.6173"></trkpt>
            <trkpt lat="55.7559" lon="37.6174"></trkpt>
            <trkpt lat="55.7560" lon="37.6175"></trkpt>
        </trkseg>
    </trk>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)

            self.assertIn('paths', result)
            self.assertIn('points', result)
            self.assertIn('metadata', result)
            self.assertEqual(len(result['paths']), 1)  # Должен быть один трек
            self.assertEqual(len(result['points']), 1)  # Должна быть одна точка (начало трека)
            self.assertIn('Test Track', result['metadata'])  # Метаданные должны содержать название трека
            path_coords = list(result['paths'].values())[0]  # Проверяем формат координат [lon, lat]
            self.assertEqual(len(path_coords), 3)
            self.assertEqual(path_coords[0], [37.6173, 55.7558])

        finally:
            os.remove(gpx_file)

    def test_process_gpx_with_waypoints(self):
        # Парсинг GPX с точкой
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1">
    <wpt lat="55.7558" lon="37.6173">
        <name>Waypoint 1</name>
    </wpt>
    <wpt lat="55.7600" lon="37.6200">
        <name>Waypoint 2</name>
    </wpt>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)

            self.assertEqual(len(result['paths']), 0)  # Должен быть один трек
            self.assertEqual(len(result['points']), 2)  # Должно быть две точки
            point_coords = [p['coords'] for p in result['points'].values()]  # Проверяем координаты точек
            self.assertIn([37.6173, 55.7558], point_coords)
            self.assertIn([37.6200, 55.7600], point_coords)
            point_descs = [p['desc'] for p in result['points'].values()]  # Проверяем названия точек
            self.assertIn('Waypoint 1', point_descs)
            self.assertIn('Waypoint 2', point_descs)

        finally:
            os.remove(gpx_file)

    def test_process_gpx_with_namespace(self):
        # Парсинг GPX с XML namespace
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">
    <trk>
        <name>Namespaced Track</name>
        <trkseg>
            <trkpt lat="55.7558" lon="37.6173"></trkpt>
        </trkseg>
    </trk>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)

            self.assertEqual(len(result['paths']), 1)
            self.assertIn('Namespaced Track', result['metadata'])

        finally:
            os.remove(gpx_file)

    def test_process_gpx_multiple_segments(self):
        # Парсинг GPX с несколькими треками
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1">
    <trk>
        <name>Multi-segment Track</name>
        <trkseg>
            <trkpt lat="55.7558" lon="37.6173"></trkpt>
            <trkpt lat="55.7559" lon="37.6174"></trkpt>
        </trkseg>
        <trkseg>
            <trkpt lat="55.7600" lon="37.6200"></trkpt>
            <trkpt lat="55.7601" lon="37.6201"></trkpt>
        </trkseg>
    </trk>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)

            self.assertEqual(len(result['paths']), 2)  # Должно быть два трека
            self.assertEqual(len(result['points']), 2)  # Должно быть две точки

        finally:
            os.remove(gpx_file)

    def test_process_gpx_empty_track(self):
        # Парсинг GPX с пустым треком
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1">
    <trk>
        <name>Empty Track</name>
        <trkseg>
        </trkseg>
    </trk>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)

            self.assertEqual(len(result['paths']), 0)  # Должен быть пустой трек
            self.assertIn('Empty Track', result['metadata'])  # Метаданные должны содержать название трека

        finally:
            os.remove(gpx_file)

    def test_process_gpx_invalid_coordinates(self):
        # Парсинг GPX с невалидными координатами
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1">
    <trk>
        <trkseg>
            <trkpt lat="invalid" lon="37.6173"></trkpt>
            <trkpt lat="55.7559" lon="37.6174"></trkpt>
        </trkseg>
    </trk>
    <wpt lat="55.7558" lon="invalid">
        <name>Invalid Waypoint</name>
    </wpt>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)

            path_coords = list(result['paths'].values())[0]  # Должен быть один трек
            self.assertEqual(len(path_coords), 1)  # Должна быть одна точка
            self.assertEqual(path_coords[0], [37.6174, 55.7559])
            self.assertEqual(len(result['points']), 1)  # Невалидный waypoint пропущен, точка трека должна быть в points

        finally:
            os.remove(gpx_file)

    def test_process_gpx_waypoint_without_name(self):
        # Парсинг GPX точки без имени
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1">
    <wpt lat="55.7558" lon="37.6173">
    </wpt>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)
            point = list(result['points'].values())[0]  # Waypoint без имени должен использовать имя файла как описание
            self.assertTrue(point['desc'].endswith('.gpx'))

        finally:
            os.remove(gpx_file)

    def test_process_gpx_track_without_name(self):
        # Парсинг GPX трека без имени
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1">
    <trk>
        <trkseg>
            <trkpt lat="55.7558" lon="37.6173"></trkpt>
        </trkseg>
    </trk>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)

            self.assertEqual(len(result['metadata']), 0)  # Metadata должна быть пустой (нет названия трека)
            point = list(result['points'].values())[0]  # Point description должна использовать имя файла
            self.assertTrue(point['desc'].endswith('.gpx'))

        finally:
            os.remove(gpx_file)

    def test_process_gpx_invalid_xml(self):
        # Парсинг GPX с невалидным XML
        gpx_content = ''''''
        gpx_file = self.create_gpx_file(gpx_content)
        try:
            with self.assertRaises(ProcessingError) as context:
                process_gpx(gpx_file)

            self.assertIn('Ошибка чтения файла', str(context.exception.message))

        finally:
            os.remove(gpx_file)

    def test_process_gpx_nonexistent_file(self):
        # Парсинг несуществующего GPX файла
        with self.assertRaises(ProcessingError) as context:
            process_gpx('/nonexistent/file.gpx')

        self.assertIn('Ошибка чтения файла', str(context.exception.message))

    def test_process_gpx_duplicate_track_names(self):
        # Парсинг дублирующихся названий треков
        gpx_content = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1">
    <trk>
        <name>Same Name</name>
        <trkseg>
            <trkpt lat="55.7558" lon="37.6173"></trkpt>
        </trkseg>
    </trk>
    <trk>
        <name>Same Name</name>
        <trkseg>
            <trkpt lat="55.7600" lon="37.6200"></trkpt>
        </trkseg>
    </trk>
</gpx>'''

        gpx_file = self.create_gpx_file(gpx_content)
        try:
            result = process_gpx(gpx_file)

            self.assertEqual(len(result['metadata']), 1)  # Должна быть только одна запись в metadata (без дубликатов)
            self.assertEqual(result['metadata'][0], 'Same Name')

        finally:
            os.remove(gpx_file)


if __name__ == '__main__':
    unittest.main()
