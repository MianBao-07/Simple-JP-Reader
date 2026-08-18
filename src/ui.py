from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QHBoxLayout, 
                             QVBoxLayout, QLabel, QRubberBand, QScrollArea, QFrame, QSizeGrip)
from PyQt6.QtCore import Qt, QRect, QPoint, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QGuiApplication, QPainter, QPen, QColor, QBrush

from dictionary import get_real_data
from model import extract_words

USER_SETTINGS = {
    "show_pitch": True,
    "show_freq": True,
    "show_meaning": True
}

class SignalManager(QObject):
    trigger_snip = pyqtSignal()
    show_results = pyqtSignal(list, int, int)
    update_history = pyqtSignal(str) 

signals = SignalManager()

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

        if self.surface != self.base_form:
            header_text = f"{self.surface} <span style='font-size: 13px; color: #9CA3AF;'>({self.base_form})</span>"
        else:
            header_text = self.surface

        self.lbl_word = QLabel(header_text)
        self.lbl_word.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_word.setStyleSheet("font-size: 18px; font-weight: bold; color: #E2E8F0;")
        
        self.btn_toggle = QPushButton("v")
        self.btn_toggle.setFixedSize(24, 24)
        self.btn_toggle.setStyleSheet("background: transparent; color: #9CA3AF; font-weight: bold; font-size: 16px; border: none;")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.btn_toggle.clicked.connect(self.toggle)
        self.lbl_word.mousePressEvent = lambda e: self.toggle()
        self.lbl_word.setCursor(Qt.CursorShape.PointingHandCursor)

        self.header_layout.addWidget(self.lbl_word)
        self.header_layout.addStretch()

        dummy_drop = len(self.base_form) % 3 
        self.pitch_graph = PitchGraphWidget(self.base_form, pitch_drop=dummy_drop)
        self.header_layout.addWidget(self.pitch_graph)

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
                    # 1. Create a styled header for the Dictionary Name
                    lbl_dict_name = QLabel(f"<b>[ {entry['dict_name']} ]</b>")
                    lbl_dict_name.setStyleSheet("color: #60A5FA; font-size: 12px; margin-top: 5px;")
                    self.content_layout.addWidget(lbl_dict_name)

                    # 2. Render the HTML content
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
        
        self.setFixedWidth(320)
        # self.setMaximumHeight(450)

        self.layout = QVBoxLayout()
        # self.layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.layout)

        self.top_bar = QHBoxLayout()
        self.btn_close = QPushButton("X")
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setStyleSheet("background: #EF4444; color: white; border-radius: 10px; font-weight: bold; border: none;")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide)
        self.top_bar.addStretch()
        self.top_bar.addWidget(self.btn_close)
        self.layout.addLayout(self.top_bar)

        self.lbl_sentence = QLabel()
        self.lbl_sentence.setStyleSheet("font-size: 16px; color: #60A5FA; font-weight: bold; border: none;")
        self.lbl_sentence.setWordWrap(True)
        self.layout.addWidget(self.lbl_sentence)

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
        self.size_grip = QSizeGrip(self)
        self.grip_layout.addWidget(self.size_grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.layout.addLayout(self.grip_layout)


        self._is_dragging = False
        self._drag_start_position = QPoint()

        signals.show_results.connect(self.display_words)

    def display_words(self, token_list, x, y):
        for i in reversed(range(self.scroll_layout.count())): 
            widget = self.scroll_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        full_text = "".join([t["surface"] for t in token_list])
        self.lbl_sentence.setText(full_text)

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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # dummy
        mora_count = max(2, len(self.word))

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
        self.setStyleSheet("background-color: black;")
        self.setWindowOpacity(0.4)
        self.setCursor(Qt.CursorShape.CrossCursor)
        
        self.rubberBand = QRubberBand(QRubberBand.Shape.Rectangle, self)
        self.origin = QPoint()
        
        signals.trigger_snip.connect(self.start_snipping)

    def start_snipping(self):
        screen_geometry = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(screen_geometry)
        self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.rubberBand.setGeometry(QRect(self.origin, self.origin))
            self.rubberBand.show()

    def mouseMoveEvent(self, event):
        self.rubberBand.setGeometry(QRect(self.origin, event.position().toPoint()).normalized())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.hide()
            rect = QRect(self.origin, event.position().toPoint()).normalized()
            mouse_x = event.position().toPoint().x()
            mouse_y = event.position().toPoint().y()
            QTimer.singleShot(100, lambda: self.process_image(rect, mouse_x, mouse_y))

    def process_image(self, rect, x, y):
        region = {"top": rect.top(), "left": rect.left(), "width": rect.width(), "height": rect.height()}
        import mss
        from PIL import Image
        with mss.MSS() as sct:
            sct_img = sct.grab(region)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            token_list = extract_words(img)
            
            if token_list:
                signals.show_results.emit(token_list, int(x), int(y))
                full_text = "".join([t["surface"] for t in token_list])
                signals.update_history.emit(full_text)