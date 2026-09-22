import os
import re
import base64
import requests
import time
from model import get_tokenizer

ANKI_URL = "http://127.0.0.1:8765"

def generate_html_ruby(text):
    """Generates standard HTML ruby tags with smart Okurigana separation."""
    tokenizer = get_tokenizer()
    tokens = tokenizer.tokenize(text)
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

def clean_term(html_val):
    if not html_val:
        return ""
    # Strip HTML ruby pronunciation (<rt>...</rt>) first
    text = re.sub(r'<rt>.*?</rt>', '', html_val, flags=re.DOTALL)
    # Strip all remaining HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Strip bracket furigana e.g. 見[み]え -> 見え
    text = re.sub(r'\[[^\]]+\]', '', text)
    # Remove HTML entities like &nbsp;
    text = text.replace('&nbsp;', ' ').strip()
    return text

def check_card_exists(deck_name, term, base_form=None, custom_map=None):
    """
    Checks whether a note specifically targeting the term/base_form already exists in the deck.
    Only matches against target vocabulary fields, preventing false positives from context sentences or definitions.
    """
    if not term and not base_form:
        return False

    terms = list(dict.fromkeys([t for t in (term, base_form) if t]))
    custom_map = custom_map or {}
    term_field = custom_map.get("term") or custom_map.get("word")

    candidate_ids = set()
    for t in terms:
        # Build wildcard query (e.g., *見*え* to match across potential ruby tags in the field)
        w = "*" + "*".join(list(t)) + "*"
        if term_field:
            query = f'deck:"{deck_name}" "{term_field}:{w}"' if deck_name else f'"{term_field}:{w}"'
        else:
            query = f'deck:"{deck_name}" "{w}"' if deck_name else f'"{w}"'
        res = invoke("findNotes", query=query)
        if isinstance(res, list):
            candidate_ids.update(res)

    if not candidate_ids:
        return False

    # Fetch candidate notes to inspect their actual field contents
    notes = invoke("notesInfo", notes=list(candidate_ids))
    if not isinstance(notes, list):
        return False

    common_term_fields = [
        "VocabWord", "Expression", "Word", "Vocabulary-Kanji",
        "Vocabulary", "Kanji", "Japanese", "Front", "Term", "Text"
    ]

    for note in notes:
        fields = note.get("fields", {})
        # If user mapped a specific term field, check that field
        if term_field and term_field in fields:
            val = clean_term(fields[term_field].get("value", ""))
            if any(val == t for t in terms):
                return True
        else:
            # Check likely term fields
            checked_any = False
            for fname in common_term_fields:
                if fname in fields:
                    checked_any = True
                    val = clean_term(fields[fname].get("value", ""))
                    if any(val == t for t in terms):
                        return True
            # If none of the common field names existed on this note,
            # inspect non-sentence / non-definition fields as fallback
            if not checked_any:
                for fname, fobj in fields.items():
                    if any(skip in fname.lower() for skip in ("sentence", "context", "meaning", "definition", "glossary", "dialogue", "image", "screenshot", "audio", "sound")):
                        continue
                    val = clean_term(fobj.get("value", ""))
                    if any(val == t for t in terms):
                        return True

    return False

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