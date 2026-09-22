import requests
from deep_translator import GoogleTranslator

# global cache
TRANSLATION_CACHE = {}

def translate_text(text, engine="google", api_key="", base_url="", text_model=""):
    if not text or not text.strip():
        return ""

    engine_key = engine.lower().strip()
    cache_key = f"{engine_key}_{text_model}_{text}"
    if cache_key in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[cache_key]

    translated_text = ""

    # --- DEEPL ---
    if engine_key == "deepl":
        if not api_key:
            return "Error: DeepL API key is missing."

        url = "https://api-free.deepl.com/v2/translate"
        params = {
            "auth_key": api_key, 
            "text": text, 
            "target_lang": "EN"
        }
        try:
            response = requests.post(url, data=params, timeout=8)
            response.raise_for_status()
            translated_text = response.json()["translations"][0]["text"]
        except Exception as e:
            return f"DeepL API Error: {e}"

    # --- NVIDIA NIM ---
    elif engine_key == "nvidia":
        if not api_key:
            return "Error: NVIDIA API key is missing."
            
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        model_name = text_model.strip() if text_model else "meta/llama-3.1-70b-instruct"
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are an expert Japanese to English translator for video games and manga. Reply ONLY with the English translation. Do not include explanations, quotes, or conversational filler."},
                {"role": "user", "content": text}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=12)
            response.raise_for_status()
            translated_text = response.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.Timeout:
            return "NVIDIA API Error: Connection timed out. The server might be busy."
        except Exception as e:
            return f"NVIDIA API Error: {e}"

    # --- LOCAL LLM (Ollama / LM Studio / OpenAI-Compatible) ---
    elif engine_key == "local":
        target_url = (base_url.rstrip("/") if base_url else "http://localhost:11434/v1") + "/chat/completions"
        model_name = text_model.strip() if text_model else "llama3"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key or 'sk-local'}"
        }
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are an expert Japanese to English translator for video games and manga. Reply ONLY with the English translation. Do not include explanations, quotes, or conversational filler."},
                {"role": "user", "content": text}
            ],
            "temperature": 0.3,
            "max_tokens": 200
        }
        try:
            response = requests.post(target_url, headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            translated_text = response.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            return f"Local LLM Error: {e}"

    # --- GOOGLE TRANSLATE ---
    elif engine_key == "google":
        try:
            translated_text = GoogleTranslator(source='ja', target='en').translate(text)
        except Exception as e:
            return f"Google Translate Error: {e}"

    else:
        return f"Unknown translation engine: '{engine}'."

    if translated_text and "Error:" not in translated_text:
        TRANSLATION_CACHE[cache_key] = translated_text

    return translated_text