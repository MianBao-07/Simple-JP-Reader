import os
import base64
import requests

ANKI_URL = "http://127.0.0.1:8765"

def invoke(action, **params):
    try:
        response = requests.post(
            ANKI_URL,
            json={"action": action, "version": 6, "params": params},
            timeout=3
        )
        response.raise_for_status()
        data = response.json()
        if len(data) != 2:
            raise Exception("Response has an unexpected number of fields.")
        if "error" not in data:
            raise Exception("Response is missing required error field.")
        if "result" not in data:
            raise Exception("Response is missing required result field.")
        if data["error"] is not None:
            raise Exception(data["error"])
        return data["result"]
    except requests.exceptions.ConnectionError:
        return {"error": "Anki is not running or AnkiConnect plugin is missing."}
    except Exception as e:
        return {"error": str(e)}

def is_anki_alive():
    res = invoke("version")
    return not isinstance(res, dict) or "error" not in res

def get_deck_names():
    res = invoke("deckNames")
    return [] if isinstance(res, dict) and "error" in res else res

def get_model_names():
    res = invoke("modelNames")
    return [] if isinstance(res, dict) and "error" in res else res

def add_anki_card(deck_name, model_name, term, reading, definition, sentence, image_path=None, custom_map=None):
    if custom_map is None:
        custom_map = {}
        
    mapped_fields = {}
    
    if custom_map.get("term"): mapped_fields[custom_map["term"]] = term
    if custom_map.get("reading"): mapped_fields[custom_map["reading"]] = reading
    if custom_map.get("meaning"): mapped_fields[custom_map["meaning"]] = definition
    if custom_map.get("sentence"): mapped_fields[custom_map["sentence"]] = sentence
    
    image_field = custom_map.get("image")
    if image_field and image_path and os.path.exists(image_path):
        img_name = os.path.basename(image_path)
        with open(image_path, "rb") as img_file:
            b64_data = base64.b64encode(img_file.read()).decode("utf-8")
        
        invoke("storeMediaFile", filename=img_name, data=b64_data)
        mapped_fields[image_field] = f'<img src="{img_name}">'

    if not mapped_fields:
        mapped_fields = {
            "Front": f"{term} ({reading})<br><br>{sentence}",
            "Back": definition
        }

    note = {
        "deckName": deck_name,
        "modelName": model_name,
        "fields": mapped_fields,
        "options": {
            "allowDuplicate": False, # Prevents creating identical cards
            "duplicateScope": "deck"
        },
        "tags": ["simple-jp-reader"]
    }

    return invoke("addNote", note=note)