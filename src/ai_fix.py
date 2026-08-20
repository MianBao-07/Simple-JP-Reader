from google import genai
import PIL.Image

def fix_japanese_ocr(image_path, current_text, api_key=""):
    """
    Sends the snipped image and the flawed text to Gemini to reconstruct the exact Japanese sentence.
    """
    if not api_key:
        return "Error: Gemini API Key is missing."
    
    try:
        client = genai.Client(api_key=api_key)
        
        img = PIL.Image.open(image_path)
        prompt = (
            f"You are an expert Japanese OCR assistant. Here is an image of Japanese text, "
            f"and a flawed OCR attempt: '{current_text}'. "
            f"Please read the image carefully and reply with ONLY the perfectly corrected Japanese text. "
            f"Do not include any English, explanations, quotes, or markdown formatting."
        )
        
        # Use the recommended modern Flash model
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=[prompt, img]
        )
        
        return response.text.strip()
    
    except Exception as e:
        return f"AI Error: {e}"