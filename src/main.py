import sys
import signal
from pynput import keyboard
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QListWidget, QTabWidget, QGroupBox, 
                             QCheckBox, QSlider, QFormLayout, QComboBox, 
                             QScrollArea, QLineEdit)
from PyQt6.QtCore import Qt, QTimer

from ui import ResultOverlay, SnippingWidget, signals

class ControlPanel(QWidget):
    def update_info_state(self, is_enabled):
        self.combo_info_trigger.setEnabled(is_enabled)
        self.evaluate_engine_dropdown()

    def update_workspace_state(self, is_enabled):
        self.combo_workspace_trigger.setEnabled(is_enabled)
        self.evaluate_engine_dropdown()

        if is_enabled:
            self.default_lbl_text = "App is running. Press 'Alt + Click' to snip.\nWorkspace Translation ON: Click history to translate, Double-Click to copy."
        else:
            self.default_lbl_text = "App is running. Press 'Alt + Click' to snip.\nClick any history item to instantly copy it to your clipboard."
        
        self.lbl.setText(self.default_lbl_text)

    def evaluate_engine_dropdown(self):
        if hasattr(self, 'combo_trans_engine'):
            is_any_enabled = self.chk_info_trans.isChecked() or self.chk_workspace_trans.isChecked()
            self.combo_trans_engine.setEnabled(is_any_enabled)

            self.toggle_api_key_field()

    def toggle_api_key_field(self):
        is_any_enabled = self.chk_info_trans.isChecked() or self.chk_workspace_trans.isChecked()
        is_api_selected = "API" in self.combo_trans_engine.currentText()

        if hasattr(self, 'input_api_key'):
            self.input_api_key.setEnabled(is_any_enabled and is_api_selected)

    def __init__(self, keyboard_listener):
        super().__init__()
        self.keyboard_listener = keyboard_listener
        
        self.setWindowTitle("Simple JP Reader - Workspace")
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
        
        # click2copy
        self.history_list.itemClicked.connect(self.copy_history_item)
        
        self.history_layout.addWidget(self.history_list)
        self.tabs.addTab(self.tab_history, "History")
        
        # TAB 2: Dictionaries
        self.tab_dicts = QWidget()
        self.dicts_layout = QVBoxLayout(self.tab_dicts)
        self.init_dictionary_tab()
        self.tabs.addTab(self.tab_dicts, "Dictionaries")

        # TAB 3: Settings
        self.tab_settings = QWidget()
        self.settings_layout = QVBoxLayout(self.tab_settings)
        self.init_settings_tab()
        self.tabs.addTab(self.tab_settings, "Settings")

        signals.update_history.connect(self.add_to_history)

    # copy logic
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
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        group_term = QGroupBox("Term Dictionaries  (Coming Soon)")
        l_term = QVBoxLayout()
        self.chk_jitendex = QCheckBox("Jitendex (Japanese-to-English)")
        self.chk_jitendex.setChecked(True)
        self.chk_jmnedict = QCheckBox("JMnedict (Proper Names)")
        l_term.addWidget(self.chk_jitendex)
        l_term.addWidget(self.chk_jmnedict)
        group_term.setLayout(l_term)
        content_layout.addWidget(group_term) # Changed to content_layout

        group_kanji = QGroupBox("Kanji Dictionaries  (Coming Soon)")
        layout_kanji = QVBoxLayout()
        self.chk_kanjidic = QCheckBox("KANJIDIC (Readings, Meanings, Stroke Order)")
        layout_kanji.addWidget(self.chk_kanjidic)
        group_kanji.setLayout(layout_kanji)
        content_layout.addWidget(group_kanji) # Changed to content_layout

        group_freq = QGroupBox("Frequency Dictionaries (Coming Soon)")
        l_freq = QVBoxLayout()
        self.chk_jpdb = QCheckBox("JPDBv2 (Anime / Visual Novels)")
        self.chk_jpdb.setChecked(True)
        self.chk_bccwj = QCheckBox("BCCWJ (Literature / News)")
        l_freq.addWidget(self.chk_jpdb)
        l_freq.addWidget(self.chk_bccwj)
        group_freq.setLayout(l_freq)
        content_layout.addWidget(group_freq) # Changed to content_layout
        
        content_layout.addStretch()
        scroll_area.setWidget(content_widget)
        self.dicts_layout.addWidget(scroll_area)

    def init_settings_tab(self):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # --- Capture & OCR ---
        group_capture = QGroupBox("Capture and OCR")
        form_capture = QFormLayout()
        
        self.combo_ocr_engine = QComboBox()
        self.combo_ocr_engine.addItems(["MangaOCR (Local)", "OneOCR (Windows Native)", "Google Lens (Cloud)"])
        form_capture.addRow("Active OCR Engine:", self.combo_ocr_engine)
        
        self.lbl_hotkey = QLabel("Alt + Left Click (Hardcoded)")
        self.lbl_hotkey.setStyleSheet("color: #888;")
        form_capture.addRow("Capture Hotkey:", self.lbl_hotkey)
        
        self.slider_dim = QSlider(Qt.Orientation.Horizontal)
        self.slider_dim.setRange(0, 100)
        self.slider_dim.setValue(40)
        form_capture.addRow("Snip Screen Dimming:", self.slider_dim)

        self.chk_auto_copy = QCheckBox("Auto-copy to clipboard on snip")
        self.chk_auto_copy.setChecked(False)
        form_capture.addRow("", self.chk_auto_copy)
        
        group_capture.setLayout(form_capture)
        content_layout.addWidget(group_capture) # Changed from settings_layout

        # --- AI Translation ---
        group_trans = QGroupBox("AI Translation")
        form_trans = QFormLayout()
        
        self.combo_trans_engine = QComboBox()
        self.combo_trans_engine.addItems(["Google Translate (Free)", "DeepL API (Requires Key)"])
        form_trans.addRow("Active Engine:", self.combo_trans_engine)

        self.input_api_key = QLineEdit()
        self.input_api_key.setPlaceholderText("Enter API Key")
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form_trans.addRow("API Key:", self.input_api_key)
        
        self.chk_info_trans = QCheckBox("Enable in Info Box")
        self.chk_info_trans.setChecked(False)
        self.combo_info_trigger = QComboBox()
        self.combo_info_trigger.addItems(["Click sentence to translate", "Auto-translate on snip"])
        form_trans.addRow(self.chk_info_trans, self.combo_info_trigger)

        self.chk_workspace_trans = QCheckBox("Enable in Workspace")
        self.chk_workspace_trans.setChecked(False)
        self.combo_workspace_trigger = QComboBox()
        self.combo_workspace_trigger.addItems(["Click: Translate | Double-Click: Copy"])
        form_trans.addRow(self.chk_workspace_trans, self.combo_workspace_trigger)

        group_trans.setLayout(form_trans)
        content_layout.addWidget(group_trans)
        
        self.chk_info_trans.toggled.connect(self.update_info_state)
        self.chk_workspace_trans.toggled.connect(self.update_workspace_state)
        self.combo_trans_engine.currentTextChanged.connect(lambda: self.toggle_api_key_field())
        
        self.update_info_state(self.chk_info_trans.isChecked())
        self.update_workspace_state(self.chk_workspace_trans.isChecked())
        self.toggle_api_key_field()

        # --- Display Features ---
        group_display = QGroupBox("Dictionary Display")
        l_display = QVBoxLayout()
        self.chk_show_pitch = QCheckBox("Show Pitch Accent Graphs")
        self.chk_show_pitch.setChecked(True)
        self.chk_show_freq = QCheckBox("Show Frequency Tags (e.g., Common)")
        self.chk_show_freq.setChecked(True)
        self.chk_show_jlpt = QCheckBox("Show JLPT Difficulty (N5 - N1)")
        self.chk_show_jlpt.setChecked(True)
        
        l_display.addWidget(self.chk_show_pitch)
        l_display.addWidget(self.chk_show_freq)
        l_display.addWidget(self.chk_show_jlpt)
        group_display.setLayout(l_display)
        content_layout.addWidget(group_display) # Changed from settings_layout

        # --- Appearance ---
        group_app = QGroupBox("Appearance")
        form_app = QFormLayout()
        
        self.combo_theme = QComboBox()
        self.combo_theme.addItems(["Dark Overlay", "Light Overlay", "Transparent"])
        form_app.addRow("Base Theme:", self.combo_theme)

        self.slider_font = QSlider(Qt.Orientation.Horizontal)
        self.slider_font.setRange(12, 36)
        self.slider_font.setValue(18)
        form_app.addRow("Japanese Text Size:", self.slider_font)

        
        group_app.setLayout(form_app)
        content_layout.addWidget(group_app) # Changed from settings_layout

        content_layout.addStretch()

        scroll_area.setWidget(content_widget)
        self.settings_layout.addWidget(scroll_area)

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