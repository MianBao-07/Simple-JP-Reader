import cv2
import numpy as np
from manga_ocr import MangaOcr
from janome.tokenizer import Tokenizer
from PIL import Image, ImageOps, ImageEnhance

print("Booting up Simple JP Reader...")
mocr = MangaOcr()
tokenizer = Tokenizer()

def tokenize_sentence(text):
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

    # cubic interpolation
    gray = cv2.resize(gray, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)

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

def extract_words(img, color_range=None):
    print("Processing via AI...")
    
    # OpenCV Preprocessing
    img = preprocess_image(img, extract_color_range=color_range)

    # Dynamic Padding
    img = ImageOps.expand(img, border=30, fill='white')

    img.save("debug_preprocessed_snip.png")
    
    # OCR Recognition
    text = mocr(img)
    print(f"Raw OCR Output: {text}")
    
    return tokenize_sentence(text)