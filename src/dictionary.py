import os
import json
import requests
import sqlite3

from pathlib import Path
from deinflect import get_base_forms

# Enable or disable dictionaries
ENABLE_OFFLINE_DICT = True 

# Point to the SQLite file
DB_PATH = os.path.join(os.path.dirname(__file__), "dictionary.db")

ENABLED_DICTIONARIES = set()

def set_dictionary_enabled(dict_title, is_enabled):
    if is_enabled:
        ENABLED_DICTIONARIES.add(dict_title)
    else:
        ENABLED_DICTIONARIES.discard(dict_title)

def parse_yomitan_content(node):
    """Recursively flattens Yomitan structured content into clean, styled HTML."""
    if isinstance(node, str):
        return node
    elif isinstance(node, list):
        return "".join(parse_yomitan_content(n) for n in node)
    elif isinstance(node, dict):
        tag = node.get("tag", "span")
        content = node.get("content", node.get("text", ""))
        
        parsed = parse_yomitan_content(content)
        
        # 1. GRAMMAR BADGES (e.g., adverb, noun)
        is_tag = False
        if isinstance(node.get("data"), dict) and node["data"].get("class") == "tag":
            is_tag = True
            
        if is_tag:
            # PyQt doesn't support padding well on spans, so we fake it with &nbsp;
            return f'<span style="background-color: #374151; color: #93C5FD;">&nbsp;{parsed}&nbsp;</span>&nbsp;'
            
        # 2. FURIGANA FORMATTING
        if tag == "rt":
            # Subdued gray color, slightly smaller
            return f'<span style="color: #9CA3AF; font-size: 0.85em;">({parsed})</span>'
        elif tag == "ruby":
            return f'<span style="margin-right: 2px;">{parsed}</span>'
            
        # 3. LINE BREAKS
        elif tag == "br":
            return "<br>"
            
        # 4. BLOCK ELEMENTS & EXAMPLES
        elif tag == "div":
            is_example = isinstance(node.get("data"), dict) and "example" in str(node["data"])
            if is_example:
                # Indent examples, turn them gray, and italicize them
                return f'<div style="color: #9CA3AF; margin-left: 20px; margin-top: 4px; margin-bottom: 8px;"><i>{parsed}</i></div>'
            return f'<div style="margin-top: 2px; margin-bottom: 2px;">{parsed}</div>'
            
        # 5. LIST FORMATTING
        elif tag == "ul":
            return f'<ul style="margin-top: 4px; margin-bottom: 4px; padding-left: 15px;">{parsed}</ul>'
        elif tag == "li":
            return f'<li style="margin-bottom: 6px;">{parsed}</li>'
            
        # 6. STANDARD TAGS
        elif tag in ["span", "p", "b", "strong", "i", "em"]:
            return f"<{tag}>{parsed}</{tag}>"
        else:
            return parsed
            
    return str(node)

def init_local_dictionaries_to_db():
    """Scans the 'dictionaries' folder and auto-imports Yomitan JSONs into SQLite."""
    dict_root = Path(os.getcwd()) / "dictionaries"
    if not dict_root.exists():
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create tables for Terms, Pitch Accents, and Frequencies
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS words (
            term TEXT, reading TEXT, dict_name TEXT, html_content TEXT, pitch_drop INTEGER, freq TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meta_pitch (
            term TEXT, reading TEXT, dict_name TEXT, pitch_drop INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS meta_freq (
            term TEXT, reading TEXT, dict_name TEXT, freq_value TEXT
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_words_term ON words(term)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_meta_pitch_term ON meta_pitch(term)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_meta_freq_term ON meta_freq(term)")

    conn.commit()
    conn.commit()

    for sub_dir in dict_root.iterdir():
        if not sub_dir.is_dir():
            continue

        index_path = sub_dir / "index.json"
        if not index_path.exists():
            continue

        dict_title = sub_dir.name

        # Check all tables to see if this dictionary is already indexed
        cursor.execute("SELECT COUNT(*) FROM words WHERE dict_name = ?", (dict_title,))
        c1 = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM meta_pitch WHERE dict_name = ?", (dict_title,))
        c2 = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM meta_freq WHERE dict_name = ?", (dict_title,))
        c3 = cursor.fetchone()[0]

        if c1 + c2 + c3 > 0:
            continue

        print(f"[Dictionary] Indexing local dictionary: {dict_title}...")
        
        for file_path in sub_dir.glob("*.json"):
            if file_path.name == "index.json":
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    bank_data = json.load(f)

                    # 1. Parse Term Banks
                    if "term_bank" in file_path.name:
                        for entry in bank_data:
                            if len(entry) >= 6:
                                expression, reading, glossary = entry[0], entry[1], entry[5]
                                
                                html_def = ""
                                if isinstance(glossary, list):
                                    html_def = "<ul>"
                                    for item in glossary:
                                        parsed = parse_yomitan_content(item)
                                        if parsed.strip():
                                            if parsed.startswith("<li"):
                                                html_def += parsed
                                            else:
                                                html_def += f"<li>{parsed}</li>"
                                    html_def += "</ul>"
                                else:
                                    html_def = f"<p>{parse_yomitan_content(glossary)}</p>"

                                cursor.execute(
                                    "INSERT INTO words (term, reading, dict_name, html_content, pitch_drop, freq) VALUES (?, ?, ?, ?, ?, ?)",
                                    (expression, reading, dict_title, html_def, 0, "Installed")
                                )

                    # 2. Parse Kanji Banks
                    elif "kanji_bank" in file_path.name:
                        for entry in bank_data:
                            if len(entry) >= 5:
                                kanji_char, onyomi, kunyomi, meanings = entry[0], entry[1], entry[2], entry[4]

                                html_def = f"<p><b>Meanings:</b> {', '.join(meanings)}</p>" if isinstance(meanings, list) else f"<p>{meanings}</p>"
                                if onyomi: html_def += f"<p><b>On:</b> {' '.join(onyomi)}</p>"
                                if kunyomi: html_def += f"<p><b>Kun:</b> {' '.join(kunyomi)}</p>"

                                combined_reading = " ".join(onyomi + kunyomi)
                                cursor.execute(
                                    "INSERT INTO words (term, reading, dict_name, html_content, pitch_drop, freq) VALUES (?, ?, ?, ?, ?, ?)",
                                    (kanji_char, combined_reading, f"{dict_title} (Kanji)", html_def, 0, "Installed")
                                )

                    # 3. Parse Meta Banks (Pitch Accent & Frequency)
                    elif "term_meta_bank" in file_path.name:
                        for entry in bank_data:
                            if len(entry) >= 3:
                                term, mode, meta_info = entry[0], entry[1], entry[2]

                                if mode == "freq":
                                    reading = ""
                                    if isinstance(meta_info, dict):
                                        reading = meta_info.get("reading", "")
                                        freq_data = meta_info.get("frequency", meta_info)
                                        if isinstance(freq_data, dict):
                                            freq_val = str(freq_data.get("displayValue", freq_data.get("value", "Common")))
                                        else:
                                            freq_val = str(freq_data)
                                    else:
                                        freq_val = str(meta_info)

                                    cursor.execute(
                                        "INSERT INTO meta_freq (term, reading, dict_name, freq_value) VALUES (?, ?, ?, ?)",
                                        (term, reading, dict_title, freq_val)
                                    )

                                elif mode == "pitch":
                                    if isinstance(meta_info, dict) and "pitches" in meta_info:
                                        pitches = meta_info["pitches"]
                                        if len(pitches) > 0 and "position" in pitches[0]:
                                            pitch_drop = int(pitches[0]["position"])
                                            reading = meta_info.get("reading", "")
                                            cursor.execute(
                                                "INSERT INTO meta_pitch (term, reading, dict_name, pitch_drop) VALUES (?, ?, ?, ?)",
                                                (term, reading, dict_title, pitch_drop)
                                            )

            except Exception as e:
                print(f"[Dictionary] Error parsing {file_path.name}: {e}")

        conn.commit()
    conn.close()

def query_sqlite(term):
    if not os.path.exists(DB_PATH):
        return None

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cursor = conn.cursor()

        # 1. Fetch meanings
        cursor.execute("SELECT reading, dict_name, html_content FROM words WHERE term = ?", (term,))
        rows = cursor.fetchall()
        
        filtered_rows = [row for row in rows if row[1] in ENABLED_DICTIONARIES or row[1].replace(" (Kanji)", "") in ENABLED_DICTIONARIES]
        
        if not filtered_rows:
            conn.close()
            return None

        # Base Data Object
        data = {
            "pitch_drop": 0,
            "freq": "Installed",
            "meanings_list": []
        }

        # 2. Fetch Pitch Overrides from active dictionaries
        cursor.execute("SELECT pitch_drop, dict_name FROM meta_pitch WHERE term = ?", (term,))
        for p_row in cursor.fetchall():
            if p_row[1] in ENABLED_DICTIONARIES:
                data["pitch_drop"] = p_row[0]
                break

        # 3. Fetch Freq Overrides from active dictionaries
        cursor.execute("SELECT freq_value, dict_name FROM meta_freq WHERE term = ?", (term,))
        for f_row in cursor.fetchall():
            if f_row[1] in ENABLED_DICTIONARIES:
                data["freq"] = f_row[0]
                break

        conn.close()

        # 4. Group Meanings and Collect Readings
        dict_groups = {}
        seen_meanings = set()
        readings = []

        for row in filtered_rows:
            reading, dict_name, html_content = row[0], row[1], row[2]
            
            # Collect unique readings (e.g., to catch both とうけい and とうきょう)
            if reading and reading not in readings:
                readings.append(reading)

            # Group the HTML content by dictionary name
            if html_content not in seen_meanings:
                seen_meanings.add(html_content)
                if dict_name not in dict_groups:
                    dict_groups[dict_name] = []
                dict_groups[dict_name].append(html_content)

        # Set the combined readings at the top of the UI
        data["pitch"] = " ・ ".join(readings) if readings else "???"

        # Assemble the final list so the UI only prints one badge per dictionary
        for d_name, contents in dict_groups.items():
            data["meanings_list"].append({
                "dict_name": d_name,
                "html_content": "".join(contents)
            })

        return data

    except Exception as e:
        print(f"[Dictionary] Database error: {e}")
        return None

def get_real_data(lookup_term, fallback_term=None):
    data = {
        "pitch": "???", 
        "pitch_drop": -1, 
        "freq": "Rare", 
        "jlpt": None,
        "meaning": "Definition not found.",
        "grammar": [] 
    }

    candidates = get_base_forms(lookup_term)
    
    if fallback_term and fallback_term != lookup_term:
        if not any(c["term"] == fallback_term for c in candidates):
            candidates.append({"term": fallback_term, "grammar_path": []})

    if ENABLE_OFFLINE_DICT:
        for candidate in candidates:
            term = candidate["term"]
            db_result = query_sqlite(term)
            if db_result:
                grammar_str = " + ".join(candidate["grammar_path"]) if candidate["grammar_path"] else "Base Form"
                print(f"-> Found '{term}' instantly via SQLite Database. [Grammar: {grammar_str}]")
                
                db_result["grammar"] = candidate["grammar_path"]
                return db_result

    print(f"-> '{lookup_term}' not found offline. Asking Jisho API...")
    
    terms_to_try = [lookup_term]
    if fallback_term and fallback_term != lookup_term:
        terms_to_try.append(fallback_term)

    for term in terms_to_try:
        if not term or not term.strip():
            continue
            
        try:
            url = f"https://jisho.org/api/v1/search/words?keyword={term}"
            response = requests.get(url, timeout=5)
            result = response.json()
            
            if result.get("data"):
                entry = result["data"][0]
                if entry.get("senses"):
                    data["meaning"] = "; ".join(entry["senses"][0].get("english_definitions", []))
                if entry.get("japanese"):
                    data["pitch"] = f"{entry['japanese'][0].get('reading', '')}"
                
                # --- Separate Frequency & JLPT ---
                data["freq"] = "Common" if entry.get("is_common", False) else "Rare"
                
                jlpt_list = entry.get("jlpt", [])
                if jlpt_list:
                    data["jlpt"] = jlpt_list[0].replace("jlpt-", "").upper()
                else:
                    data["jlpt"] = None
                
                break
        except requests.exceptions.RequestException:
            data["meaning"] = "Network error: Could not reach Jisho.org."
            break
            
    return data