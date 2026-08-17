import os
import json
import glob
import requests
import re

# --- GLOBAL CACHE ---
LOCAL_DICT = {}
DICT_LOADED = False

# --- NEW: MASTER TOGGLE ---
ENABLE_OFFLINE_DICT = False # Change to True later when you want to resume testing

def flatten_structured_content(node):
    """
    Recursively digs through Yomitan's complex JSON nodes.
    Processes children FIRST, then applies formatting to prevent empty bullets.
    """
    if isinstance(node, str):
        return node
    elif isinstance(node, list):
        return "".join(flatten_structured_content(n) for n in node)
    elif isinstance(node, dict):
        tag = node.get("tag", "")
        
        # Completely skip furigana readings (rt) and ruby parentheses (rp)
        if tag in ["rt", "rp"]:
            return ""
            
        # 1. Process the contents of the tag FIRST
        res = ""
        if "content" in node:
            res += flatten_structured_content(node["content"])
        if "text" in node:
            res += flatten_structured_content(node["text"])
            
        # 2. Apply formatting to the processed text
        if tag == "li":
            if res.strip():
                return f"\n• {res}"
            return ""
            
        elif tag == "br":
            return "\n"
            
        elif tag in ["div", "p"]:
            return f"{res}\n"
            
        elif tag == "span":
            return f"{res} "
            
        return res
    return ""


def load_local_dictionary():
    global LOCAL_DICT, DICT_LOADED
    
    # --- NEW: Check the master toggle before loading ---
    if not ENABLE_OFFLINE_DICT or DICT_LOADED: 
        return
        
    print("\n[Dictionary] Checking for offline Yomichan dictionaries...")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dict_path = os.path.join(base_dir, "dictionaries", "jitendex")
    
    if not os.path.exists(dict_path):
        print(f"[Dictionary] No offline folder found at: {dict_path}")
        DICT_LOADED = True
        return

    term_files = glob.glob(os.path.join(dict_path, "term_bank_*.json"))
    
    if not term_files:
        print("[Dictionary] Folder found, but no 'term_bank_*.json' files inside.")
        DICT_LOADED = True
        return

    print(f"[Dictionary] Found {len(term_files)} offline files. Loading into memory (this takes a few seconds)...")
    
    for file_path in term_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            term_bank = json.load(f)
            
            for entry in term_bank:
                term = entry[0]
                reading = entry[1]
                meanings_raw = entry[5]
                
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

                if term not in LOCAL_DICT:
                    LOCAL_DICT[term] = {
                        "pitch": reading,
                        "freq": "Offline DB", 
                        "meaning": meaning_text
                    }
                else:
                    if meaning_text not in LOCAL_DICT[term]["meaning"]:
                        LOCAL_DICT[term]["meaning"] += f"\n\n--- Also: ---\n{meaning_text}"
                    
    print(f"[Dictionary] Success! Loaded {len(LOCAL_DICT):,} words into memory.")
    DICT_LOADED = True


def get_real_data(lookup_term, fallback_term=None):
    # This function call will now hit the toggle and exit immediately
    load_local_dictionary()
    
    data = {
        "pitch": "???", 
        "freq": "Rare", 
        "meaning": "Definition not found."
    }
    
    terms_to_try = [lookup_term]
    if fallback_term and fallback_term != lookup_term:
        terms_to_try.append(fallback_term)

    # Because LOCAL_DICT is empty, this offline check will gracefully skip
    for term in terms_to_try:
        if term in LOCAL_DICT:
            print(f"-> Found '{term}' instantly via Offline Dictionary.")
            return LOCAL_DICT[term]

    # The code will naturally fall through to your working Jisho API logic
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