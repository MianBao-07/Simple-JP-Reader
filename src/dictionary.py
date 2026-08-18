import os
import json
import glob
import requests
import re
import html

# --- GLOBAL CACHE ---
LOCAL_DICT = {}
DICT_LOADED = False

# MASTER TOGGLE
ENABLE_OFFLINE_DICT = True # Change to True later when testing

def flatten_structured_content(node):
    if isinstance(node, str):
        # Escape raw text so accidental symbols don't break the HTML
        return html.escape(node)
        
    elif isinstance(node, list):
        # If it's a list, parse every item and glue the HTML together
        return "".join(flatten_structured_content(n) for n in node)
        
    elif isinstance(node, dict):
        # Default to a generic span if the dictionary doesn't specify a tag
        tag = node.get("tag", "span")
        
        # PyQt6 doesn't support HTML <ruby> tags natively, so we hide the furigana 
        # (rt/rp) to prevent the kanji from looking cluttered
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
            # Small tweak to make lists look a bit tighter in the UI
            if tag in ["ul", "ol"]:
                return f"<{tag} style='margin-top: 2px; margin-bottom: 2px;'>{res}</{tag}>"
            return f"<{tag}>{res}</{tag}>"
        else:
            # Fallback for unrecognized Yomitan-specific tags (like 'ruby' or 'rb')
            return f"<span>{res}</span>"
            
    return ""


def load_local_dictionary():
    global LOCAL_DICT, DICT_LOADED
    
    # CHECKS MASTER TOGGLE FIRST
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
                        "meanings_list": [
                            {
                                "dict_name": "Jitendex",
                                "html_content": meaning_text 
                            }
                        ]
                    }
                else:
                    # Check if this exact meaning is already in the list to avoid duplicates
                    existing_meanings = [m["html_content"] for m in LOCAL_DICT[term]["meanings_list"]]
                    if meaning_text not in existing_meanings:
                        LOCAL_DICT[term]["meanings_list"].append({
                            "dict_name": "Jitendex",
                            "html_content": meaning_text
                        })
                    
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

    # Because LOCAL_DICT is empty, this offline check will skip
    for term in terms_to_try:
        if term in LOCAL_DICT:
            print(f"-> Found '{term}' instantly via Offline Dictionary.")
            return LOCAL_DICT[term]

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