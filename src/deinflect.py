import json
import os
import urllib.request

DEINFLECT_PATH = os.path.join(os.path.dirname(__file__), "deinflect.json")
DEINFLECT_URL = "https://raw.githubusercontent.com/FooSoft/yomichan/master/ext/data/deinflect.json"

def load_rules():
    if not os.path.exists(DEINFLECT_PATH):
        print("Downloading official Yomitan deinflect.json.")
        try:
            urllib.request.urlretrieve(DEINFLECT_URL, DEINFLECT_PATH)
            print("Download complete.")
        except Exception as e:
            print(f"Failed to download deinflect.json: {e}")
            return []

    try:
        with open(DEINFLECT_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        reasons = data.get("reasons", [])
        raw_rules = data.get("rules", [])
        parsed_rules = []
        
        iterable_rules = raw_rules.values() if isinstance(raw_rules, dict) else raw_rules
        
        for rule in iterable_rules:
            reason_val = rule.get("reason")
            
            # Map the integer ID to the actual grammatical term (e.g., "Past", "Causative")
            if isinstance(reason_val, int) and reason_val < len(reasons):
                reason_str = reasons[reason_val]
            else:
                reason_str = str(reason_val)
                
            parsed_rules.append({
                "kana_in": rule.get("kanaIn", ""),
                "kana_out": rule.get("kanaOut", ""),
                "reason": reason_str
            })
            
        return parsed_rules
        
    except Exception as e:
        print(f"Error parsing deinflect.json: {e}")
        return []

RULES = load_rules()

def get_base_forms(word):
    results = [{"term": word, "grammar_path": []}]
    
    def search(current_word, current_path, depth):
        if depth > 3: # Most stacked conjugations rarely exceed 3 suffixes
            return
            
        for rule in RULES:
            # If the current word ends with the conjugated suffix
            if rule["kana_in"] and current_word.endswith(rule["kana_in"]):
                # Strip the suffix and append the dictionary ending
                base_guess = current_word[:-len(rule["kana_in"])] + rule["kana_out"]
                new_path = current_path + [rule["reason"]]
                
                results.append({"term": base_guess, "grammar_path": new_path})
                
                # Recursively check the new base form for further conjugations
                search(base_guess, new_path, depth + 1)
                
    search(word, [], 0)
    
    seen = set()
    unique_results = []
    for r in results:
        if r["term"] not in seen:
            seen.add(r["term"])
            unique_results.append(r)
            
    return unique_results