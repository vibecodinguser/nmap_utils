import json
import logging
import os
import uuid

import geopandas as gpd
import pandas as pd

from settings import INDEX_JSON_PATH

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def process_polygon(poly, desc):
    """Обрабатывает один полигон, создавая отдельные объекты для exterior и каждого interior"""
    objects = []
    
    # Exterior как отдельный объект
    polygon_uuid = str(uuid.uuid4())
    coords = list(poly.exterior.coords)
    centroid = poly.exterior.centroid
    point_uuid = str(uuid.uuid4())
    
    objects.append({
        "path_uuid": polygon_uuid,
        "coords": coords,
        "point_uuid": point_uuid,
        "centroid": [float(centroid.x), float(centroid.y)],
        "desc": desc
    })
    
    # Каждый interior как отдельный объект (без точки)
    for interior in poly.interiors:
        polygon_uuid = str(uuid.uuid4())
        coords = list(interior.coords)
        
        objects.append({
            "path_uuid": polygon_uuid,
            "coords": coords,
            "point_uuid": None,
            "centroid": None,
            "desc": desc
        })
    
    return objects

def process_shapefile(zip_path):
    """Обрабатывает shapefile из zip архива"""
    try:
        gdf = gpd.read_file(f"zip://{os.path.abspath(zip_path)}", encoding='utf-8')
        
        result = {"paths": {}, "points": {}}
        
        for idx, row in gdf.iterrows():
            geometry = row.geometry
            
            # Извлечение данных с кодировкой UTF-8
            category_t = ""
            if "category_t" in row and pd.notna(row.get("category_t")):
                cat_val = row.get("category_t")
                if isinstance(cat_val, bytes):
                    category_t = cat_val.decode('utf-8', errors='ignore')
                else:
                    category_t = str(cat_val)
            
            title = ""
            if "title" in row and pd.notna(row.get("title")):
                title_val = row.get("title")
                if isinstance(title_val, bytes):
                    title = title_val.decode('utf-8', errors='ignore')
                else:
                    title = str(title_val)
            
            sig = ""
            if "sig" in row and pd.notna(row.get("sig")):
                sig_val = row.get("sig")
                if isinstance(sig_val, bytes):
                    sig = sig_val.decode('utf-8', errors='ignore')
                else:
                    sig = str(sig_val)
                # Замена значений sig
                if sig == "regional":
                    sig = "региональный"
                elif sig == "federal":
                    sig = "федеральный"
                if sig:
                    sig = f" ({sig})"
            
            desc = f"{category_t} {title}{sig}".strip()
            
            # Обработка различных типов геометрии
            if geometry.geom_type == "Point":
                point_uuid = str(uuid.uuid4())
                result["points"][point_uuid] = {
                    "coords": [float(geometry.x), float(geometry.y)],
                    "desc": desc
                }
            
            elif geometry.geom_type == "MultiPoint":
                for point in geometry.geoms:
                    point_uuid = str(uuid.uuid4())
                    result["points"][point_uuid] = {
                        "coords": [float(point.x), float(point.y)],
                        "desc": desc
                    }
            
            elif geometry.geom_type == "LineString":
                path_uuid = str(uuid.uuid4())
                coords = list(geometry.coords)
                result["paths"][path_uuid] = coords
            
            elif geometry.geom_type == "MultiLineString":
                for line in geometry.geoms:
                    path_uuid = str(uuid.uuid4())
                    coords = list(line.coords)
                    result["paths"][path_uuid] = coords
            
            elif geometry.geom_type == "MultiPolygon":
                for poly in geometry.geoms:
                    objects = process_polygon(poly, desc)
                    for obj in objects:
                        result["paths"][obj["path_uuid"]] = obj["coords"]
                        # Создаем точку только для exterior контуров
                        if obj["point_uuid"] is not None:
                            result["points"][obj["point_uuid"]] = {
                                "coords": obj["centroid"],
                                "desc": obj["desc"]
                            }
            
            elif geometry.geom_type == "Polygon":
                objects = process_polygon(geometry, desc)
                for obj in objects:
                    result["paths"][obj["path_uuid"]] = obj["coords"]
                    # Создаем точку только для exterior контуров
                    if obj["point_uuid"] is not None:
                        result["points"][obj["point_uuid"]] = {
                            "coords": obj["centroid"],
                            "desc": obj["desc"]
                        }
        
        return result
    
    except Exception as e:
        logger.error(f"Ошибка обработки {zip_path}: {e}")
        return None

def merge_json_data(new_data, existing_data):
    """Объединяет новые данные с существующими, пропуская совпадающие UUID"""
    merged = {
        "paths": existing_data.get("paths", {}).copy(),
        "points": existing_data.get("points", {}).copy()
    }
    
    for uuid_key, coords in new_data.get("paths", {}).items():
        if uuid_key not in merged["paths"]:
            merged["paths"][uuid_key] = coords
    
    for uuid_key, point_data in new_data.get("points", {}).items():
        if uuid_key not in merged["points"]:
            merged["points"][uuid_key] = point_data
    
    return merged

def process_files(file_paths):
    """Обрабатывает список zip файлов"""
    # Сначала загружаем существующие данные
    existing_data = {"paths": {}, "points": {}}
    if os.path.exists(INDEX_JSON_PATH):
        try:
            with open(INDEX_JSON_PATH, "r", encoding="utf-8") as f:
                loaded_data = json.load(f)
                # Проверяем, что файл не пустой (есть данные в paths или points)
                if loaded_data and (loaded_data.get("paths") or loaded_data.get("points")):
                    existing_data = loaded_data
                    logger.info("Загружены существующие данные из index.json")
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Ошибка чтения index.json: {e}, создаем новый")
    
    # Обрабатываем новые файлы
    new_data = {"paths": {}, "points": {}}
    for file_path in file_paths:
        result = process_shapefile(file_path)
        if result:
            new_data = merge_json_data(result, new_data)
            logger.info(f"Обработан: {file_path}")
    
    # Объединяем новые данные с существующими
    final_data = merge_json_data(new_data, existing_data)
    
    with open(INDEX_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=4)
    
    logger.info(f"Объединено: {len(existing_data.get('paths', {}))} -> {len(final_data.get('paths', {}))} paths, "
                f"{len(existing_data.get('points', {}))} -> {len(final_data.get('points', {}))} points")
    
    return final_data

