from typing import Dict, Any, Optional

ERR_JSON_PARSE = "ERR_JSON_PARSE"
ERR_STRUCT_INVALID = "ERR_STRUCT_INVALID"
ERR_LOGIC = "ERR_LOGIC"
ERR_NETWORK = "ERR_NETWORK"
ERR_SHAPEFILE = "ERR_SHAPEFILE"

KEY_PATHS = "paths"
KEY_POINTS = "points"


class ProcessingError(Exception):
    def __init__(self, code: str, message: str, details: Optional[str] = None):
        self.code = code
        self.message = message
        self.details = details
        super().__init__(self.message)


def validate_shp(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    if KEY_PATHS not in data or not isinstance(data[KEY_PATHS], dict):
        return False
    if KEY_POINTS not in data or not isinstance(data[KEY_POINTS], dict):
        return False
    return True


def merge_nmap_output_template(current_index: Dict[str, Any], new_data: Dict[str, Any]) -> Dict[str, Any]:
    if not validate_shp(current_index):
        if validate_shp(new_data):
            return new_data
        return create_nmap_output_template()

    if not validate_shp(new_data):
        return current_index

    merged = {
        KEY_PATHS: current_index[KEY_PATHS].copy(),
        KEY_POINTS: current_index[KEY_POINTS].copy()
    }

    merged[KEY_PATHS].update(new_data[KEY_PATHS])
    merged[KEY_POINTS].update(new_data[KEY_POINTS])

    return merged


def create_nmap_output_template() -> Dict[str, Any]:
    return {KEY_PATHS: {}, KEY_POINTS: {}}
