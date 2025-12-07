import json

def getkeyvalue(data, target_key):
    if isinstance(data, dict):
        if target_key in data:
            return data[target_key]
        for value in data.values():
            result = getkeyvalue(value, target_key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = getkeyvalue(item, target_key)
            if result is not None:
                return result
    return None

def read_json_file(filepath):
    with open(filepath, 'r') as file:
        return json.load(file)