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
    Получаем данные из НСПД по реестровому номеру, сохраняет во временный GeoJSON
    и обрабатывает его с помощью process_geojson.
    """
    try:
        logger.info(f"Поиск объекта в НСПД по реестровому номеру: {registry_number}")
        nspd = Nspd()
        # Поиск объекта в слое "Населённые пункты (полигоны)"
        results = nspd.search_in_layer(registry_number, Layer36281Feature)

        if not results:
            raise ProcessingError("NSPD Error", f"Объект с номером {registry_number} не найден")
        target_feature = results[0]

        # Преобразуем в GeoJSON структуру
        if hasattr(target_feature, 'model_dump'):
            feature_dict = target_feature.model_dump()
        elif hasattr(target_feature, 'dict'):
            feature_dict = target_feature.dict()
        else:
            if hasattr(target_feature, '__geo_interface__'):
                feature_dict = target_feature.__geo_interface__
            else:
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


def debug_search(query):
    """
    Отладочная функция для тестирования поиска в НСПД. Выводит результаты поиска в консоль для диагностики.
    """
    print(f"Searching for: {query}")
    try:
        nspd = Nspd()

        print(f"Searching in Layer36281Feature (Localities)...")
        results = nspd.search_in_layer(query, Layer36281Feature)
        print(f"Layer Search Results: {results}")

        if results:
            print(f"First result type: {type(results[0])}")
            try:
                print(f"First result dump: {results[0].model_dump()}")
            except:
                print("Could not dump model")

    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    debug_search("23:01-4.9")
