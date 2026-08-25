import requests
from deep_translator import GoogleTranslator

# global cache
TRANSLATION_CACHE = {}

def translate_text(text, engine="google", api_key=""):
    if not text or not text.strip():
        return ""

    cache_key = f"{engine}_{text}"
    if cache_key in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[cache_key]

    translated_text = ""

    # --- DEEPL ---
    if engine.lower() == "deepl":
        if not api_key:
            return "Error: DeepL API key is missing."

        url = "https://api-free.deepl.com/v2/translate"
        params = {
            "auth_key": api_key, 
            "text": text, 
            "target_lang": "EN"
        }
        try:
            response = requests.post(url, data=params, timeout=5)
            response.raise_for_status()
            translated_text = response.json()["translations"][0]["text"]
        except Exception as e:
            return f"DeepL API Error: {e}"

    # --- NVIDIA ---
    elif engine.lower() == "nvidia":
        if not api_key:
            return "Error: NVIDIA API key is missing."
            
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "meta/llama-3.1-70b-instruct",
            "messages": [
                {"role": "system", "content": "You are an expert Japanese to English translator for video games and manga. Reply ONLY with the English translation. Do not include explanations, quotes, or conversational filler."},
                {"role": "user", "content": text}
            ],
            "temperature": 0.3,
            "max_tokens": 150
        }
        
        try:
            # 10s timeout
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            translated_text = response.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.Timeout:
            return "NVIDIA API Error: Connection timed out. The server might be busy."
        except Exception as e:
            return f"NVIDIA API Error: {e}"

    # --- GOOGLE TRANSLATE ---
    elif engine.lower() == "google":
        try:
            translated_text = GoogleTranslator(source='ja', target='en').translate(text)
        except Exception as e:
            return f"Google Translate Error: {e}"

    else:
        return "Unknown translation engine detected."

    if translated_text and not "Error:" in translated_text:
        TRANSLATION_CACHE[cache_key] = translated_text

    return translated_text