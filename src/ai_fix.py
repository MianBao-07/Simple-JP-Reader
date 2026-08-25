import base64
import PIL.Image
from google import genai

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def fix_japanese_ocr(image_path, current_text, engine="google", api_key="", base_url="", vision_model=""):
    prompt = (
        f"You are an expert Japanese OCR assistant. Here is an image of Japanese text, "
        f"and a flawed OCR attempt: '{current_text}'. "
        f"Please read the image carefully and reply with ONLY the perfectly corrected Japanese text. "
        f"Do not include any English, explanations, quotes, or markdown formatting."
    )

    if engine == "google":
        if not api_key: return "Error: Gemini API Key missing."
        try:
            client = genai.Client(api_key=api_key)
            img = PIL.Image.open(image_path)
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=[prompt, img]
            )
            return response.text.strip()
        except Exception as e:
            return f"Gemini Error: {e}"

    elif engine in ["nvidia", "local"]:
        if not OpenAI: return "Error: OpenAI library not installed."
        if not vision_model: return "Error: Vision model name required."
        
        try:
            client = OpenAI(api_key=api_key or "sk-local", base_url=base_url)
            base64_image = encode_image(image_path)
            
            response = client.chat.completions.create(
                model=vision_model,
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