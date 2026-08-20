import requests

def translate_text(text, engine="google", api_key=""):
	if not text or not text.strip():
		return ""

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
			return response.json()["translations"][0]["text"]
		except Exception as e:
			return f"DeepL API Error: {e}"

	elif engine.lower() == "google":
		url = "https://translate.googleapis.com/translate_a/single"
		params = {
			"client": "gtx", 
			"sl": "ja", 
			"tl": "en", 
			"dt": "t", 
			"q": text
		}
		try:
			response = requests.get(url, params=params, timeout=5)
			response.raise_for_status()

			data = response.json()
			translated_text = "".join([segment[0] for segment in data[0]])
			return translated_text
		except Exception as e:
			return f"Google Translate Error: {e}"

	return "Unknown translation engine detected."