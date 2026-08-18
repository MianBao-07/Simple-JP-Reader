import os
import json
import glob
import re
import html
import sqlite3

def flatten_structured_content(node):
    if isinstance(node, str):
        return html.escape(node)
    elif isinstance(node, list):
        return "".join(flatten_structured_content(n) for n in node)
    elif isinstance(node, dict):
        tag = node.get("tag", "span")
        if tag in ["rt", "rp"]:
            return ""
        res = ""
        if "content" in node:
            res += flatten_structured_content(node["content"])
        if "text" in node:
            res += flatten_structured_content(node["text"])
            
        if tag == "br":
            return "<br>"
        elif tag in ["div", "p", "span", "ul", "ol", "li", "b", "i", "strong", "em", "table", "tr", "td", "th"]:
            if tag in ["ul", "ol"]:
                return f"<{tag} style='margin-top: 2px; margin-bottom: 2px;'>{res}</{tag}>"
            return f"<{tag}>{res}</{tag}>"
        else:
            return f"<span>{res}</span>"
    return ""

def build_database():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Setup SQLite Database
    db_path = os.path.join(base_dir, "dictionary.db")
    
    # Ensure the folder exists
    if not os.path.exists(os.path.dirname(db_path)):
        os.makedirs(os.path.dirname(db_path))
        
    print(f"Creating database at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Drop existing table to start fresh
    cursor.execute('DROP TABLE IF EXISTS words')
    
    # Create the table
    cursor.execute('''
        CREATE TABLE words (
            term TEXT,
            reading TEXT,
            dict_name TEXT,
            html_content TEXT,
            pitch_drop INTEGER,
            freq TEXT
        )
    ''')
    
    cursor.execute('CREATE INDEX idx_term ON words(term)')

    # --- PRE-LOAD PITCH ACCENTS ---
    pitch_data = {}
    pitch_folder = os.path.join(base_dir, "dictionaries", "pitch")
    pitch_files = glob.glob(os.path.join(pitch_folder, "term_meta_bank_*.json"))
    
    if pitch_files:
        print(f"Found {len(pitch_files)} Pitch Accent files. Loading into memory...")
        for pf in pitch_files:
            with open(pf, 'r', encoding='utf-8') as f:
                meta_bank = json.load(f)
                for entry in meta_bank:
                    # Yomichan pitch meta format: [term, "pitch", {data}]
                    if len(entry) >= 3 and entry[1] == "pitch":
                        term = entry[0]
                        meta_info = entry[2]
                        if isinstance(meta_info, dict) and "pitches" in meta_info:
                            pitches = meta_info["pitches"]
                            if len(pitches) > 0 and "position" in pitches[0]:
                                pitch_drop = int(pitches[0]["position"])
                                reading = meta_info.get("reading", "")

                                # converts katakana to hiragana to match jitendex
                                normalized_reading = "".join(
                                        chr(ord(c) - 96) if 12449 <= ord(c) <= 12534 else c for c in reading
                                    )
                                
                                # Store by (term, reading) for accuracy, and term as fallback
                                pitch_data[(term, reading)] = pitch_drop
                                if term not in pitch_data:
                                    pitch_data[term] = pitch_drop

        print(f"  -> Successfully mapped {len(pitch_data):,} pitch accents.")
    else:
        print("No Pitch Accent files found in 'dictionaries/pitch/'. Defaulting all pitch drops to 0.")


    # --- LOAD DEFINITIONS & MERGE ---
    dict_path = os.path.join(base_dir, "dictionaries", "jitendex")
    term_files = glob.glob(os.path.join(dict_path, "term_bank_*.json"))
    
    if not term_files:
        print(f"No dictionary files found in {dict_path}.")
        conn.close()
        return

    print(f"Found {len(term_files)} files. Parsing and inserting...")

    # Parse and Insert Data
    total_entries = 0
    dict_name = "Jitendex"
    
    for file_path in term_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            term_bank = json.load(f)
            batch_data = []
            
            for entry in term_bank:
                term = entry[0]
                reading = entry[1]
                meanings_raw = entry[5]

                # Try to find the exact pitch drop from the pre-loaded data, fallback to 0
                pitch_drop = pitch_data.get((term, reading), pitch_data.get(term, 0))
                
                extracted_meanings = []
                for m in meanings_raw:
                    if isinstance(m, str):
                        extracted_meanings.append(m)
                    elif isinstance(m, dict) or isinstance(m, list):
                        parsed = flatten_structured_content(m).strip()
                        if parsed:
                            extracted_meanings.append(parsed)
                
                if not extracted_meanings:
                    extracted_meanings.append("Definition parsing failed.")

                meaning_text = "\n\n".join(extracted_meanings).strip()
                meaning_text = re.sub(r'\n{3,}', '\n\n', meaning_text)
                meaning_text = re.sub(r' +', ' ', meaning_text)

                # Prepare the row for insertion
                batch_data.append((term, reading, dict_name, meaning_text, pitch_drop, "Offline DB"))
                total_entries += 1
            
            cursor.executemany('''
                INSERT INTO words (term, reading, dict_name, html_content, pitch_drop, freq) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', batch_data)
            
            print(f"  Processed {os.path.basename(file_path)}...")

    conn.commit()
    conn.close()
    print(f"\nSuccessfully packed {total_entries:,} words into database.")

if __name__ == "__main__":
    build_database()