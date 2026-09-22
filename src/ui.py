from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QHBoxLayout, 
                             QVBoxLayout, QLabel, QRubberBand, QScrollArea, 
                             QFrame, QSizeGrip, QLineEdit, QFormLayout,
                             QCheckBox, QComboBox)
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import (QGuiApplication, QPainter, QPen, QColor, QBrush, QPolygon, 
                         QPolygonF, QPixmap, QImage, QPainterPath)

from dictionary import get_real_data
from model import extract_words, tokenize_sentence
from translation import translate_text
from ai_fix import fix_japanese_ocr
from anki_export import add_anki_card

import os
import json
import cv2
import numpy as np

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_SETTINGS = {
    "show_pitch": True,
    "show_freq": True,
    "show_jlpt": True,
    "show_meaning": True,
    "enable_translation": True,
    "translation_engine": "google",
    "deepl_api_key": "",
    "nvidia_api_key": "",
    "ai_engine": "google",
    "global_api_key": "",
    "local_base_url": "http://localhost:11434/v1",
    "vision_model": "meta/llama-3.2-90b-vision-instruct",
    "text_model": "meta/llama-3.1-70b-instruct",
    "enable_ai_fix": True,
    "gemini_api_key": "",
    "anki_deck": "Default",
    "anki_model": "Basic",
    "anki_field_map": {},
    "anki_custom_css": ".sjr-dictionary ul {\n    list-style-type: none;\n    padding-left: 0;\n    margin: 0;\n}\n.sjr-dictionary li {\n    margin-bottom: 4px;\n}\n.sjr-dictionary b {\n    color: #3B82F6;\n}",
    "enable_quick_snip": True,
    "quick_snip_hotkey": "Alt",
    "enable_manual_snip": True,
    "manual_snip_hotkey": "Ctrl+Alt",
    "minimize_to_tray": True,
    "active_ocr_engine": "manga_ocr",
}

def load_settings():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                merged = DEFAULT_SETTINGS.copy()
                merged.update(loaded)
                return merged
        except Exception as e:
            print(f"Error loading config: {e}")
    return DEFAULT_SETTINGS.copy()

def save_settings_disk():
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(USER_SETTINGS, f, indent=4)
    except Exception as e:
        print(f"Error saving config: {e}")

USER_SETTINGS = load_settings()

class SignalManager(QObject):
    trigger_quick_snip = pyqtSignal()
    trigger_manual_snip = pyqtSignal()
    show_results = pyqtSignal(list, int, int)
    update_history = pyqtSignal(str) 
    word_edited = pyqtSignal()

signals = SignalManager()

# --- WORKER THREADS (NON-BLOCKING) ---

class OCRWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, img, engine="manga_ocr"):
        super().__init__()
        self.img = img
        self.engine = engine

    def run(self):
        try:
            token_list = extract_words(self.img, engine=self.engine)
            self.finished.emit(token_list)
        except Exception as e:
            self.error.emit(str(e))

class AnkiCheckWorker(QThread):
    exists = pyqtSignal(bool)

    def __init__(self, deck_name, term, base_form=None, custom_map=None):
        super().__init__()
        self.deck_name = deck_name
        self.term = term
        self.base_form = base_form
        self.custom_map = custom_map or {}

    def run(self):
        try:
            from anki_export import check_card_exists
            res = check_card_exists(
                deck_name=self.deck_name,
                term=self.term,
                base_form=self.base_form,
                custom_map=self.custom_map
            )
            self.exists.emit(res)
        except Exception:
            self.exists.emit(False)

class AIFixWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, image_path, current_text, engine, api_key, base_url, vision_model):
        super().__init__()
        self.image_path = image_path
        self.current_text = current_text
        self.engine = engine
        self.api_key = api_key
        self.base_url = base_url
        self.vision_model = vision_model

    def run(self):
        try:
            res = fix_japanese_ocr(
                self.image_path,
                self.current_text,
                engine=self.engine,
                api_key=self.api_key,
                base_url=self.base_url,
                vision_model=self.vision_model
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))

class TranslationWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, text, engine, api_key, base_url, text_model):
        super().__init__()
        self.text = text
        self.engine = engine
        self.api_key = api_key
        self.base_url = base_url
        self.text_model = text_model

    def run(self):
        try:
            res = translate_text(
                self.text,
                engine=self.engine,
                api_key=self.api_key,
                base_url=self.base_url,
                text_model=self.text_model
            )
            self.finished.emit(res)
        except Exception as e:
            self.error.emit(str(e))

class DictLookupWorker(QThread):
    finished = pyqtSignal(dict)

    def __init__(self, base_form, fallback_term):
        super().__init__()
        self.base_form = base_form
        self.fallback_term = fallback_term

    def run(self):
        try:
            data = get_real_data(self.base_form, fallback_term=self.fallback_term)
            self.finished.emit(data or {})
        except Exception:
            self.finished.emit({})

class AnkiCardWorker(QThread):
    finished = pyqtSignal(object)

    def __init__(self, deck, model, term, reading, definition, sentence, image_path, field_map):
        super().__init__()
        self.deck = deck
        self.model = model
        self.term = term
        self.reading = reading
        self.definition = definition
        self.sentence = sentence
        self.image_path = image_path
        self.field_map = field_map

    def run(self):
        try:
            res = add_anki_card(
                deck_name=self.deck,
                model_name=self.model,
                term=self.term,
                reading=self.reading,
                definition=self.definition,
                sentence=self.sentence,
                image_path=self.image_path,
                custom_map=self.field_map
            )
            self.finished.emit(res)
        except Exception as e:
            self.finished.emit({"error": str(e)})


# --- EXPANDABLE WORD COMPONENT ---
class ExpandableWordWidget(QWidget):
    def __init__(self, token_info):
        super().__init__()
        self.surface = token_info["surface"]
        self.base_form = token_info["base_form"]
        self.data_fetched = False
        self.cached_dict_data = {}

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 5, 0, 5)
        self.setLayout(self.layout)

        self.header_widget = QWidget()
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        self.edit_word = EditableWord(self.surface)
        self.header_layout.addWidget(self.edit_word)
        
        self.edit_word.returnPressed.connect(self.update_word)

        self.lbl_lemma = None
        if self.surface != self.base_form:
            self.lbl_lemma = QLabel(f"({self.base_form})")
            self.lbl_lemma.setStyleSheet("font-size: 13px; color: #9CA3AF;")
            self.header_layout.addWidget(self.lbl_lemma)

        self.header_layout.addStretch()

        self.pitch_graph = PitchGraphWidget("", pitch_drop=-1)
        self.header_layout.addWidget(self.pitch_graph)

        self.btn_anki = QPushButton("+")
        self.btn_anki.setFixedSize(24, 24)
        self.btn_anki.setToolTip("Export card to Anki")
        self.btn_anki.setStyleSheet("""
            QPushButton { 
                background-color: rgba(59, 130, 246, 0.2); 
                color: #60A5FA; 
                font-weight: bold; 
                font-size: 16px; 
                border-radius: 4px; 
                border: 1px solid #3B82F6;
                padding: 0px 0px 6px 1px;
                text-align: center; 
            }
            QPushButton:hover { 
                background-color: #3B82F6; 
                color: white; 
            }
        """)
        self.btn_anki.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_anki.clicked.connect(self.export_to_anki)
        self.header_layout.addWidget(self.btn_anki)

        self.btn_toggle = QPushButton("v")
        self.btn_toggle.setFixedSize(24, 24)
        self.btn_toggle.setStyleSheet("background: transparent; color: #9CA3AF; font-weight: bold; font-size: 16px; border: none;")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle)
        self.header_layout.addWidget(self.btn_toggle)
        
        self.layout.addWidget(self.header_widget)

        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(15, 0, 0, 10)

        self.lbl_loading = QLabel("Loading dictionary...")
        self.lbl_loading.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        self.content_layout.addWidget(self.lbl_loading)

        self.content_widget.hide()
        self.layout.addWidget(self.content_widget)

        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.Shape.HLine)
        self.sep.setStyleSheet("background-color: rgba(255, 255, 255, 30);")
        self.layout.addWidget(self.sep)

        self.fetch_data()
        self.check_anki_duplicate()

    def check_anki_duplicate(self):
        deck = USER_SETTINGS.get("anki_deck", "Default")
        field_map = USER_SETTINGS.get("anki_field_map", {})
        self.anki_check_worker = AnkiCheckWorker(
            deck_name=deck,
            term=self.surface,
            base_form=self.base_form,
            custom_map=field_map
        )
        self.anki_check_worker.exists.connect(self.on_anki_check_result)
        self.anki_check_worker.start()

    def on_anki_check_result(self, exists):
        if exists:
            self.btn_anki.setText("★")
            self.btn_anki.setToolTip("Word already in Anki deck (Click to re-export)")
            self.btn_anki.setStyleSheet("""
                QPushButton { 
                    background-color: rgba(245, 158, 11, 0.2); 
                    color: #F59E0B; 
                    font-weight: bold; 
                    font-size: 16px; 
                    border-radius: 4px; 
                    border: 1px solid #F59E0B;
                    padding: 0px 0px 4px 0px;
                    text-align: center; 
                }
                QPushButton:hover { 
                    background-color: #F59E0B; 
                    color: white; 
                }
            """)
        else:
            self.btn_anki.setText("+")
            self.btn_anki.setToolTip("Export card to Anki")
            self.btn_anki.setStyleSheet("""
                QPushButton { 
                    background-color: rgba(59, 130, 246, 0.2); 
                    color: #60A5FA; 
                    font-weight: bold; 
                    font-size: 16px; 
                    border-radius: 4px; 
                    border: 1px solid #3B82F6;
                    padding: 0px 0px 6px 1px;
                    text-align: center; 
                }
                QPushButton:hover { 
                    background-color: #3B82F6; 
                    color: white; 
                }
            """)

    def export_to_anki(self):
        import re

        data = self.cached_dict_data if self.cached_dict_data else get_real_data(self.base_form, fallback_term=self.surface)
        reading = data.get("pitch", self.surface)
        
        definition_html = ""
        if "meanings_list" in data and data["meanings_list"]:
            for entry in data["meanings_list"]:
                definition_html += f"<b>[{entry['dict_name']}]</b><br>{entry['html_content']}<br>"
        else:
            definition_html = data.get("meaning", "No definition")

        clean_html = re.sub(r'\s*style="[^"]*"', '', definition_html)
        wrapped_html = f'<div class="sjr-dictionary">{clean_html}</div>'

        custom_css = USER_SETTINGS.get("anki_custom_css", "")
        if custom_css:
            wrapped_html += f'<style>{custom_css}</style>'

        deck = USER_SETTINGS.get("anki_deck", "Default")
        model = USER_SETTINGS.get("anki_model", "Basic")
        image_path = "temp_snip.png" if os.path.exists("temp_snip.png") else None
        field_map = USER_SETTINGS.get("anki_field_map", {})

        overlay = self.window()
        sentence_context = overlay.lbl_sentence.text() if hasattr(overlay, 'lbl_sentence') else ""

        self.btn_anki.setEnabled(False)
        self.btn_anki.setText("...")

        self.anki_worker = AnkiCardWorker(
            deck=deck,
            model=model,
            term=self.surface,
            reading=reading,
            definition=wrapped_html,
            sentence=sentence_context,
            image_path=image_path,
            field_map=field_map
        )
        self.anki_worker.finished.connect(self.on_anki_exported)
        self.anki_worker.start()

    def on_anki_exported(self, res):
        self.btn_anki.setEnabled(True)
        if isinstance(res, dict) and "error" in res:
            print(f"[Anki] Error: {res['error']}")
            self.btn_anki.setText("✕")
            self.btn_anki.setStyleSheet(
                "background-color: rgba(239, 68, 68, 0.2); color: #EF4444; border: 1px solid #EF4444; padding: 0px 0px 2px 0px; text-align: center;")
            QTimer.singleShot(2000, self.reset_anki_btn)
        else:
            print(f"[Anki] Successfully created card ID: {res}")
            self.btn_anki.setText("✓")
            self.btn_anki.setStyleSheet("background-color: rgba(16, 185, 129, 0.2); color: #10B981; border: 1px solid #10B981; padding: 0px 0px 2px 0px; text-align: center;")
            QTimer.singleShot(2000, self.reset_anki_btn)

    def reset_anki_btn(self):
        self.btn_anki.setText("+")
        self.btn_anki.setToolTip("Export card to Anki")
        self.btn_anki.setStyleSheet("""
            QPushButton { 
                background-color: rgba(59, 130, 246, 0.2); 
                color: #60A5FA; 
                font-weight: bold; 
                font-size: 16px; 
                border-radius: 4px; 
                border: 1px solid #3B82F6; 
                padding: 0px 0px 6px 1px;
                text-align: center;
            }
            QPushButton:hover { 
                background-color: #3B82F6; 
                color: white; 
            }
        """)
        self.check_anki_duplicate()

    def update_word(self):
        new_text = self.edit_word.text().strip()

        if not new_text or new_text == self.surface:
            self.edit_word.clearFocus()
            return

        self.surface = new_text
        self.base_form = new_text
        self.data_fetched = False
        self.cached_dict_data = {}

        self.check_anki_duplicate()

        if self.lbl_lemma:
            self.lbl_lemma.hide()

        if hasattr(self, 'pitch_graph'):
            dummy_drop = len(self.base_form) % 3
            self.pitch_graph.update_pitch(self.base_form, dummy_drop)
            self.pitch_graph.show()

        for i in reversed(range(self.content_layout.count())):
            widget = self.content_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        self.lbl_loading = QLabel("Loading Dictionary...")
        self.lbl_loading.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        self.content_layout.addWidget(self.lbl_loading)

        self.edit_word.clearFocus()

        signals.word_edited.emit()

        if not self.content_widget.isHidden():
            self.fetch_data()
        else:
            self.toggle()

    def toggle(self):
        if self.content_widget.isHidden():
            self.content_widget.show()
            self.btn_toggle.setText("^")
            
            if not self.data_fetched:
                self.fetch_data()
        else:
            self.content_widget.hide()
            self.btn_toggle.setText("v")

    def fetch_data(self):
        if self.data_fetched:
            return
        self.dict_worker = DictLookupWorker(self.base_form, self.surface)
        self.dict_worker.finished.connect(self.on_dict_loaded)
        self.dict_worker.start()

    def on_dict_loaded(self, data):
        self.data_fetched = True
        self.cached_dict_data = data

        if self.lbl_loading:
            self.lbl_loading.deleteLater()
            self.lbl_loading = None

        # Yomitan-style hover preview tooltip
        reading_disp = data.get("pitch", "")
        meaning_snippet = ""
        if "meanings_list" in data and data["meanings_list"]:
            first_m = data["meanings_list"][0].get("html_content", "")
            import re
            clean_snippet = re.sub(r'<[^>]+>', ' ', first_m).strip()
            if len(clean_snippet) > 120:
                clean_snippet = clean_snippet[:117] + "..."
            meaning_snippet = clean_snippet
        elif "meaning" in data:
            meaning_snippet = data["meaning"]
            if len(meaning_snippet) > 120:
                meaning_snippet = meaning_snippet[:117] + "..."

        hover_tip = f"<b>{self.surface}</b>"
        if reading_disp and reading_disp != "???":
            hover_tip += f" [{reading_disp}]"
        if meaning_snippet:
            hover_tip += f"<br><span style='color: #D1D5DB;'>{meaning_snippet}</span>"

        self.edit_word.setToolTip(hover_tip)
        if self.lbl_lemma:
            self.lbl_lemma.setToolTip(hover_tip)

        # pitch accent
        if hasattr(self, 'pitch_graph'):
            if USER_SETTINGS.get("show_pitch", True):
                real_pitch_drop = data.get("pitch_drop", -1)
                actual_reading = data.get("pitch", self.base_form)
                self.pitch_graph.update_pitch(actual_reading, real_pitch_drop)
                self.pitch_graph.show()
            else:
                self.pitch_graph.hide()

        # grammar
        grammar_path = data.get("grammar", [])
        if grammar_path:
            grammar_str = " + ".join(grammar_path)
            lbl_grammar = QLabel(f"Grammar: {grammar_str}")
            lbl_grammar.setStyleSheet("font-size: 13px; color: #FBBF24; margin-bottom: 2px;")
            self.content_layout.addWidget(lbl_grammar)

        # metadata
        meta_badges = []
        reading_text = data.get('pitch', '').strip()
        if reading_text and reading_text != "???":
            meta_badges.append(f"Reading: {reading_text}")

        if USER_SETTINGS.get("show_freq", True):
            freq_val = data.get("freq")
            if freq_val:
                meta_badges.append(f"Freq: {freq_val}")

        if USER_SETTINGS.get("show_jlpt", True):
            jlpt_val = data.get("jlpt")
            if jlpt_val:
                meta_badges.append(f"JLPT: {jlpt_val}")

        if meta_badges:
            lbl_meta = QLabel(" • ".join(meta_badges))
            lbl_meta.setStyleSheet("font-size: 13px; color: #9CA3AF; margin-bottom: 5px;")
            self.content_layout.addWidget(lbl_meta)

        # dict def
        if USER_SETTINGS.get("show_meaning", True):
            if "meanings_list" in data and data["meanings_list"]:
                for entry in data["meanings_list"]:
                    lbl_dict_name = QLabel(f"<b>[ {entry['dict_name']} ]</b>")
                    lbl_dict_name.setStyleSheet("color: #60A5FA; font-size: 12px; margin-top: 5px;")
                    self.content_layout.addWidget(lbl_dict_name)

                    lbl_mean = QLabel(entry['html_content'])
                    lbl_mean.setTextFormat(Qt.TextFormat.RichText)
                    lbl_mean.setStyleSheet("font-size: 14px; color: white;")
                    lbl_mean.setWordWrap(True)
                    self.content_layout.addWidget(lbl_mean)
            elif "meaning" in data:
                lbl_dict_name = QLabel("<b>[ Jisho API ]</b>")
                lbl_dict_name.setStyleSheet("color: #34D399; font-size: 12px; margin-top: 5px;")
                self.content_layout.addWidget(lbl_dict_name)
                
                lbl_mean = QLabel(data['meaning'])
                lbl_mean.setStyleSheet("font-size: 14px; color: white;")
                lbl_mean.setWordWrap(True)
                self.content_layout.addWidget(lbl_mean)


# --- EDITABLE TEXT ---
class EditableWord(QLineEdit):
    def __init__(self, word):
        super().__init__(word)

        font = self.font()
        font.setPixelSize(18)
        font.setBold(True)
        self.setFont(font)

        self.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #E2E8F0;
                font-size: 18px;
                font-weight: bold;
                padding: 0px;
            }
            QLineEdit:focus {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid #666;
                border-radius: 3px;
                padding: 2px;
            }
        """)

        self.textChanged.connect(self.adjust_width)
        self.adjust_width(word)

        self.setSizePolicy(self.sizePolicy().Policy.Fixed, self.sizePolicy().Policy.Fixed)
        self.setCursorPosition(0)

    def adjust_width(self, text):
        metrics = self.fontMetrics()
        width = metrics.horizontalAdvance(text) + 30
        self.setFixedWidth(width)


# --- VERTICAL OVERLAY (INFO BOX) ---
class ResultOverlay(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        
        self.setMinimumSize(300, 150)

        self.setObjectName("MainBackground")
        self.setStyleSheet("""
            #MainBackground { 
                background-color: rgba(20, 20, 25, 250); 
                border-radius: 8px; 
                border: 1px solid #555; 
            }
        """)
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.top_bar = QHBoxLayout()
        self.top_bar.addStretch()

        self.btn_close = QPushButton("X")
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setStyleSheet("color: white; border-radius: 10px; font-weight: bold; border: none;")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide)
        self.top_bar.addStretch()
        self.top_bar.addWidget(self.btn_close)
        self.layout.addLayout(self.top_bar)

        self.lbl_sentence = QLabel()
        self.lbl_sentence.setStyleSheet("font-size: 16px; color: #60A5FA; font-weight: bold; border: none;")
        self.lbl_sentence.setWordWrap(True)
        self.layout.addWidget(self.lbl_sentence)

        self.lbl_translation = QLabel()
        self.lbl_translation.setStyleSheet("font-size: 14px; color: #34D399; font-style: italic; border: none; margin-top: 2px;")
        self.lbl_translation.setWordWrap(True)
        self.lbl_translation.hide()
        self.layout.addWidget(self.lbl_translation)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #3B82F6; margin-top: 5px; margin-bottom: 5px; min-height: 2px;")
        self.layout.addWidget(sep)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background: transparent;")
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 10, 0) 
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.scroll_content)
        self.layout.addWidget(self.scroll_area)

        self.grip_layout = QHBoxLayout()
        self.grip_layout.setContentsMargins(0, 0, 0, 0)
        self.grip_layout.addStretch()

        self.btn_ai_fix = QPushButton("✨")
        self.btn_ai_fix.setFixedSize(45, 20)
        self.btn_ai_fix.setStyleSheet("background: transparent; color: #FBBF24; font-weight: bold; font-size: 13px; border: none;")
        self.btn_ai_fix.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ai_fix.clicked.connect(self.run_ai_fix)
        self.grip_layout.addWidget(self.btn_ai_fix, 0, Qt.AlignmentFlag.AlignBottom)

        self.btn_translate = QPushButton("Aあ")
        self.btn_translate.setFixedSize(30, 20)
        self.btn_translate.setStyleSheet("background: transparent; color: #9CA3AF; font-weight: bold; font-size: 14px; border: none;")
        self.btn_translate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_translate.clicked.connect(self.run_translation)
        self.grip_layout.addWidget(self.btn_translate, 0, Qt.AlignmentFlag.AlignBottom)

        self.grip_layout.addStretch()

        self.size_grip = QSizeGrip(self)
        self.grip_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.layout.addLayout(self.grip_layout)

        self._is_dragging = False
        self._drag_start_position = QPoint()

        signals.show_results.connect(self.display_words)
        signals.word_edited.connect(self.rebuild_sentence)

    def run_ai_fix(self):
        full_text = self.lbl_sentence.text().strip()
        if not full_text:
            return

        self.btn_ai_fix.setEnabled(False)
        self.btn_ai_fix.setText("✨...")

        engine = USER_SETTINGS.get("ai_engine", "google")
        api_key = USER_SETTINGS.get("global_api_key") or USER_SETTINGS.get("gemini_api_key") or USER_SETTINGS.get("nvidia_api_key") or ""
        base_url = USER_SETTINGS.get("local_base_url", "")
        vision_model = USER_SETTINGS.get("vision_model", "")

        self.ai_worker = AIFixWorker(
            image_path="temp_snip.png",
            current_text=full_text,
            engine=engine,
            api_key=api_key,
            base_url=base_url,
            vision_model=vision_model
        )
        self.ai_worker.finished.connect(lambda res: self.on_ai_fix_finished(res, full_text))
        self.ai_worker.error.connect(lambda err: self.on_ai_fix_error(err))
        self.ai_worker.start()

    def on_ai_fix_finished(self, fixed_text, original_text):
        self.btn_ai_fix.setEnabled(True)
        self.btn_ai_fix.setText("✨")

        if fixed_text.startswith("Error:") or "Error" in fixed_text:
            print(f"[AI Fix] {fixed_text}")
            self.lbl_translation.setText(fixed_text)
            self.lbl_translation.show()
            self.adjustSize()
            return

        self.lbl_sentence.setText(fixed_text)
        self.lbl_sentence.setStyleSheet("font-size: 16px; color: #60A5FA; font-weight: bold; border: none;")

        for i in reversed(range(self.scroll_layout.count())):
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        new_tokens = tokenize_sentence(fixed_text)
        for token_info in new_tokens:
            if token_info["surface"].strip():
                item = ExpandableWordWidget(token_info)
                self.scroll_layout.addWidget(item)

        signals.update_history.emit(fixed_text)

        if not self.lbl_translation.isHidden():
            self.run_translation()

        self.adjustSize()

    def on_ai_fix_error(self, err_msg):
        self.btn_ai_fix.setEnabled(True)
        self.btn_ai_fix.setText("✨")
        self.lbl_translation.setText(f"AI Fix Failed: {err_msg}")
        self.lbl_translation.show()
        self.adjustSize()

    def run_translation(self):
        full_text = self.lbl_sentence.text().strip()
        if not full_text:
            return

        self.lbl_translation.setText("Translating...")
        self.lbl_translation.show()
        self.btn_translate.setEnabled(False)

        engine = USER_SETTINGS.get("ai_engine", USER_SETTINGS.get("translation_engine", "google"))
        api_key = USER_SETTINGS.get("global_api_key") or USER_SETTINGS.get("nvidia_api_key") or USER_SETTINGS.get("deepl_api_key") or ""
        base_url = USER_SETTINGS.get("local_base_url", "")
        text_model = USER_SETTINGS.get("text_model", "")

        self.trans_worker = TranslationWorker(
            text=full_text,
            engine=engine,
            api_key=api_key,
            base_url=base_url,
            text_model=text_model
        )
        self.trans_worker.finished.connect(self.on_translation_finished)
        self.trans_worker.error.connect(self.on_translation_error)
        self.trans_worker.start()

    def on_translation_finished(self, english_text):
        self.btn_translate.setEnabled(True)
        self.lbl_translation.setText(english_text)
        self.adjustSize()

    def on_translation_error(self, err_msg):
        self.btn_translate.setEnabled(True)
        self.lbl_translation.setText(f"Translation Error: {err_msg}")
        self.adjustSize()

    def display_words(self, token_list, x, y):
        if USER_SETTINGS.get("enable_ai_fix", True):
            self.btn_ai_fix.show()
        else:
            self.btn_ai_fix.hide()
            
        if USER_SETTINGS.get("enable_translation", True):
            self.btn_translate.show()
        else:
            self.btn_translate.hide()

        for i in reversed(range(self.scroll_layout.count())): 
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        full_text = "".join([t["surface"] for t in token_list])
        self.lbl_sentence.setText(full_text)

        self.lbl_translation.hide()

        for token_info in token_list:
            if token_info["surface"].strip(): 
                item = ExpandableWordWidget(token_info)
                self.scroll_layout.addWidget(item)

        self.adjustSize()
        width = self.width()
        height = self.height()

        screen = QGuiApplication.primaryScreen().availableGeometry()
        spawn_x = x + 15
        spawn_y = y + 15

        if spawn_x + width > screen.width():
            spawn_x = x - width - 15
        if spawn_y + height > screen.height():
            spawn_y = screen.height() - height - 15

        spawn_x = max(0, spawn_x)
        spawn_y = max(0, spawn_y)

        self.move(int(spawn_x), int(spawn_y))
        self.show()

    def rebuild_sentence(self):
        full_text = ""
        for i in range(self.scroll_layout.count()):
            widget = self.scroll_layout.itemAt(i).widget()
            if hasattr(widget, 'surface'):
                full_text += widget.surface

        self.lbl_sentence.setText(full_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_start_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            event.accept()


# --- PITCH GRAPH ---
class PitchGraphWidget(QWidget):
    def __init__(self, word, pitch_drop):
        super().__init__()
        self.spacing = 12
        self.update_pitch(word, pitch_drop)

    def update_pitch(self, new_word, new_pitch_drop):
        self.word = new_word.split('・')[0].strip() if new_word else ""
        self.pitch_drop = new_pitch_drop
        
        if self.pitch_drop == -1:
            self.setFixedSize(0, 24)
        else:
            small_kana = set("ゃゅょぁぃぅぇぉャュョァィゥェォ")
            mora_count = max(1, sum(1 for c in self.word if c not in small_kana))
            total_dots = mora_count + 1 if self.pitch_drop == 0 else mora_count
            self.setFixedSize(total_dots * self.spacing + 10, 24)
            
        self.update()

    def paintEvent(self, event):
        if self.pitch_drop == -1:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        small_kana = set("ゃゅょぁぃぅぇぉャュョァィゥェォ")
        mora_count = max(1, sum(1 for c in self.word if c not in small_kana))
        total_dots = mora_count + 1 if self.pitch_drop == 0 else mora_count

        high_y = 4
        low_y = 16
        radius = 3
        start_x = 5

        points = []

        for i in range(total_dots):
            mora_num = i + 1
            is_high = False

            if self.pitch_drop == 0:        # Heiban: low, high, high... (particle high)
                is_high = (mora_num > 1)
            elif self.pitch_drop == 1:      # Atamadaka: high, low, low...
                is_high = (mora_num == 1)
            else:                           # Nakadaka/Odaka
                if mora_num == 1:
                    is_high = False
                elif mora_num <= self.pitch_drop:
                    is_high = True
                else:
                    is_high = False

            y = high_y if is_high else low_y
            x = start_x + (i * self.spacing)
            points.append(QPoint(x, y))

        pen = QPen(QColor(96, 165, 250))
        pen.setWidth(2)
        painter.setPen(pen)

        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i+1])

        painter.setBrush(QColor(20, 20, 25))
        for p in points:
            painter.drawEllipse(p, radius, radius)


# --- SNIPPING CAMERA ---
class SnippingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.is_manual_mode = False
        self.state = "HIDDEN"

        self.start_point = QPoint()
        self.end_point = QPoint()
        self.polygon = QPolygon()
        self.active_corner_index = None

        signals.trigger_quick_snip.connect(lambda: self.start_snipping(is_manual=False))
        signals.trigger_manual_snip.connect(lambda: self.start_snipping(is_manual=True))

    def start_snipping(self, is_manual):
        self.is_manual_mode = is_manual
        self.state = "IDLE"
        self.polygon.clear()

        from PyQt6.QtGui import QCursor, QGuiApplication
        import mss

        current_screen = QGuiApplication.screenAt(QCursor.pos())
        if not current_screen:
            current_screen = QGuiApplication.primaryScreen()
            
        geom = current_screen.geometry()

        with mss.mss() as sct:
            monitor = {
                "top": geom.y(),
                "left": geom.x(),
                "width": geom.width(),
                "height": geom.height()
            }
            sct_img = sct.grab(monitor)

        self.frozen_img_cv = np.array(sct_img)
        self.frozen_img_cv = cv2.cvtColor(self.frozen_img_cv, cv2.COLOR_BGRA2BGR)

        height, width, channel = self.frozen_img_cv.shape
        bytes_per_line = 3 * width
        q_img = QImage(self.frozen_img_cv.data, width, height, bytes_per_line, QImage.Format.Format_BGR888)
        self.frozen_pixmap = QPixmap.fromImage(q_img)

        self.setGeometry(geom)
        self.show()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            click_pos = event.position().toPoint()

            if self.state == "ADJUSTING":
                for i in range(self.polygon.count()):
                    if (self.polygon.at(i) - click_pos).manhattanLength() < 15:
                        self.active_corner_index = i
                        return

                self.state = "DRAGGING"
                self.start_point = click_pos
                self.end_point = self.start_point
                self.update()

            elif self.state == "IDLE":
                self.state = "DRAGGING"
                self.start_point = click_pos
                self.end_point = self.start_point
                self.update()

    def mouseMoveEvent(self, event):
        if self.state == "ADJUSTING" and self.active_corner_index is not None:
            self.polygon.replace(self.active_corner_index, event.position().toPoint())
            self.update()

        elif self.state == "DRAGGING":
            self.end_point = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.state == "ADJUSTING":
                self.active_corner_index = None
                
            elif self.state == "DRAGGING":
                self.end_point = event.position().toPoint()
                
                if not self.is_manual_mode:
                    # --- QUICK SNIP MODE ---
                    self.state = "HIDDEN"
                    self.hide()
                    rect = QRect(self.start_point, self.end_point).normalized()
                    poly = QPolygon([rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()])
                    
                    mouse_x = event.position().toPoint().x()
                    mouse_y = event.position().toPoint().y()
                    QTimer.singleShot(100, lambda: self.process_image(poly, mouse_x, mouse_y))
                else:
                    # --- MANUAL ADJUSTMENT MODE ---
                    self.state = "ADJUSTING"
                    rect = QRect(self.start_point, self.end_point).normalized()
                    self.polygon = QPolygon([rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()])
                    self.update()

    def keyPressEvent(self, event):
        if self.state == "ADJUSTING":
            if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
                self.state = "HIDDEN"
                self.hide()
                
                rect = self.polygon.boundingRect()
                poly_copy = QPolygon(self.polygon)
                
                QTimer.singleShot(100, lambda: self.process_image(poly_copy, rect.x(), rect.y()))
                
            elif event.key() == Qt.Key.Key_Escape:
                self.state = "HIDDEN"
                self.hide()

    def paintEvent(self, event):
        if self.state == "HIDDEN":
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if hasattr(self, 'frozen_pixmap'):
            painter.drawPixmap(self.rect(), self.frozen_pixmap)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

        if self.state == "DRAGGING":
            rect = QRect(self.start_point, self.end_point).normalized()
            painter.drawPixmap(rect, self.frozen_pixmap, rect)

        elif self.state == "ADJUSTING":
            from PyQt6.QtCore import QPointF
            path = QPainterPath()

            poly_f = QPolygonF()
            for i in range(self.polygon.count()):
                poly_f.append(QPointF(self.polygon.at(i)))
            path.addPolygon(poly_f)

            painter.setClipPath(path)
            painter.drawPixmap(self.rect(), self.frozen_pixmap)
            painter.setClipping(False)

        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        pen = QPen(QColor(59, 130, 246))
        pen.setWidth(2)
        painter.setPen(pen)

        if self.state == "DRAGGING":
            painter.drawRect(QRect(self.start_point, self.end_point).normalized())
        elif self.state == "ADJUSTING":
            painter.drawPolygon(self.polygon)

            painter.setBrush(QColor(59, 130, 246))
            for i in range(self.polygon.count()):
                painter.drawEllipse(self.polygon.at(i), 6, 6)

    def process_image(self, polygon, x, y):
        from PIL import Image
        
        rect = polygon.boundingRect()
        if rect.width() < 10 or rect.height() < 10:
            print("Snip too small, aborting.")
            return
            
        img_h, img_w = self.frozen_img_cv.shape[:2]
        
        # Calculate DPI scaling ratio between Qt widget logical coordinates and image resolution
        scale_x = img_w / max(1, self.width())
        scale_y = img_h / max(1, self.height())

        top = max(0, int(rect.top() * scale_y))
        bottom = min(img_h, int(rect.bottom() * scale_y))
        left = max(0, int(rect.left() * scale_x))
        right = min(img_w, int(rect.right() * scale_x))
        
        cropped_cv = self.frozen_img_cv[top:bottom, left:right]
        
        if cropped_cv.size == 0:
            print("Cropped image is empty, aborting.")
            return
        
        pts = []
        for i in range(4):
            pt = polygon.at(i)
            pts.append([pt.x() * scale_x - left, pt.y() * scale_y - top]) 
        
        src_pts = np.array(pts, dtype="float32")
        
        width_top = np.linalg.norm(src_pts[0] - src_pts[1])
        width_bottom = np.linalg.norm(src_pts[3] - src_pts[2])
        max_width = max(int(width_top), int(width_bottom))
        
        height_left = np.linalg.norm(src_pts[0] - src_pts[3])
        height_right = np.linalg.norm(src_pts[1] - src_pts[2])
        max_height = max(int(height_left), int(height_right))
        
        if max_width < 5 or max_height < 5:
            return

        dst_pts = np.array([[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]], dtype="float32")
        
        matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
        warped = cv2.warpPerspective(cropped_cv, matrix, (max_width, max_height))

        final_img = Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
        final_img.save("temp_snip.png")
        
        active_engine = USER_SETTINGS.get("active_ocr_engine", "manga_ocr")
        self.ocr_thread = OCRWorker(final_img, engine=active_engine)
        self.ocr_thread.finished.connect(lambda tokens: self.on_ocr_complete(tokens, int(x), int(y)))
        self.ocr_thread.error.connect(lambda e: print(f"\n[CRASH LOG] OCR Failed: {e}\n"))
        self.ocr_thread.start()

    def on_ocr_complete(self, token_list, x, y):
        if token_list:
            signals.show_results.emit(token_list, x, y)
            full_text = "".join([t["surface"] for t in token_list])
            signals.update_history.emit(full_text)