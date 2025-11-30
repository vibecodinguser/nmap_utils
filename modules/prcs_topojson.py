import os
import uuid
import logging
import geopandas as gpd
from shapely.geometry import Polygon
from typing import Dict, Any
from .prcs_flow import ProcessingError, ERR_SHAPEFILE


logger = logging.getLogger(__name__)

"""
Получаем TopoJSON файл и извлекаем из него координаты объекта с помощью geopandas.
"""


def process_topojson(file_path: str) -> Dict[str, Any]:
    try:
        gdf = gpd.read_file(file_path, encoding='utf-8')
    except Exception as e:
        raise ProcessingError(ERR_SHAPEFILE, f"Ошибка чтения файла: {str(e)}")

    # Проверки
    if gdf.empty:
        raise ProcessingError(ERR_SHAPEFILE, "TopoJSON пуст")

    if gdf.crs is None:
        pass

    paths = {}
    points = {}
    metadata = []

    for _, row in gdf.iterrows():
        geom = row.geometry
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
            for line in geom.geoms:
                current_feature_paths.append(list(line.coords))

        # Генерируем описание объекта из названия файла
        desc = os.path.basename(file_path)

        category = row.get('category_t', '')
        title = row.get('title', '')
        if category or title:
            display_text = f"{category} {title}".strip()
            if display_text and display_text not in metadata:
                metadata.append(display_text)
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

    return {"paths": paths, "points": points, "metadata": metadata}
