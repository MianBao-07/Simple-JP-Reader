import os
import requests
import sqlite3

# Enable or disable the offline database check
ENABLE_OFFLINE_DICT = True 

# Point to the SQLite file
DB_PATH = os.path.join(os.path.dirname(__file__), "dictionary.db")

def query_sqlite(term):
    """Searches the SQLite database for the exact term."""
    if not os.path.exists(DB_PATH):
        return None

    try:
        # Open in read-only mode for safety and speed
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Fetch all matching entries for this term
        cursor.execute("SELECT reading, dict_name, html_content, pitch_drop, freq FROM words WHERE term = ?", (term,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return None

        # Build the final dictionary object expected by the UI
        data = {
            "pitch": rows[0][0], # Use the reading from the first row
            "pitch_drop": rows[0][3],
            "freq": rows[0][4],
            "meanings_list": []
        }

        # Pack all definitions into the meanings list
        seen_meanings = set()
        for row in rows:
            dict_name = row[1]
            html_content = row[2]
            
            # Prevent duplicate entries if dictionaries overlap
            if html_content not in seen_meanings:
                seen_meanings.add(html_content)
                data["meanings_list"].append({
                    "dict_name": dict_name,
                    "html_content": html_content
                })

        return data

    except Exception as e:
        print(f"[Dictionary] Database error: {e}")
        return None


def get_real_data(lookup_term, fallback_term=None):
    # Default fallback object if everything fails
    data = {
        "pitch": "???", 
        "pitch_drop": 0, 
        "freq": "Rare", 
        "meaning": "Definition not found."
    }
    
    terms_to_try = [lookup_term]
    if fallback_term and fallback_term != lookup_term:
        terms_to_try.append(fallback_term)

    # 1. Offline SQLite Search
    if ENABLE_OFFLINE_DICT:
        for term in terms_to_try:
            db_result = query_sqlite(term)
            if db_result:
                print(f"-> Found '{term}' instantly via SQLite Database.")
                return db_result

    # 2. Jisho API Fallback
    print(f"-> '{lookup_term}' not found offline. Asking Jisho API...")
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
                    meanings = entry["senses"][0].get("english_definitions", [])
                    data["meaning"] = "; ".join(meanings)
                
                if entry.get("japanese"):
                    reading = entry["japanese"][0].get("reading", "")
                    data["pitch"] = f"{reading}"
                
                is_common = entry.get("is_common", False)
                jlpt = entry.get("jlpt", [])
                
                freq_tags = []
                if is_common: freq_tags.append("Common")
                if jlpt: freq_tags.append(jlpt[0].upper())
                
                if freq_tags:
                    data["freq"] = " | ".join(freq_tags)
                
                break

        except requests.exceptions.RequestException:
            data["meaning"] = "Network error: Could not reach Jisho.org."
            break
            
    return data