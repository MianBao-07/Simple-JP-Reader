# Simple-JP-Reader (Alpha Stage)

A lightweight, customizable Japanese OCR and reading assistant tool built with Python and PyQt6. Simply press a hotkey to snip a section of your screen, and the app will instantly extract the Japanese text, de-conjugate verbs, and provide dictionary definitions.

After experimenting a handful of Japanese-learning apps myself, I have dedicated a little personal projects that is free, simple and customizable to my needs. Mostly inspired by ShareX's OCR and Yomitan's Popup Dictionary, I combined both into all-in-one, simplified app that works on desktop.

## ✨ Current Features

* **Instant Screen Snipping:** Press `Left Alt` to freeze the screen and snip any Japanese text.
* **High-Accuracy OCR:** Powered by MangaOCR for robust recognition of manga, games, and web text.
* **Smart Lemmatization:** Uses Janome to automatically detect and de-conjugate verbs to their dictionary base form (e.g., 食べたくない -> 食べる).
* **Live Dictionary Lookups:** Hooks directly into the Jisho.org API to pull definitions, readings, and word frequencies.
* **Click-to-Copy History:** A dedicated history tab logs your snips. Click any sentence to instantly copy it to your clipboard.
* **Draggable Overlay UI:** A sleek, transparent, non-intrusive interface that floats above your active windows.

## 🚀 Roadmap / Upcoming Features

- [ ] **Offline Dictionaries:** Support for Yomitan/Yomichan structured JSON dictionaries (Jitendex, JPDBv2, JMnedict) for instant, lag-free lookups. Works but really buggy.
- [ ] **Anki Integration:** One-click flashcard creation sending the base form, contextual sentence, and definition straight to an Anki deck.
- [ ] **"No Dim":** Transparent snipping mode that doesn't dim the screen.
- [ ] **Text-to-Speech (TTS):** Native audio playback to verify pitch accent and pronunciation.
- [ ] **Settings:** For full customizable features/add-ons.
- [ ] **Improved UI:** Make it absolute an absolute beauty, with different color scheme options.
- [ ] **Universal OCR:** Inspired by rtr46's universal ocr, (a.k.a. meikipop), will try to implement as a secondary OCR option.

## 🛠️ Installation & Usage (Developer Setup)

Currently, the app must be run via a Python environment.

```bash
git clone [https://github.com/MianBao-07/Simple-JP-Reader.git](https://github.com/MianBao-07/Simple-JP-Reader.git)
cd Simple-JP-Reader
pip install -r requirements.txt
python src/main.py
```



## ⌨️ Controls

* **Left Alt:** Trigger snipping tool
* **Click + Drag:** Select text area
* **Escape (While Snipping):** Cancel snip
