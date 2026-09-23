import os
import tempfile
import cv2
import numpy as np
from janome.tokenizer import Tokenizer
from PIL import Image, ImageOps, ImageEnhance

_mocr = None
_tokenizer = None

def get_tokenizer():
    """Returns a shared Janome Tokenizer instance (singleton)."""
    global _tokenizer
    if _tokenizer is None:
        _tokenizer = Tokenizer()
    return _tokenizer

def get_ocr_engine():
    """Lazily loads and returns the MangaOcr engine instance."""
    global _mocr
    if _mocr is None:
        print("[OCR] Loading MangaOCR model (first-time init)...")
        from manga_ocr import MangaOcr
        _mocr = MangaOcr()
        print("[OCR] MangaOCR loaded successfully.")
    return _mocr

def tokenize_sentence(text):
    tokenizer = get_tokenizer()
    tokens = tokenizer.tokenize(text)
    word_data = []
    
    for token in tokens:
        surface = token.surface
        # If Janome cannot determine a base form, it returns '*'
        base_form = token.base_form if token.base_form != '*' else surface
        
        word_data.append({
            "surface": surface,
            "base_form": base_form,
            "pos": token.part_of_speech.split(',')[0] 
        })
        
    return word_data

def preprocess_image(pil_img, extract_color_range=None):
    if pil_img.mode != "RGB":
        pil_img = pil_img.convert("RGB")
    cv_img = np.array(pil_img)
    cv_img = cv2.cvtColor(cv_img, cv2.COLOR_RGB2BGR)

    if extract_color_range:
        # color isolating
        hsv = cv2.cvtColor(cv_img, cv2.COLOR_BGR2HSV)
        lower, upper = extract_color_range
        mask = cv2.inRange(hsv, lower, upper)
        processed_cv = cv2.bitwise_not(mask)
        processed_cv = cv2.resize(processed_cv, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        return Image.fromarray(processed_cv)

    # grayscale
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)

    # cubic interpolation with minimum dimension safety for CLAHE
    h, w = gray.shape
    if h == 0 or w == 0:
        return pil_img
    fx = max(2.5, 16.0 / max(1, w))
    fy = max(2.5, 16.0 / max(1, h))
    gray = cv2.resize(gray, None, fx=fx, fy=fy, interpolation=cv2.INTER_CUBIC)

    # polarity check
    h, w = gray.shape
    border_pixels = np.concatenate([gray[0, :], gray[-1, :], gray[:, 0], gray[:, -1]])
    avg_border_brightness = np.mean(border_pixels)

    if avg_border_brightness < 127:
        # bg is dark -> invert
        gray = cv2.bitwise_not(gray)

    # CLAHE
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    denoised = cv2.bilateralFilter(enhanced, d=5, sigmaColor=50, sigmaSpace=50)

    return Image.fromarray(denoised)

def run_windows_native_ocr(img):
    """Performs fast OCR using Windows built-in Japanese OCR engine."""
    try:
        import winocr
        res = winocr.recognize_pil_sync(img, 'ja')
        if isinstance(res, dict):
            raw_text = res.get("text", "")
            return raw_text.replace(" ", "")
        return ""
    except Exception as e:
        print(f"[OCR] Windows Native OCR error ({e}), falling back to MangaOCR...")
        ocr = get_ocr_engine()
        return ocr(img)

def extract_words(img, color_range=None, engine="manga_ocr"):
    # OpenCV Preprocessing
    img = preprocess_image(img, extract_color_range=color_range)

    # Dynamic Padding
    img = ImageOps.expand(img, border=30, fill='white')

    debug_path = os.path.join(tempfile.gettempdir(), "debug_preprocessed_snip.png")
    try:
        img.save(debug_path)
    except Exception:
        pass
    
    # OCR Recognition
    if engine == "windows_native":
        print("[OCR] Processing via Windows Native OCR...")
        text = run_windows_native_ocr(img)
    else:
        print("[OCR] Processing via MangaOCR...")
        ocr = get_ocr_engine()
        text = ocr(img)

    print(f"Raw OCR Output: {text}")
    
    return tokenize_sentence(text)