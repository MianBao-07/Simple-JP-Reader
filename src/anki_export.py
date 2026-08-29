import os
import base64
import requests
import time
from janome.tokenizer import Tokenizer

ANKI_URL = "http://127.0.0.1:8765"

# Initialize Janome once for lightning-fast tokenization
janome_tokenizer = Tokenizer()

def generate_html_ruby(text):
    """Generates standard HTML ruby tags with smart Okurigana separation."""
    tokens = janome_tokenizer.tokenize(text)
    result = ""
    for token in tokens:
        surface = token.surface
        reading = token.reading
        
        # If the word contains a Kanji and Janome found a reading
        if any('\u4e00' <= c <= '\u9faf' for c in surface) and reading and reading != "*":
            # Convert Katakana reading to Hiragana
            hiragana = "".join(chr(ord(c) - 96) if 12449 <= ord(c) <= 12534 else c for c in reading)
            
            # 1. Strip matching leading kana (e.g., お茶 -> お + 茶)
            lead_kana = ""
            while surface and hiragana and surface[0] == hiragana[0]:
                lead_kana += surface[0]
                surface = surface[1:]
                hiragana = hiragana[1:]
                
            # 2. Strip matching trailing kana/Okurigana (e.g., 染まる -> 染 + まる)
            tail_kana = ""
            while surface and hiragana and surface[-1] == hiragana[-1]:
                tail_kana = surface[-1] + tail_kana
                surface = surface[:-1]
                hiragana = hiragana[:-1]
                
            # 3. Wrap ONLY the remaining Kanji core
            if surface:
                result += f"{lead_kana}<ruby>{surface}<rt>{hiragana}</rt></ruby>{tail_kana}"
            else:
                result += f"{lead_kana}{tail_kana}"
        else:
            result += surface
    return result

def auto_highlight(sentence, term):
    """Generates furigana and safely wraps the target term in the highlight HTML."""
    if not sentence or not term:
        return sentence
        
    ruby_sentence = generate_html_ruby(sentence)
    ruby_term = generate_html_ruby(term)
    
    # Attempt 1: Match the exact ruby-generated term
    highlighted = ruby_sentence.replace(ruby_term, f'<span class="highlight">{ruby_term}</span>')
    
    # Attempt 2 (Fallback): If Janome parsed the term differently in context
    if highlighted == ruby_sentence:
        highlighted = ruby_sentence.replace(term, f'<span class="highlight">{term}</span>')
        
    return highlighted

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
        
    if sentence and term in sentence:
        sentence = auto_highlight(sentence, term)

    term_with_ruby = generate_html_ruby(term)
        
    mapped_fields = {}
    
    if custom_map.get("term"): mapped_fields[custom_map["term"]] = term_with_ruby
    if custom_map.get("word"): mapped_fields[custom_map["word"]] = term_with_ruby
    if custom_map.get("reading"): mapped_fields[custom_map["reading"]] = reading
    if custom_map.get("meaning"): mapped_fields[custom_map["meaning"]] = definition
    if custom_map.get("sentence"): mapped_fields[custom_map["sentence"]] = sentence
    
    image_field = custom_map.get("image")
    if image_field and image_path and os.path.exists(image_path):
        timestamp = int(time.time())
        img_name = f"simple_jp_reader_{timestamp}.png"
        
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
            "allowDuplicate": False,
            "duplicateScope": "deck"
        },
        "tags": ["simple-jp-reader"]
    }

    return invoke("addNote", note=note)