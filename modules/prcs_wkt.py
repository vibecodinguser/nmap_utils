import os
import uuid
import logging
from shapely import wkt
from shapely.geometry import Polygon
from typing import Dict, Any
from .prcs_flow import ProcessingError, ERR_SHAPEFILE


logger = logging.getLogger(__name__)

"""
Получаем WKT файл и извлекаем из него координаты объектов.
"""


def process_wkt(file_path: str) -> Dict[str, Any]:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        raise ProcessingError(ERR_SHAPEFILE, f"Ошибка чтения файла: {str(e)}")

    if not lines:
        raise ProcessingError(ERR_SHAPEFILE, "WKT пуст")

    paths = {}
    points = {}
    metadata = []

    # Генерируем описание объекта из названия файла
    desc = os.path.basename(file_path)

    for line_num, line in enumerate(lines, 1):
        line = line.strip()

        # Пропускаем если решетка
        if not line or line.startswith('#'):
            continue

        try:
            geom = wkt.loads(line)
        except Exception as e:
            logger.warning(f"Ошибка парсинга WKT в строке {line_num}: {str(e)}")
            continue

        if geom is None or geom.is_empty:
            continue

        current_feature_paths = []

        if geom.geom_type == 'Point':
            current_feature_paths.append([[geom.x, geom.y]])

        elif geom.geom_type in ['LineString', 'Line']:
            current_feature_paths.append(list(geom.coords))

        elif geom.geom_type == 'Polygon':
            current_feature_paths.append(list(geom.exterior.coords))
            for interior in geom.interiors:
                current_feature_paths.append(list(interior.coords))

        elif geom.geom_type == 'MultiPoint':
            for pt in geom.geoms:
                current_feature_paths.append([[pt.x, pt.y]])

        elif geom.geom_type == 'MultiPolygon':
            for poly in geom.geoms:
                current_feature_paths.append(list(poly.exterior.coords))
                for interior in poly.interiors:
                    current_feature_paths.append(list(interior.coords))

        elif geom.geom_type == 'MultiLineString':
            for line_geom in geom.geoms:
                current_feature_paths.append(list(line_geom.coords))

        elif geom.geom_type == 'GeometryCollection':
            for sub_geom in geom.geoms:
                if sub_geom.geom_type == 'Point':
                    current_feature_paths.append([[sub_geom.x, sub_geom.y]])
                elif sub_geom.geom_type in ['LineString', 'Line']:
                    current_feature_paths.append(list(sub_geom.coords))
                elif sub_geom.geom_type == 'Polygon':
                    current_feature_paths.append(list(sub_geom.exterior.coords))
                    for interior in sub_geom.interiors:
                        current_feature_paths.append(list(interior.coords))

        for p_coords in current_feature_paths:
            shared_uuid = str(uuid.uuid4())
            paths[shared_uuid] = p_coords
            pt_coords = None

            # Вычисляем центроид для Polygon/MultiPolygon
            if geom.geom_type in ['Polygon', 'MultiPolygon']:
                try:
                    if len(p_coords) >= 3:
                        poly_geom = Polygon(p_coords)
                        centroid = poly_geom.centroid
                        pt_coords = [centroid.x, centroid.y]
                    else:
                        if p_coords:
                            pt_coords = p_coords[0]
                except Exception:
                    if p_coords:
                        pt_coords = p_coords[0]

            # Берем первую точку координат для LineString, Point, MultiPoint, MultiLineString
            elif p_coords and len(p_coords) > 0:
                pt_coords = p_coords[0]

            if pt_coords:
                pt_coords = [pt_coords[0], pt_coords[1]]
            else:
                continue

            points[shared_uuid] = {
                "coords": pt_coords,
                "desc": desc
            }

    if not paths:
        raise ProcessingError(ERR_SHAPEFILE, "Геометрия WKT файла не валидна")

    return {"paths": paths, "points": points, "metadata": metadata}
