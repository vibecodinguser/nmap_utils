import os
import json
import uuid
import logging
from typing import Dict, Any
from pynspd import Nspd
from pynspd.schemas import Layer36281Feature
from .prcs_geojson import process_geojson
from .prcs_flow import ProcessingError

logger = logging.getLogger(__name__)

def process_nspd_locality(registry_number: str) -> Dict[str, Any]:
    """
    Получает данные из НСПД по реестровому номеру, сохраняет во временный GeoJSON
    и обрабатывает его с помощью process_geojson.
    """
    try:
        logger.info(f"Поиск объекта в НСПД по номеру: {registry_number}")
        
        # Инициализация клиента NSPD (используем контекстный менеджер если поддерживается, или просто статический вызов)
        # Согласно документации (найденной в поиске), pynspd имеет search метод.
        # Пробуем использовать Nspd.search или создание экземпляра.
        # Предполагаем использование через экземпляр или статический метод, адаптируем по ходу.
        # В примере было: pynspd search "..."
        
        nspd = Nspd()
        # Поиск объекта в слое "Населённые пункты (полигоны)"
        results = nspd.search_in_layer(registry_number, Layer36281Feature)
        
        if not results:
             raise ProcessingError("NSPD Error", f"Объект с номером {registry_number} не найден")

        # Предполагаем, что results - это список объектов, у которых есть метод to_geojson или свойство __geo_interface__
        # Или results это уже GeoJSON FeatureCollection
        
        # Для простоты, попробуем получить geojson из первого результата
        # Если results это список pydantic моделей
        
        target_feature = results[0]
        
        # Преобразуем в GeoJSON структуру
        # Если у объекта есть метод model_dump (pydantic v2) или dict()
        if hasattr(target_feature, 'model_dump'):
            feature_dict = target_feature.model_dump()
        elif hasattr(target_feature, 'dict'):
            feature_dict = target_feature.dict()
        else:
             # Пытаемся использовать __geo_interface__ если есть
            if hasattr(target_feature, '__geo_interface__'):
                feature_dict = target_feature.__geo_interface__
            else:
                # Если это просто словарь
                feature_dict = target_feature

        # Оборачиваем в FeatureCollection для корректного чтения geopandas
        geojson_data = {
            "type": "FeatureCollection",
            "features": [feature_dict]
        }
        
        # Сохраняем во временный файл
        temp_filename = f"nspd_{registry_number}_{uuid.uuid4()}.geojson"
        temp_path = os.path.join("/tmp", temp_filename)
        
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, ensure_ascii=False, default=str)
            
        logger.info(f"Данные сохранены во временный файл: {temp_path}")
        
        # Обрабатываем как обычный GeoJSON
        try:
            result = process_geojson(temp_path)
            # Обновляем описание, чтобы было понятно, что это из НСПД
            for point in result.get('points', {}).values():
                point['desc'] = f"НСПД: {registry_number}"
            
            # Также обновляем метаданные если нужно
            if 'metadata' in result:
                 result['metadata'] = [f"НСПД: {registry_number}"] + result['metadata']

            return result
        finally:
            # Удаляем временный файл
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logger.error(f"Ошибка при обработке данных НСПД: {e}")
        raise ProcessingError("NSPD Error", f"Ошибка получения данных: {str(e)}")
