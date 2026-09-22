import os
import base64
import PIL.Image

# genai and openai are imported lazily inside fix_japanese_ocr to keep startup instantaneous

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def fix_japanese_ocr(image_path, current_text, engine="google", api_key="", base_url="", vision_model=""):
    if not image_path or not os.path.exists(image_path):
        return "Error: Image file not found for AI Fix."

    prompt = (
        f"You are an expert Japanese OCR assistant. Here is an image of Japanese text, "
        f"and a flawed OCR attempt: '{current_text}'. "
        f"Please read the image carefully and reply with ONLY the perfectly corrected Japanese text. "
        f"Do not include any English, explanations, quotes, or markdown formatting."
    )

    engine_key = engine.lower().strip()

    if engine_key == "google":
        if not api_key:
            return "Error: Gemini API Key missing. Please provide it in Settings."
        try:
            from google import genai
        except ImportError:
            return "Error: google-genai package not installed."
        try:
            client = genai.Client(api_key=api_key)
            img = PIL.Image.open(image_path)
            model_to_use = vision_model.strip() if vision_model else "gemini-2.5-flash"
            response = client.models.generate_content(
                model=model_to_use,
                contents=[prompt, img]
            )
            return response.text.strip()
        except Exception as e:
            return f"Gemini Error: {e}"

    elif engine_key in ["nvidia", "local"]:
        try:
            from openai import OpenAI
        except ImportError:
            return "Error: OpenAI library not installed."
        
        effective_base_url = base_url.strip() if base_url else ""
        if engine_key == "nvidia":
            if not api_key:
                return "Error: NVIDIA API Key missing."
            if not effective_base_url:
                effective_base_url = "https://integrate.api.nvidia.com/v1"
            effective_model = vision_model.strip() if vision_model else "meta/llama-3.2-90b-vision-instruct"
        else: # local
            if not effective_base_url:
                effective_base_url = "http://localhost:11434/v1"
            effective_model = vision_model.strip() if vision_model else "llama3.2-vision"

        try:
            client = OpenAI(api_key=api_key or "sk-local", base_url=effective_base_url)
            base64_image = encode_image(image_path)
            
            response = client.chat.completions.create(
                model=effective_model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                temperature=0.1
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Vision API Error: {e}"
            
    return current_text