import uuid
import logging
import os
import zipfile
import xml.etree.ElementTree as ET
from typing import Dict, Any, List
from .prcs_flow import ProcessingError, ERR_SHAPEFILE


logger = logging.getLogger(__name__)

"""
Получаем KML или KMZ файл и извлекаем из него координаты объектов.
"""


def process_kml(file_path: str) -> Dict[str, Any]:
    try:
        if zipfile.is_zipfile(file_path):
            with zipfile.ZipFile(file_path, 'r') as z:
                kml_files = [f for f in z.namelist() if f.lower().endswith('.kml')]
                if not kml_files:
                    raise ProcessingError(ERR_SHAPEFILE, "В KMZ-архиве отсутствует KML-файл")

                with z.open(kml_files[0]) as f:
                    tree = ET.parse(f)
        else:
            tree = ET.parse(file_path)

        root = tree.getroot()
    except Exception as e:
        raise ProcessingError(ERR_SHAPEFILE, f"Ошибка чтения файла: {str(e)}")

    paths = {}
    points = {}
    metadata = []

    def get_tag(elem):
        return elem.tag.split('}', 1)[-1] if '}' in elem.tag else elem.tag

    # Генерируем описание объекта из названия файла
    desc = os.path.basename(file_path)

    def parse_coordinates(coords_text: str) -> List[List[float]]:
        coords = []
        for coord in coords_text.strip().split():
            try:
                parts = coord.split(',')
                if len(parts) >= 2:
                    lon = float(parts[0])
                    lat = float(parts[1])
                    coords.append([lon, lat])
            except ValueError:
                continue
        return coords

    for placemark in root.iter():
        if get_tag(placemark) == 'Placemark':
            name = None
            for child in placemark:
                if get_tag(child) == 'name':
                    name = child.text
                    break

            if name:
                clean_name = name.strip()
                if clean_name and clean_name not in metadata:
                    metadata.append(clean_name)

            for child in placemark.iter():
                tag = get_tag(child)

                if tag == 'LineString':
                    for sub in child:
                        if get_tag(sub) == 'coordinates' and sub.text:
                            line_coords = parse_coordinates(sub.text)
                            if line_coords:
                                shared_uuid = str(uuid.uuid4())
                                paths[shared_uuid] = line_coords

                                # Start point
                                points[shared_uuid] = {
                                    "coords": line_coords[0],
                                    "desc": desc
                                }

                elif tag == 'Point':
                    for sub in child:
                        if get_tag(sub) == 'coordinates' and sub.text:
                            pt_coords = parse_coordinates(sub.text)
                            if pt_coords:
                                pt_uuid = str(uuid.uuid4())
                                points[pt_uuid] = {
                                    "coords": pt_coords[0],
                                    "desc": name if name else desc
                                }

    return {"paths": paths, "points": points, "metadata": metadata}
