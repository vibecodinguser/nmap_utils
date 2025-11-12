"""Модуль для обработки геометрии shapefile"""
import uuid
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, Polygon, MultiPolygon


def process_shapefile(zip_path):
    """Обрабатывает shapefile из zip-архива и возвращает словарь с paths и points"""
    output = {"paths": {}, "points": {}}
    
    try:
        # Читаем shapefile напрямую из zip
        gdf = gpd.read_file(f"zip://{zip_path}", encoding="utf-8")
        
        for idx, row in gdf.iterrows():
            geom = row.geometry
            
            # Пропускаем пустые геометрии
            if geom is None or geom.is_empty:
                continue
            
            # Обработка геометрии
            if geom.geom_type == "Polygon":
                _process_polygon(geom, output, row)
            elif geom.geom_type == "MultiPolygon":
                for poly in geom.geoms:
                    if not poly.is_empty:
                        _process_polygon(poly, output, row)
            elif geom.geom_type == "Point":
                _process_point(geom, output, row)
            elif geom.geom_type == "MultiPoint":
                for point in geom.geoms:
                    if not point.is_empty:
                        _process_point(point, output, row)
            elif geom.geom_type == "LineString":
                _process_linestring(geom, output, row)
            elif geom.geom_type == "MultiLineString":
                for line in geom.geoms:
                    if not line.is_empty:
                        _process_linestring(line, output, row)
        
        return output
    
    except Exception as e:
        raise Exception(f"Ошибка обработки shapefile: {str(e)}")


def _process_polygon(polygon, output, row):
    """Обрабатывает один полигон"""
    # Обработка exterior (внешний контур)
    if polygon.exterior:
        exterior_coords = list(polygon.exterior.coords)
        if len(exterior_coords) > 1:
            line_uuid = str(uuid.uuid4())
            output["paths"][line_uuid] = [[coord[0], coord[1]] for coord in exterior_coords]
    
    # Обработка interior (внутренние контуры)
    for interior in polygon.interiors:
        interior_coords = list(interior.coords)
        if len(interior_coords) > 1:
            line_uuid = str(uuid.uuid4())
            output["paths"][line_uuid] = [[coord[0], coord[1]] for coord in interior_coords]
    
    # Центр полигона
    center = polygon.centroid
    point_uuid = str(uuid.uuid4())
    
    # Проверка наличия полей для описания
    desc_parts = []
    if "category_t" in row and pd.notna(row["category_t"]):
        desc_parts.append(str(row["category_t"]))
    if "title" in row and pd.notna(row["title"]):
        desc_parts.append(str(row["title"]))
    if "sig" in row and pd.notna(row["sig"]):
        desc_parts.append(f"({str(row['sig'])})")
    
    point_data = {
        "coords": [center.x, center.y]
    }
    
    if desc_parts:
        point_data["desc"] = " ".join(desc_parts)
    
    output["points"][point_uuid] = point_data


def _process_point(point, output, row):
    """Обрабатывает точку"""
    point_uuid = str(uuid.uuid4())
    
    # Проверка наличия полей для описания
    desc_parts = []
    if "category_t" in row and pd.notna(row["category_t"]):
        desc_parts.append(str(row["category_t"]))
    if "title" in row and pd.notna(row["title"]):
        desc_parts.append(str(row["title"]))
    if "sig" in row and pd.notna(row["sig"]):
        desc_parts.append(f"({str(row['sig'])})")
    
    point_data = {
        "coords": [point.x, point.y]
    }
    
    if desc_parts:
        point_data["desc"] = " ".join(desc_parts)
    
    output["points"][point_uuid] = point_data


def _process_linestring(linestring, output, row):
    """Обрабатывает линию (LineString)"""
    coords = list(linestring.coords)
    if len(coords) > 1:
        line_uuid = str(uuid.uuid4())
        output["paths"][line_uuid] = [[coord[0], coord[1]] for coord in coords]

