# Simple-JP-Reader (Alpha Stage)

A lightweight, customizable Japanese OCR and reading assistant tool built with Python and PyQt6. Simply press a hotkey to snip a section of your screen, and the app will instantly extract the Japanese text, de-conjugate verbs, and provide dictionary definitions.

After experimenting with a handful of Japanese-learning apps myself, I dedicated this personal project to making something free, simple, and customizable to my needs, which not a lot of commercial apps provide.

## features

* **Dual-Mode Screen Snipping:**
  * **Quick Snip (Alt):** Freeze the screen, click and drag over any dialogue box, subtitle, or web page to immediately run OCR.
  * **Manual Adjustment Snip (Ctrl + Alt):** Freeze the screen and adjust 4 corner handles with mouse drag to correct perspective or capture angled text boxes in games. Press Enter to process or Esc to cancel.
* **Smart OCR Preprocessing:** Uses OpenCV to clean up, normalize, denoise, and resize captured text before recognition to dramatically improve OCR accuracy on tricky game backgrounds.
* **AI OCR Fix:** When stylized fonts or artistic game logos cause OCR mistakes, one click sends the screenshot to a vision model (Google Gemini, NVIDIA NIM, or a local vision LLM) to return corrected Japanese text.
* **De-inflection & Grammar Breakdown:** Uses Janome tokenization combined with official Yomitan de-inflection rules to strip multiple layers of conjugations (e.g., 食べたくなかった -> 食べる) and display the exact conjugation chain.
* **Offline Yomitan Dictionaries & SQLite Storage:**
  * Import local Yomitan dictionary zip archives directly through the UI.
  * Supports Term dictionaries, Kanji dictionaries, Pitch Accent dictionaries, and Frequency dictionaries.
  * Stored in an indexed SQLite database for instant, offline lookups.
  * Enable, disable, or delete dictionaries on the fly.
* **Dynamic Pitch Accent Graphs:** Draws pitch contours dynamically (Heiban, Atamadaka, Nakadaka, Odaka) based on pitch drop data from your installed dictionaries.
* **Online Fallback:** If a word is not found in your offline dictionaries, the app automatically falls back to the Jisho.org API for definitions, readings, and JLPT levels.
* **Built-in Translation:** Translate sentences directly inside the reader using Google Translate, DeepL, NVIDIA NIM, or local LLMs (Ollama / LM Studio).
* **Hover Dictionary Preview:** Hover over any segmented word in the overlay to view an instant preview popup with its reading and definition without needing to expand the entry.
* **AnkiConnect Integration & Duplicate Detection:** Export mined words directly into your Anki deck with one click:
  * Automatically detects whether a word already exists in your target Anki deck, indicating duplicate cards with a gold star badge.
  * Generates clean HTML ruby furigana tags automatically.
  * Highlights the target word within the sentence context.
  * Attaches the cropped screenshot to your chosen card field.
  * Configurable field mapping and custom CSS styling for card templates.
* **System Tray Minimization:** Closing the workspace window minimizes the app to the Windows system tray so shortcuts stay ready in the background without taskbar clutter.
* **Click-to-Copy History:** A dedicated history tab logs your snips. Click any sentence to copy it to your clipboard.

## how the program improves ocr reading

Raw game screenshots, visual novel text boxes, and manga panels frequently fail when fed directly into standard OCR engines due to low resolutions, complex background textures, transparent text boxes, color clashing, and perspective distortion.

Simple-JP-Reader runs every snip through an automated multi-stage image processing pipeline before feeding it to MangaOCR:

1. **Perspective Correction & Warping:**
   In manual snip mode, the four corner points you adjust are transformed using OpenCV perspective transform (`getPerspectiveTransform` and `warpPerspective`) into a flattened rectangular image, eliminating slanted or angled text distortion.
2. **High-DPI Coordinate Normalization:**
   Screen captures are automatically mapped between Qt's logical interface coordinates and physical display pixels, ensuring snips taken on 125%, 150%, or 200% Windows display scaling are not offset or cropped incorrectly.
3. **Bicubic Upscaling (2.5x):**
   Small text in games and manga often lacks stroke definition for intricate kanji. The cropped image is upscaled by 2.5x using bicubic interpolation to widen character gaps and clarify individual kanji strokes.
4. **Automatic Polarity Inversion:**
   MangaOCR works best on dark text over light backgrounds. The pipeline samples the perimeter border pixels of the snip to estimate the average background brightness. If the background is dark (average brightness < 127), the image is inverted automatically so that light text on dark backgrounds becomes readable black-on-white text.
5. **Contrast Limited Adaptive Histogram Equalization (CLAHE):**
   Rather than applying global contrast adjustments which can blow out highlights or wash out text, CLAHE enhances contrast locally across small grid tiles. This keeps characters legible even when text passes over bright-to-dark gradient backgrounds.
6. **Bilateral Filtering (Edge-Preserving Denoising):**
   A bilateral filter is applied to smooth out background noise, compression artifacts, and texture grain while keeping character edges sharp and intact.
7. **Dynamic White Margin Padding:**
   A 30-pixel white border is appended around the processed image to ensure no character edges are clipped against the frame boundary, matching the expected input format of MangaOCR.
8. **AI Vision Model Fallback (AI Fix):**
   For text that is too stylized, hand-drawn, or obscured for local OCR, the "AI Fix" button passes the preprocessed snip to a vision model (Gemini 2.5 Flash, Llama 3.2 Vision, etc.) with a prompt to transcribe only the verified Japanese text.

## installation

1. Clone the repository:
```bash
git clone https://github.com/MianBao-07/Simple-JP-Reader.git
cd Simple-JP-Reader
```

2. Create and activate a Python virtual environment:
```bash
python -m venv venv
venv\Scripts\activate
```

3. Install the required dependencies:
```bash
pip install -r requirements.txt
```

4. Launch the application:
* Double-click **`Simple-JP-Reader.exe`** in the root folder to start the app silently without a background terminal window.
* Or run **`run.bat`** if you prefer to see terminal logs and debug output.
* Or run manually via Python:
```bash
python src/main.py
```

## controls

* **Quick Snip (Default: Alt):** Freeze the screen, click and drag to select a region. Release to process.
* **Manual Adjustment Snip (Default: Ctrl + Alt):** Drag to create a box, then drag individual corner points to adjust the bounding shape.
* **Enter (in Manual Mode):** Confirm and process the selected region.
* **Escape (While Snipping):** Cancel the current snip.
* **System Tray:** Left-click or double-click the system tray icon to show or hide the workspace window. Right-click the tray icon to trigger snips or exit the application.

## configuration & settings

All settings are configurable through the Settings tab in the main workspace window or stored in `src/config.json`:

* **Capture & OCR Engine:**
  * Choose between **MangaOCR (Local AI)** for manga and stylized font reading or **Windows Native OCR (Fast)** for lightweight, rapid text extraction.
  * Adjust screen dimming and toggle auto-copying to clipboard upon snip.
* **Snipping Modes & Keybindings:**
  * Toggle Quick Snip and Manual Adjustment Snip independently via checkboxes.
  * When a snip mode is unchecked, its keybind dropdown is automatically disabled and grayed out.
  * Select custom keybindings for both snip modes (Alt, F2, F3, F4, Ctrl+Shift+S, Ctrl+Space, Ctrl+Alt, Shift+Alt, etc.).
  * Toggle system tray minimization on close.
* **AI & Translation Backend:**
  * Select your preferred engine: Google, NVIDIA NIM, DeepL, or Local LLM (Ollama / LM Studio).
  * Configure API keys, local base URLs (e.g., `http://localhost:11434/v1`), and custom vision/text model names.
  * Toggle AI OCR Fix and Translation independently.
* **Dictionary Display:**
  * Toggle pitch accent graphs, frequency tags, and JLPT level badges on or off.
* **AnkiConnect:**
  * Connect to Anki and fetch your note type fields automatically.
  * Map term, reading, definition, sentence, and screenshot image to your custom note fields.
  * Customize dictionary card CSS styling directly within the app.
