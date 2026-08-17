import sys
import signal
from pynput import keyboard
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QListWidget, QTabWidget, QGroupBox, 
                             QCheckBox, QSlider, QFormLayout)
from PyQt6.QtCore import Qt, QTimer

from ui import ResultOverlay, SnippingWidget, signals

class ControlPanel(QWidget):
    def __init__(self, keyboard_listener):
        super().__init__()
        self.keyboard_listener = keyboard_listener
        
        self.setWindowTitle("X-Ray Lens - Workspace")
        self.resize(450, 450)
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)
        
        self.default_lbl_text = "App is running. Press 'Left Alt' to snip.\nClose this window to completely quit the application."
        self.lbl = QLabel(self.default_lbl_text)
        self.lbl.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
        self.layout.addWidget(self.lbl)
        
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)
        
        # TAB 1: History
        self.tab_history = QWidget()
        self.history_layout = QVBoxLayout(self.tab_history)
        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget { font-size: 16px; padding: 5px; }
            QListWidget::item { padding: 4px; border-bottom: 1px solid #444; }
            QListWidget::item:hover { background-color: rgba(255, 255, 255, 20); cursor: pointer; }
        """)
        
        # --- NEW: Click to copy signal ---
        self.history_list.itemClicked.connect(self.copy_history_item)
        
        self.history_layout.addWidget(self.history_list)
        self.tabs.addTab(self.tab_history, "History")
        
        # TAB 2: Dictionaries
        self.tab_dicts = QWidget()
        self.dicts_layout = QVBoxLayout(self.tab_dicts)
        self.init_dictionary_tab()
        self.tabs.addTab(self.tab_dicts, "Dictionaries")

        # TAB 3: OCR Profiles
        self.tab_ocr = QWidget()
        self.ocr_layout = QVBoxLayout(self.tab_ocr)
        self.init_ocr_tab()
        self.tabs.addTab(self.tab_ocr, "OCR Profiles")

        # TAB 4: Appearance
        self.tab_appearance = QWidget()
        self.appearance_layout = QVBoxLayout(self.tab_appearance)
        self.init_appearance_tab()
        self.tabs.addTab(self.tab_appearance, "Appearance")
        
        signals.update_history.connect(self.add_to_history)

    # --- NEW: Copy Logic ---
    def copy_history_item(self, item):
        # Send text to clipboard
        QApplication.clipboard().setText(item.text())
        
        # Give visual feedback
        self.lbl.setText("Copied to clipboard!\n" + self.default_lbl_text.split('\n')[1])
        self.lbl.setStyleSheet("font-weight: bold; margin-bottom: 5px; color: #10B981;") # Turn text green
        
        # Reset the label back to normal after 1.5 seconds
        QTimer.singleShot(1500, self.reset_label)

    def reset_label(self):
        self.lbl.setText(self.default_lbl_text)
        self.lbl.setStyleSheet("font-weight: bold; margin-bottom: 5px; color: palette(window-text);")

    # --- TAB LAYOUTS ---

    def init_dictionary_tab(self):
        group_term = QGroupBox("Term Dictionaries")
        l_term = QVBoxLayout()
        self.chk_jitendex = QCheckBox("Jitendex (Japanese-to-English)")
        self.chk_jitendex.setChecked(True)
        self.chk_jmnedict = QCheckBox("JMnedict (Proper Names)")
        l_term.addWidget(self.chk_jitendex)
        l_term.addWidget(self.chk_jmnedict)
        group_term.setLayout(l_term)
        self.dicts_layout.addWidget(group_term)

        group_kanji = QGroupBox("Kanji Dictionaries")
        layout_kanji = QVBoxLayout()
        self.chk_kanjidic = QCheckBox("KANJIDIC (Readings, Meanings, Stroke Order)")
        layout_kanji.addWidget(self.chk_kanjidic)
        group_kanji.setLayout(layout_kanji)
        self.dicts_layout.addWidget(group_kanji)

        group_freq = QGroupBox("Frequency Dictionaries (Coming Soon)")
        l_freq = QVBoxLayout()
        self.chk_jpdb = QCheckBox("JPDBv2 (Anime / Visual Novels)")
        self.chk_jpdb.setChecked(True)
        self.chk_bccwj = QCheckBox("BCCWJ (Literature / News)")
        l_freq.addWidget(self.chk_jpdb)
        l_freq.addWidget(self.chk_bccwj)
        group_freq.setLayout(l_freq)
        self.dicts_layout.addWidget(group_freq)
        
        self.dicts_layout.addStretch()

    def init_ocr_tab(self):
        group = QGroupBox("Engine Settings (Coming Soon)")
        l = QVBoxLayout()
        l.addWidget(QCheckBox("Enable Grayscale Pre-processing (High Accuracy)"))
        l.addWidget(QCheckBox("Enable 3x Upscaling"))
        
        lbl = QLabel("\nFuture feature: Hot-swapping between\nMangaOCR and Cloud OCR models.")
        lbl.setStyleSheet("color: #888;")
        l.addWidget(lbl)
        
        group.setLayout(l)
        self.ocr_layout.addWidget(group)
        self.ocr_layout.addStretch()

    def init_appearance_tab(self):
        group = QGroupBox("Visual Feedback (Coming Soon)")
        form = QFormLayout()
        
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(10, 90)
        slider.setValue(40)
        
        form.addRow("Snip Screen Dimming:", slider)
        form.addRow("Theme:", QCheckBox("Use Dark Overlay"))
        form.addRow("Animation:", QCheckBox("Smooth Window Sliding"))
        
        group.setLayout(form)
        self.appearance_layout.addWidget(group)
        self.appearance_layout.addStretch()

    # --- CORE LOGIC ---

    def add_to_history(self, text):
        self.history_list.addItem(text)
        self.history_list.scrollToBottom()

    def closeEvent(self, event):
        print("Shutting down...")
        self.keyboard_listener.stop() 
        QApplication.quit()           


def on_press(key):
    if key == keyboard.Key.alt_l:
        signals.trigger_snip.emit()

    
if __name__ == '__main__':
    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    result_ui = ResultOverlay()
    snip_ui = SnippingWidget()
    
    listener = keyboard.Listener(on_press=on_press)
    listener.start()
    
    main_window = ControlPanel(listener)
    main_window.show()
    
    sys.exit(app.exec())