from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QHBoxLayout, 
                             QVBoxLayout, QLabel, QRubberBand, QScrollArea, 
                             QFrame, QSizeGrip, QLineEdit, QFormLayout,
                             QCheckBox, QComboBox)
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal, QObject, QThread
from PyQt6.QtGui import QGuiApplication, QPainter, QPen, QColor, QBrush, QPolygon

from dictionary import get_real_data
from model import extract_words, tokenize_sentence
from translation import translate_text
from ai_fix import fix_japanese_ocr

import os
import json
import cv2
import numpy as np

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_SETTINGS = {
    "show_pitch": True,
    "show_freq": True,
    "show_meaning": True,
    "enable_translation": True,
    "translation_engine": "google",
    "deepl_api_key": "",
    "enable_ai_fix": True,
    "gemini_api_key": "",
}

def load_settings():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                merged = DEFAULT_SETTINGS.copy()
                merged.update(loaded) # will overwrite default with saved data
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

class OCRWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, img):
        super().__init__()
        self.img = img

    def run(self):
        try:
            token_list = extract_words(self.img)
            self.finished.emit(token_list)
        except Exception as e:
            self.error.emit(str(e))

# --- EXPANDABLE WORD COMPONENT ---
class ExpandableWordWidget(QWidget):
    def __init__(self, token_info):
        super().__init__()
        self.surface = token_info["surface"]
        self.base_form = token_info["base_form"]
        self.data_fetched = False

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 5, 0, 5)
        self.setLayout(self.layout)

        # 1. Header (Shows surface form, with lemma indicator if conjugated)
        self.header_widget = QWidget()
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(0, 0, 0, 0)

        self.edit_word = EditableWord(self.surface)
        self.header_layout.addWidget(self.edit_word)
        
        self.edit_word.returnPressed.connect(self.update_word)

        # Handle the lemma (dictionary form) if it's conjugated
        self.lbl_lemma = None
        if self.surface != self.base_form:
            self.lbl_lemma = QLabel(f"({self.base_form})")
            self.lbl_lemma.setStyleSheet("font-size: 13px; color: #9CA3AF;")
            self.header_layout.addWidget(self.lbl_lemma)

        self.header_layout.addStretch()

        self.pitch_graph = PitchGraphWidget("", pitch_drop=-1)
        self.header_layout.addWidget(self.pitch_graph)

        self.btn_toggle = QPushButton("v")
        self.btn_toggle.setFixedSize(24, 24)
        self.btn_toggle.setStyleSheet("background: transparent; color: #9CA3AF; font-weight: bold; font-size: 16px; border: none;")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.btn_toggle.clicked.connect(self.toggle)
        self.header_layout.addWidget(self.btn_toggle)
        
        self.layout.addWidget(self.header_widget)

        # 2. Hidden Content Area
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(15, 0, 0, 10)

        self.lbl_loading = QLabel("Loading dictionary...")
        self.lbl_loading.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        self.content_layout.addWidget(self.lbl_loading)

        self.content_widget.hide()
        self.layout.addWidget(self.content_widget)

        # 3. Separator Line
        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.Shape.HLine)
        self.sep.setStyleSheet("background-color: rgba(255, 255, 255, 30);")
        self.layout.addWidget(self.sep)

        self.fetch_data()

    def update_word(self):
        new_text = self.edit_word.text().strip()

        if not new_text or new_text == self.surface:
            self.edit_word.clearFocus()
            return

        self.surface = new_text
        self.base_form = new_text # assume manual edits are dict form
        self.data_fetched = False

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
                QApplication.processEvents() 
                self.fetch_data()
        else:
            self.content_widget.hide()
            self.btn_toggle.setText("v")

    def fetch_data(self):
        # Query using the dictionary base form first, surface form as fallback
        data = get_real_data(self.base_form, fallback_term=self.surface)
        self.lbl_loading.deleteLater()

        if hasattr(self, 'pitch_graph'):
            real_pitch_drop = data.get("pitch_drop", 0)
            actual_reading = data.get("pitch", self.base_form)
            self.pitch_graph.update_pitch(actual_reading, real_pitch_drop)

        meta_text = []
        if USER_SETTINGS["show_pitch"]: meta_text.append(f"Reading: {data.get('pitch', '???')}")
        if USER_SETTINGS["show_freq"]: meta_text.append(f"Freq: {data.get('freq', 'Unknown')}")

        if meta_text:
            lbl_meta = QLabel(" • ".join(meta_text))
            lbl_meta.setStyleSheet("font-size: 13px; color: #9CA3AF; margin-bottom: 5px;")
            self.content_layout.addWidget(lbl_meta)

        if USER_SETTINGS["show_meaning"]:
            # Handle the structured HTML list (Offline Dictionaries)
            if "meanings_list" in data:
                for entry in data["meanings_list"]:
                    # Create a styled header for the Dictionary Name
                    lbl_dict_name = QLabel(f"<b>[ {entry['dict_name']} ]</b>")
                    lbl_dict_name.setStyleSheet("color: #60A5FA; font-size: 12px; margin-top: 5px;")
                    self.content_layout.addWidget(lbl_dict_name)

                    # Render the HTML content
                    lbl_mean = QLabel(entry['html_content'])
                    lbl_mean.setTextFormat(Qt.TextFormat.RichText) # Force HTML rendering
                    lbl_mean.setStyleSheet("font-size: 14px; color: white;")
                    lbl_mean.setWordWrap(True)
                    self.content_layout.addWidget(lbl_mean)
            
            # --- FALLBACK: Handle plain text (Jisho.org API) ---
            elif "meaning" in data:
                lbl_dict_name = QLabel("<b>[ Jisho API ]</b>")
                lbl_dict_name.setStyleSheet("color: #34D399; font-size: 12px; margin-top: 5px;")
                self.content_layout.addWidget(lbl_dict_name)
                
                lbl_mean = QLabel(data['meaning'])
                lbl_mean.setStyleSheet("font-size: 14px; color: white;")
                lbl_mean.setWordWrap(True)
                self.content_layout.addWidget(lbl_mean)

        self.data_fetched = True

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
            QLineEdit: focus {
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
        
        self.setMinimumSize(300,150)

        self.setObjectName("MainBackground")
        self.setStyleSheet("""
            #MainBackground { 
                background-color: rgba(20, 20, 25, 250); 
                border-radius: 8px; 
                border: 1px solid #555; 
            }
        """)
        
        # self.setFixedWidth(320)
        # self.setMaximumHeight(450)
        self.layout = QVBoxLayout()
        # self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.top_bar = QHBoxLayout()
        self.top_bar.addStretch()

        self.btn_close = QPushButton("X")
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setStyleSheet("color: white; border-radius: 10px; font-weight: bold; border: none;") # red circle -> background: #EF4444; 
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

        # Removed the static hide() check for AI Fix here!

        self.btn_translate = QPushButton("Aあ")
        self.btn_translate.setFixedSize(30, 20)
        self.btn_translate.setStyleSheet("background: transparent; color: #9CA3AF; font-weight: bold; font-size: 14px; border: none;")
        self.btn_translate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_translate.clicked.connect(self.run_translation)
        self.grip_layout.addWidget(self.btn_translate, 0, Qt.AlignmentFlag.AlignBottom)

        # Removed the static hide() check for Translation here!

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

        self.lbl_sentence.setText("✨...")
        self.lbl_sentence.setStyleSheet("font-size: 16px; color: #FBBF24; font-weight: bold; border: none; font-style: italic;")
        QApplication.processEvents()

        api_key = USER_SETTINGS.get("gemini_api_key", "")
        fixed_text = fix_japanese_ocr("temp_snip.png", full_text, api_key=api_key)
        
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

    def run_translation(self):
        full_text = self.lbl_sentence.text().strip()
        if not full_text:
            return

        self.lbl_translation.setText("Translating...")
        self.lbl_translation.show()
        QApplication.processEvents()

        engine = USER_SETTINGS.get("translation_engine", "google")
        api_key = USER_SETTINGS.get("deepl_api_key", "")

        # --- FIX: Pass the dynamic engine and API key to the translation function ---
        english_text = translate_text(full_text, engine=engine, api_key=api_key)

        self.lbl_translation.setText(english_text)
        self.adjustSize()

    def display_words(self, token_list, x, y):
        # --- FIX: Dynamically check the settings every time we display the box ---
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
        self.word = word
        self.pitch_drop = pitch_drop
        self.setFixedSize(100, 24)

    def update_pitch(self, new_word, new_pitch_drop):
        self.word = new_word
        self.pitch_drop = new_pitch_drop
        self.update()

    def paintEvent(self, event):
        if self.pitch_drop == -1:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ignore small kana
        small_kana = set("ゃゅょぁぃぅぇぉャュョァィゥェォ")
        mora_count = max(1, sum(1 for c in self.word if c not in small_kana))

        high_y = 4          # high
        low_y = 16          # low
        radius = 3          # size of dots
        spacing = 12        # horizontal space between dots
        start_x = self.width() - (mora_count * spacing) - 5 # right-align

        points = []

        for i in range(mora_count):
            mora_num = i + 1
            is_high = False

            if self.pitch_drop == 0:        # heiban -> low, high, high, ...
                is_high = (mora_num > 1)
            elif self.pitch_drop == 1:      # atamadaka -> high, low, low, ...
                is_high = (mora_num == 1)
            else:                           # nakadaka/odaka -> high, high, ....
                if mora_num == 1:
                    is_high = False
                elif mora_num <= self.pitch_drop:
                    is_high = True
                else:
                    is_high = False

            y = high_y if is_high else low_y
            x = start_x + (i * spacing)
            points.append(QPoint(x, y))

        pen = QPen(QColor(255, 255, 255))
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
        self.state = "HIDDEN" # hidden, dragging, adjusting

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

        screen_geometry = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.show()
        self.update() # force a repaint

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
            returnPressed

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # screen dimming overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0 , 150))

        # erase inside selection for transparency effect
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        if self.state == "DRAGGING":
            rect = QRect(self.start_point, self.end_point).normalized()
            painter.fillRect(rect, Qt.GlobalColor.transparent)
        elif self.state == "ADJUSTING":
            painter.drawPolygon(self.polygon)

        # blue borders and grab handles
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
        import mss
        from PIL import Image
        
        # get  standard bounding box that surrounds custom angled shape
        rect = polygon.boundingRect()
        region = {"top": rect.top(), "left": rect.left(), "width": rect.width(), "height": rect.height()}
        
        with mss.MSS() as sct:
            sct_img = sct.grab(region)
            
            # Convert mss screen grab to OpenCV numpy array
            img = np.array(sct_img)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR) # Drop the alpha channel
            
            pts = []
            for i in range(4):
                pt = polygon.at(i)
                pts.append([pt.x() - rect.left(), pt.y() - rect.top()])
            
            src_pts = np.array(pts, dtype="float32")
            
            # maximum width and height calculation
            width_top = np.linalg.norm(src_pts[0] - src_pts[1])
            width_bottom = np.linalg.norm(src_pts[3] - src_pts[2])
            max_width = max(int(width_top), int(width_bottom))
            
            height_left = np.linalg.norm(src_pts[0] - src_pts[3])
            height_right = np.linalg.norm(src_pts[1] - src_pts[2])
            max_height = max(int(height_left), int(height_right))
            
            # 4 corners of image
            dst_pts = np.array([
                [0, 0],
                [max_width - 1, 0],
                [max_width - 1, max_height - 1],
                [0, max_height - 1]
            ], dtype="float32")
            
            # matrix calc
            matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
            warped = cv2.warpPerspective(img, matrix, (max_width, max_height))

            final_img = Image.fromarray(cv2.cvtColor(warped, cv2.COLOR_BGR2RGB))
            final_img.save("temp_snip.png") 

            # Pass it to the background thread
            self.ocr_thread = OCRWorker(final_img)
            self.ocr_thread.finished.connect(lambda tokens: self.on_ocr_complete(tokens, int(x), int(y)))
            self.ocr_thread.error.connect(lambda e: print(f"\n[CRASH LOG] OCR Failed: {e}\n"))
            self.ocr_thread.start()

    def on_ocr_complete(self, token_list, x, y):
        if token_list:
            signals.show_results.emit(token_list, x, y)
            full_text = "". join([t["surface"] for t in token_list])
            signals.update_history.emit(full_text)