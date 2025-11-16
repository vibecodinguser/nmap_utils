"""Модуль для обработки GPX файлов"""
import uuid
import gpxpy
import gpxpy.gpx
from shapely.geometry import LineString, Point


def process_gpx(gpx_path):
    """Обрабатывает GPX файл и возвращает словарь с paths и points"""
    output = {"paths": {}, "points": {}}
    titles = set()  # Собираем уникальные значения title
    categories = set()  # Собираем уникальные значения category_t
    
    try:
        # Читаем GPX файл
        with open(gpx_path, 'r', encoding='utf-8') as f:
            gpx = gpxpy.parse(f)
        
        # Обработка tracks (треки)
        # Получаем имя из metadata для использования как fallback
        metadata_name = None
        if hasattr(gpx, 'metadata') and gpx.metadata and hasattr(gpx.metadata, 'name') and gpx.metadata.name:
            metadata_name = gpx.metadata.name.strip()
        
        for track in gpx.tracks:
            # Извлекаем имя трека: сначала из <trk><name>, если отсутствует - из <metadata><name>
            # Если track.name присутствует, metadata.name не используется
            track_name = None
            if track.name:
                track_name = track.name.strip()
            elif metadata_name:
                track_name = metadata_name
            
            if track_name:
                titles.add(track_name)
            
            # Создаем точку для трека с координатами из первой точки первого сегмента
            if track_name and track.segments and len(track.segments) > 0:
                first_segment = track.segments[0]
                if first_segment.points and len(first_segment.points) > 0:
                    first_point = first_segment.points[0]
                    point_uuid = str(uuid.uuid4())
                    point_data = {
                        "coords": [first_point.longitude, first_point.latitude],
                        "desc": track_name
                    }
                    output["points"][point_uuid] = point_data
            
            for segment in track.segments:
                if len(segment.points) > 1:
                    coords = [[point.longitude, point.latitude] for point in segment.points]
                    line_uuid = str(uuid.uuid4())
                    output["paths"][line_uuid] = coords
        
        # Обработка routes (маршруты)
        for route in gpx.routes:
            route_name = route.name or ""
            
            if route_name:
                titles.add(route_name.strip())
            
            if len(route.points) > 1:
                coords = [[point.longitude, point.latitude] for point in route.points]
                line_uuid = str(uuid.uuid4())
                output["paths"][line_uuid] = coords
        
        # Обработка waypoints (точки)
        for waypoint in gpx.waypoints:
            waypoint_name = waypoint.name or ""
            waypoint_description = waypoint.description or ""
            
            if waypoint_name:
                titles.add(waypoint_name.strip())
            
            point_uuid = str(uuid.uuid4())
            point_data = {
                "coords": [waypoint.longitude, waypoint.latitude]
            }
            
            # Формируем описание из метаданных
            desc_parts = []
            if waypoint_name:
                desc_parts.append(waypoint_name)
            if waypoint_description:
                desc_parts.append(f"({waypoint_description})")
            
            if desc_parts:
                point_data["desc"] = " ".join(desc_parts)
            
            output["points"][point_uuid] = point_data
        
        # Добавляем информацию о category_t и title в результат
        if categories:
            output["category_t"] = ", ".join(sorted(categories))
        if titles:
            output["title"] = ", ".join(sorted(titles))
        
        return output
    
    except Exception as e:
        raise Exception(f"Ошибка обработки GPX: {str(e)}")

