import unittest
import tempfile
import os
import zipfile
from modules.prcs_kml import process_kml
from modules.prcs_flow import ProcessingError


class TestPrcsKml(unittest.TestCase):

    def create_kml_file(self, content):
        # Создание временного KML
        fd, path = tempfile.mkstemp(suffix='.kml')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def create_kmz_file(self, kml_content):
        # Создание временного KMZ
        kml_fd, kml_path = tempfile.mkstemp(suffix='.kml')

        with os.fdopen(kml_fd, 'w', encoding='utf-8') as f:
            f.write(kml_content)
        fd, kmz_path = tempfile.mkstemp(suffix='.kmz')
        os.close(fd)

        with zipfile.ZipFile(kmz_path, 'w') as zipf:
            zipf.write(kml_path, 'doc.kml')

        os.remove(kml_path)
        return kmz_path

    def test_process_kml_with_point(self):
        # Парсинг KML файла с точкой
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <name>Test Point</name>
            <Point>
                <coordinates>37.6173,55.7558,0</coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            self.assertIn('paths', result)
            self.assertIn('points', result)
            self.assertIn('metadata', result)
            self.assertEqual(len(result['paths']), 0)  # Должен быть пустой трек
            self.assertEqual(len(result['points']), 1)  # Должна быть одна точка
            self.assertIn('Test Point', result['metadata'])  # Проверка метаданных
            point = list(result['points'].values())[0]  # Проверка координат
            self.assertEqual(point['coords'], [37.6173, 55.7558])
            self.assertEqual(point['desc'], 'Test Point')

        finally:
            os.remove(kml_file)

    def test_process_kml_with_linestring(self):
        # Парсинг KML файла с линией
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <name>Test Line</name>
            <LineString>
                <coordinates>
                    37.6173,55.7558,0
                    37.6200,55.7600,0
                    37.6250,55.7650,0
                </coordinates>
            </LineString>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            self.assertEqual(len(result['paths']), 1)  # Должен быть один трек
            self.assertEqual(len(result['points']), 1)  # Должна быть одна точка (начало линии)
            path = list(result['paths'].values())[0]  # Проверка координат трека
            self.assertEqual(len(path), 3)
            self.assertEqual(path[0], [37.6173, 55.7558])
            self.assertEqual(path[2], [37.6250, 55.7650])
            self.assertIn('Test Line', result['metadata'])  # Проверка метаданных

        finally:
            os.remove(kml_file)

    def test_process_kml_without_namespace(self):
        # Парсинг KML файла без пространства имен
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml>
    <Document>
        <Placemark>
            <name>No Namespace</name>
            <Point>
                <coordinates>37.6173,55.7558</coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            self.assertEqual(len(result['points']), 1)
            self.assertIn('No Namespace', result['metadata'])

        finally:
            os.remove(kml_file)

    def test_process_kmz_file(self):
        # Парсинг KMZ файла (сжатый KML)
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <name>KMZ Test</name>
            <Point>
                <coordinates>37.6173,55.7558</coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kmz_file = self.create_kmz_file(kml_content)
        try:
            result = process_kml(kmz_file)

            self.assertEqual(len(result['points']), 1)
            self.assertIn('KMZ Test', result['metadata'])

        finally:
            os.remove(kmz_file)

    def test_process_kml_multiple_placemarks(self):
        # Парсинг KML файла с несколькими placemarks
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <name>Point 1</name>
            <Point>
                <coordinates>37.6173,55.7558</coordinates>
            </Point>
        </Placemark>
        <Placemark>
            <name>Point 2</name>
            <Point>
                <coordinates>37.6200,55.7600</coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            self.assertEqual(len(result['points']), 2)
            self.assertEqual(len(result['metadata']), 2)
            self.assertIn('Point 1', result['metadata'])
            self.assertIn('Point 2', result['metadata'])

        finally:
            os.remove(kml_file)

    def test_process_kml_placemark_without_name(self):
        # Парсинг KML файла с placemark без имени
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <Point>
                <coordinates>37.6173,55.7558</coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            point = list(result['points'].values())[0]  # Должна быть точка с описанием, соответствующим имени файла
            self.assertTrue(point['desc'].endswith('.kml'))
            self.assertEqual(len(result['metadata']), 0)  # Метаданные не должны быть пустыми

        finally:
            os.remove(kml_file)

    def test_process_kml_duplicate_names(self):
        # Парсинг KML файла с дублирующимися именами которые не должны добавляться в метаданные
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <name>Same Name</name>
            <Point>
                <coordinates>37.6173,55.7558</coordinates>
            </Point>
        </Placemark>
        <Placemark>
            <name>Same Name</name>
            <Point>
                <coordinates>37.6200,55.7600</coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            self.assertEqual(len(result['points']), 2)  # Должны быть две точки
            self.assertEqual(len(result['metadata']), 1)  # Но только одна запись в метаданных
            self.assertEqual(result['metadata'][0], 'Same Name')

        finally:
            os.remove(kml_file)

    def test_process_kml_invalid_coordinates(self):
        # Парсинг KML с недействительными координатами
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <LineString>
                <coordinates>
                    invalid,coordinates
                    37.6200,55.7600
                    37.6250,55.7650
                </coordinates>
            </LineString>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            path = list(result['paths'].values())[0]  # Должен быть один трек
            self.assertEqual(len(path), 2)  # Только 2 валидные точки

        finally:
            os.remove(kml_file)

    def test_process_kml_coordinates_without_altitude(self):
        #  координатами без высоты (2D)
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <Point>
                <coordinates>37.6173,55.7558</coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            point = list(result['points'].values())[0]
            self.assertEqual(point['coords'], [37.6173, 55.7558])

        finally:
            os.remove(kml_file)

    def test_process_kml_empty_coordinates(self):
        # Парсинг KML с пустыми координатами
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <Point>
                <coordinates></coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            self.assertEqual(len(result['points']), 0)  # Должна быть пустая точка

        finally:
            os.remove(kml_file)

    def test_process_kml_invalid_xml(self):
        # Тест невалидного XML файла
        kml_content = '''Не валидная структура XML для теста'''

        kml_file = self.create_kml_file(kml_content)
        try:
            with self.assertRaises(ProcessingError) as context:
                process_kml(kml_file)

            self.assertIn('Ошибка чтения файла', str(context.exception.message))

        finally:
            os.remove(kml_file)

    def test_process_kmz_without_kml(self):
        # Парсинг обработки KMZ файла без KML внутри
        fd, kmz_path = tempfile.mkstemp(suffix='.kmz')
        os.close(fd)

        with zipfile.ZipFile(kmz_path, 'w') as zipf:  # Создание пустого ZIP
            zipf.writestr('readme.txt', 'No KML here')

        try:
            with self.assertRaises(ProcessingError) as context:
                process_kml(kmz_path)

            self.assertIn('В KMZ-архиве отсутствует KML-файл', str(context.exception.message))

        finally:
            os.remove(kmz_path)

    def test_process_kml_nonexistent_file(self):
        # Парсинг несуществующего файла
        with self.assertRaises(ProcessingError) as context:
            process_kml('/nonexistent/file.kml')

        self.assertIn('Ошибка чтения файла', str(context.exception.message))

    def test_process_kml_mixed_geometries(self):
        # Парсинг KML как с точками, так и с линиями
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <name>Point Feature</name>
            <Point>
                <coordinates>37.6173,55.7558</coordinates>
            </Point>
        </Placemark>
        <Placemark>
            <name>Line Feature</name>
            <LineString>
                <coordinates>
                    37.6200,55.7600
                    37.6250,55.7650
                </coordinates>
            </LineString>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            self.assertEqual(len(result['paths']), 1)  # Должна быть одна линия
            self.assertEqual(len(result['points']), 2)  # Должны быть две точки (одна отдельная, другая из начала линии)
            self.assertEqual(len(result['metadata']), 2)  # Должны быть два имени в метаданных
            self.assertIn('Point Feature', result['metadata'])
            self.assertIn('Line Feature', result['metadata'])

        finally:
            os.remove(kml_file)

    def test_process_kml_whitespace_in_coordinates(self):
        # Парсинг KML файла где координаты с различными пробелами
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <LineString>
                <coordinates>
                    37.6173,55.7558
                    
                    37.6200,55.7600
                    
                    37.6250,55.7650
                </coordinates>
            </LineString>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            path = list(result['paths'].values())[0]
            self.assertEqual(len(path), 3)

        finally:
            os.remove(kml_file)

    def test_process_kml_point_uses_placemark_name(self):
        # Парсинг KML файла где используется имя placemark, если оно доступно
        kml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <Placemark>
            <name>Custom Point Name</name>
            <Point>
                <coordinates>37.6173,55.7558</coordinates>
            </Point>
        </Placemark>
    </Document>
</kml>'''

        kml_file = self.create_kml_file(kml_content)
        try:
            result = process_kml(kml_file)

            point = list(result['points'].values())[0]
            self.assertEqual(point['desc'], 'Custom Point Name')

        finally:
            os.remove(kml_file)


if __name__ == '__main__':
    unittest.main()
