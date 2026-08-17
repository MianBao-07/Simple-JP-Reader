from manga_ocr import MangaOcr
from janome.tokenizer import Tokenizer
from PIL import Image, ImageOps

print("Booting up X-Ray Lens... (Loading AI models)")
mocr = MangaOcr()
tokenizer = Tokenizer()

def extract_words(img):
    print("Processing via AI...")
    
    # 1. Grayscale & Upscale
    img = img.convert('L')
    new_size = (img.width * 3, img.height * 3)
    img = img.resize(new_size, Image.Resampling.LANCZOS)
    
    # 2. Dynamic Padding
    bg_color = img.getpixel((0, 0))
    img = ImageOps.expand(img, border=30, fill=bg_color)
    
    # 3. OCR Recognition
    text = mocr(img)
    print(f"Raw OCR Output: {text}")
    
    # 4. Tokenization & Lemmatization
    tokens = tokenizer.tokenize(text)
    
    word_data = []
    for token in tokens:
        surface = token.surface
        # If Janome cannot determine a base form, it returns '*'
        base_form = token.base_form if token.base_form != '*' else surface
        
        # --- NEW: Returning a dictionary instead of a plain string ---
        word_data.append({
            "surface": surface,
            "base_form": base_form,
            "pos": token.part_of_speech.split(',')[0] 
        })
        
    return word_data