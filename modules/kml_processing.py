"""Модуль для обработки KML/KMZ файлов"""
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_coordinates(coords_text):
    """Парсит строку координат KML и возвращает список [longitude, latitude]"""
    if not coords_text:
        return None
    
    # Удаляем пробелы и переносы строк
    coords_text = coords_text.strip().replace('\n', ' ').replace('\t', ' ')
    
    # Разбиваем по пробелам и берем первую пару координат
    parts = coords_text.split()
    if not parts:
        return None
    
    # Берем первую пару координат (формат: longitude,latitude[,altitude])
    first_coord = parts[0]
    coord_parts = first_coord.split(',')
    
    if len(coord_parts) < 2:
        return None
    
    try:
        longitude = float(coord_parts[0].strip())
        latitude = float(coord_parts[1].strip())
        return [longitude, latitude]
    except (ValueError, IndexError):
        return None


def parse_coordinates_list(coords_text):
    """Парсит строку координат KML и возвращает список координат [[longitude, latitude], ...]"""
    if not coords_text:
        return []
    
    # Удаляем пробелы и переносы строк
    coords_text = coords_text.strip().replace('\n', ' ').replace('\t', ' ')
    
    # Разбиваем по пробелам
    parts = coords_text.split()
    coords = []
    
    for part in parts:
        coord_parts = part.split(',')
        if len(coord_parts) >= 2:
            try:
                longitude = float(coord_parts[0].strip())
                latitude = float(coord_parts[1].strip())
                coords.append([longitude, latitude])
            except (ValueError, IndexError):
                continue
    
    return coords


def calculate_polygon_center(coords_list):
    """Вычисляет центр полигона из списка координат"""
    if not coords_list or len(coords_list) == 0:
        return None
    
    # Вычисляем среднее арифметическое всех координат
    total_longitude = 0.0
    total_latitude = 0.0
    count = 0
    
    for coord in coords_list:
        if len(coord) >= 2:
            total_longitude += coord[0]
            total_latitude += coord[1]
            count += 1
    
    if count == 0:
        return None
    
    return [total_longitude / count, total_latitude / count]


def find_kml_namespace(root):
    """Находит namespace KML из корневого элемента"""
    # Пробуем различные варианты namespace
    namespaces = {
        'kml': 'http://www.opengis.net/kml/2.2',
        'kml22': 'http://www.opengis.net/kml/2.2',
        'kml21': 'http://earth.google.com/kml/2.1',
        'kml20': 'http://earth.google.com/kml/2.0'
    }
    
    # Проверяем атрибуты корневого элемента
    for prefix, uri in root.attrib.items():
        if prefix.startswith('{http://www.w3.org/2000/xmlns/}') or prefix == 'xmlns':
            if uri in namespaces.values():
                return uri
    
    # Если не нашли, используем стандартный
    return 'http://www.opengis.net/kml/2.2'


def process_kml(kml_path):
    """Обрабатывает KML/KMZ файл и возвращает словарь с paths и points"""
    output = {"paths": {}, "points": {}}
    titles = set()  # Собираем уникальные значения title
    categories = set()  # Собираем уникальные значения category_t
    
    try:
        # Проверяем, является ли файл KMZ (ZIP архив)
        file_path = Path(kml_path)
        is_kmz = file_path.suffix.lower() == '.kmz'
        
        if is_kmz:
            # Распаковываем KMZ и ищем doc.kml
            with zipfile.ZipFile(kml_path, 'r') as kmz_file:
                # Ищем doc.kml или первый .kml файл
                kml_content = None
                for name in kmz_file.namelist():
                    if name.lower().endswith('.kml'):
                        kml_content = kmz_file.read(name).decode('utf-8')
                        break
                
                if not kml_content:
                    raise Exception("Не найден KML файл в KMZ архиве")
                
                # Парсим XML из строки
                root = ET.fromstring(kml_content)
        else:
            # Читаем обычный KML файл
            tree = ET.parse(kml_path)
            root = tree.getroot()
        
        # Находим namespace
        ns = find_kml_namespace(root)
        ns_map = {'kml': ns}
        
        # Функция для поиска элементов с учетом namespace
        def find_elements(parent, tag):
            # Пробуем с namespace
            result = parent.findall(f'.//kml:{tag}', ns_map)
            if result:
                return result
            # Пробуем без namespace (на случай, если namespace не указан)
            result = parent.findall(f'.//{tag}')
            if result:
                return result
            # Пробуем с полным namespace в теге
            result = parent.findall(f'.//{{{ns}}}{tag}')
            return result
        
        def find_element(parent, tag):
            # Пробуем с namespace
            result = parent.find(f'.//kml:{tag}', ns_map)
            if result is not None:
                return result
            # Пробуем без namespace
            result = parent.find(f'.//{tag}')
            if result is not None:
                return result
            # Пробуем с полным namespace в теге
            result = parent.find(f'.//{{{ns}}}{tag}')
            return result
        
        def get_text(element, tag, default=""):
            """Извлекает текст из элемента"""
            if element is None:
                return default
            elem = find_element(element, tag)
            if elem is not None and elem.text:
                return elem.text.strip()
            return default
        
        def format_desc(placemark_name, document_name):
            """Формирует описание desc согласно правилам:
            - Если есть только Document.name → "Файл: Document.name"
            - Если есть только Placemark.name → "Название: Placemark.name"
            - Если есть оба → "Файл: Document.name Название: Placemark.name"
            """
            desc_parts = []
            if document_name:
                desc_parts.append(f"Файл: {document_name}")
            if placemark_name:
                desc_parts.append(f"Название: {placemark_name}")
            return " ".join(desc_parts) if desc_parts else None
        
        # Извлекаем Document.name для использования как fallback
        document_name = ""
        document_elem = find_element(root, 'Document')
        if document_elem is not None:
            document_name = get_text(document_elem, 'name')
        
        # Обрабатываем все Placemark элементы
        placemarks = find_elements(root, 'Placemark')
        
        for placemark in placemarks:
            # Извлекаем name и description
            name = get_text(placemark, 'name')
            description = get_text(placemark, 'description')
            
            if name:
                titles.add(name)
            
            # Формируем описание
            desc_parts = []
            if name:
                desc_parts.append(name)
            if description:
                desc_parts.append(f"({description})")
            desc = " ".join(desc_parts) if desc_parts else None
            
            # Обрабатываем Point
            point_elem = find_element(placemark, 'Point')
            if point_elem is not None:
                coords_elem = find_element(point_elem, 'coordinates')
                if coords_elem is not None and coords_elem.text:
                    coords = parse_coordinates(coords_elem.text)
                    if coords:
                        point_uuid = str(uuid.uuid4())
                        point_data = {"coords": coords}
                        if desc:
                            point_data["desc"] = desc
                        output["points"][point_uuid] = point_data
            
            # Обрабатываем LineString
            linestring_elem = find_element(placemark, 'LineString')
            if linestring_elem is not None:
                coords_elem = find_element(linestring_elem, 'coordinates')
                if coords_elem is not None and coords_elem.text:
                    coords_list = parse_coordinates_list(coords_elem.text)
                    if len(coords_list) > 1:
                        line_uuid = str(uuid.uuid4())
                        output["paths"][line_uuid] = coords_list
                        
                        # Добавляем первую точку линии в points только если есть имя
                        linestring_desc = format_desc(name, document_name)
                        if linestring_desc:
                            first_point = coords_list[0]
                            point_uuid = str(uuid.uuid4())
                            point_data = {"coords": first_point, "desc": linestring_desc}
                            output["points"][point_uuid] = point_data
            
            # Обрабатываем Polygon
            polygon_elem = find_element(placemark, 'Polygon')
            if polygon_elem is not None:
                # Ищем outerBoundaryIs -> LinearRing -> coordinates
                outer_boundary = find_element(polygon_elem, 'outerBoundaryIs')
                if outer_boundary is not None:
                    linear_ring = find_element(outer_boundary, 'LinearRing')
                    if linear_ring is not None:
                        coords_elem = find_element(linear_ring, 'coordinates')
                        if coords_elem is not None and coords_elem.text:
                            coords_list = parse_coordinates_list(coords_elem.text)
                            if len(coords_list) > 1:
                                # Для полигона берем границы как путь
                                line_uuid = str(uuid.uuid4())
                                output["paths"][line_uuid] = coords_list
                                
                                # Вычисляем центр полигона и добавляем в points только если есть имя
                                polygon_desc = format_desc(name, document_name)
                                if polygon_desc:
                                    center = calculate_polygon_center(coords_list)
                                    if center:
                                        point_uuid = str(uuid.uuid4())
                                        point_data = {"coords": center, "desc": polygon_desc}
                                        output["points"][point_uuid] = point_data
        
        # Добавляем информацию о category_t и title в результат
        if categories:
            output["category_t"] = ", ".join(sorted(categories))
        if titles:
            output["title"] = ", ".join(sorted(titles))
        
        return output
    
    except Exception as e:
        raise Exception(f"Ошибка обработки KML/KMZ: {str(e)}")

