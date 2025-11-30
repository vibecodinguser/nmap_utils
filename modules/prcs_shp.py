import os
import uuid
import logging
import geopandas as gpd
from shapely.geometry import Polygon
from typing import Dict, Any
from .prcs_flow import ProcessingError, ERR_SHAPEFILE


logger = logging.getLogger(__name__)

"""
Получаем архив с Shapefiles и извлекаем из него координаты объекта без разархивирования с помощью geopandas.
"""


def process_zip(zip_path: str) -> Dict[str, Any]:
    try:
        gdf = gpd.read_file(f"zip://{zip_path}", encoding='utf-8')
    except Exception as e:
        raise ProcessingError(ERR_SHAPEFILE, f"Ошибка чтения ZIP-файла: {str(e)}")

    # Проверки
    if gdf.empty:
        raise ProcessingError(ERR_SHAPEFILE, "Shapefile пуст")

    if gdf.crs is None:
        raise ProcessingError(ERR_SHAPEFILE, "Shapefile не имеет CRS")

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

        """
        Генерируем описание объекта из метаинформации shapefile для Polygon/MultiPolygon это центр полигона, 
        для остальных объектов это первая координата из списка.
        """

        desc_lines = ["Особо охраняемые природные территории России\n"]

        fields = [
            ('nid', 'Идентификатор ООПТ'),
            ('status_tit', 'Статус'),
            ('sig', 'Значение'),
            ('category_t', 'Категория'),
            ('title', 'Название')
        ]

        has_data = False
        for field, label in fields:
            if field in row and row[field]:
                has_data = True
                raw_val = row[field]
                val = str(raw_val)

                if field == 'nid':
                    try:
                        val = str(int(float(raw_val)))
                    except (ValueError, TypeError):
                        pass

                if field == 'sig':
                    if val == 'regional':
                        val = 'региональный'
                    elif val == 'federal':
                        val = 'федеральный'

                desc_lines.append(f"{label} - {val}")

        if has_data:
            desc = "\n".join(desc_lines)
        else:
            desc = ""

        if not desc:
            desc = os.path.basename(zip_path)
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
