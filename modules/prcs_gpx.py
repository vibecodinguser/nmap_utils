import uuid
import logging
import os
import xml.etree.ElementTree as ET
from typing import Dict, Any
from .prcs_flow import ProcessingError, ERR_SHAPEFILE


logger = logging.getLogger(__name__)

"""
Получаем GPX файл и извлекаем из него треки и путевые точки.
"""


def process_gpx(file_path: str) -> Dict[str, Any]:
    try:
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

    # Парсим tracks (trk)
    for trk in root.iter():
        if get_tag(trk) == 'trk':
            trk_name = None
            # Try to find name
            for child in trk:
                if get_tag(child) == 'name':
                    trk_name = child.text
                    break

            if trk_name:
                clean_name = trk_name.strip()
                if clean_name and clean_name not in metadata:
                    metadata.append(clean_name)

            for trkseg in trk:
                if get_tag(trkseg) == 'trkseg':
                    segment_coords = []
                    for trkpt in trkseg:
                        if get_tag(trkpt) == 'trkpt':
                            try:
                                lat = float(trkpt.attrib['lat'])
                                lon = float(trkpt.attrib['lon'])
                                segment_coords.append([lon, lat])
                            except (ValueError, KeyError):
                                continue

                    if segment_coords:
                        shared_uuid = str(uuid.uuid4())
                        paths[shared_uuid] = segment_coords

                        first_pt = segment_coords[0]
                        points[shared_uuid] = {
                            "coords": first_pt,
                            "desc": desc
                        }

    # Парсим waypoints (wpt)
    for wpt in root.iter():
        if get_tag(wpt) == 'wpt':
            try:
                lat = float(wpt.attrib['lat'])
                lon = float(wpt.attrib['lon'])

                wpt_name = desc
                for child in wpt:
                    if get_tag(child) == 'name':
                        if child.text:
                            wpt_name = child.text.strip()
                        break

                wpt_uuid = str(uuid.uuid4())
                points[wpt_uuid] = {
                    "coords": [lon, lat],
                    "desc": wpt_name
                }

            except (ValueError, KeyError):
                continue

    return {"paths": paths, "points": points, "metadata": metadata}
