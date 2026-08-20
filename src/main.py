import sys
import signal
import os
import zipfile
import shutil
from pathlib import Path
from pynput import keyboard
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QListWidget, QTabWidget, QGroupBox, 
                             QCheckBox, QSlider, QFormLayout, QComboBox, 
                             QScrollArea, QLineEdit, QPushButton, QProgressBar,
                             QFileDialog)
from PyQt6.QtCore import Qt, QTimer, QEvent, QThread, pyqtSignal

from ui import ResultOverlay, SnippingWidget, signals, USER_SETTINGS
from dictionary import set_dictionary_enabled

class DictInstallWorker(QThread):
    progress = pyqtSignal(int, float) # percent, current_mb
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, zip_path, extract_dir):
        super().__init__()
        self.zip_path = zip_path
        self.extract_dir = extract_dir

    def run(self):
        try:
            os.makedirs(self.extract_dir, exist_ok=True)
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                file_list = zip_ref.infolist()
                total_size = sum(f.file_size for f in file_list)
                extracted_size = 0

                for file_info in file_list:
                    zip_ref.extract(file_info, self.extract_dir)
                    extracted_size += file_info.file_size

                    percent = int((extracted_size / total_size) * 100)
                    current_mb = extracted_size / (1024 * 1024)

                    self.progress.emit(percent, current_mb)

            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class DictionaryRow(QWidget):
    def __init__(self, name, size_mb, install_callback, is_custom=False, delete_callback=None, zip_path=None):
        super().__init__()
        self.name = name
        self.size_mb = size_mb
        self.is_installed = False
        self.is_custom = is_custom
        self.install_callback = install_callback
        self.delete_callback = delete_callback
        self.zip_path = zip_path
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        
        self.checkbox = QCheckBox(name)
        self.checkbox.setEnabled(False) 
        # --- NEW: Hook up checkbox toggle to dictionary engine ---
        self.checkbox.toggled.connect(self.on_checkbox_toggled)
        
        layout.addWidget(self.checkbox)
        layout.addStretch()
        
        self.btn_install = QPushButton("Install")
        self.btn_install.setFixedSize(80, 25)
        self.btn_install.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_uninstalled_style()
        
        self.btn_install.installEventFilter(self)
        self.btn_install.clicked.connect(self.handle_click)
        
        layout.addWidget(self.btn_install)

    def get_clean_name(self):
        """Removes tags and file extensions to match the internal dictionary title."""
        return self.name.replace(".zip", "").replace("[Term]", "").replace("[Kanji]", "").replace("[Freq]", "").strip()

    def on_checkbox_toggled(self, checked):
        # Notify dictionary.py whether this dictionary should be included in searches
        set_dictionary_enabled(self.get_clean_name(), checked)

    def set_uninstalled_style(self):
        self.btn_install.setText("Install")
        self.btn_install.setStyleSheet("""
            QPushButton { background-color: transparent; color: #EF4444; border: 1px solid #EF4444; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: rgba(239, 68, 68, 0.1); }
        """)

    def set_installed_style(self):
        self.btn_install.setText("Installed")
        self.btn_install.setStyleSheet("""
            QPushButton { background-color: transparent; color: #10B981; border: 1px solid #10B981; border-radius: 4px; font-weight: bold; }
        """)

    def handle_click(self):
        if self.is_installed:
            if self.is_custom:
                # Custom imported dictionaries are permanently deleted on uninstall
                extract_path = os.path.join(os.getcwd(), "dictionaries", self.name.replace(".zip", ""))
                if os.path.exists(extract_path):
                    shutil.rmtree(extract_path)

                # Ensure it's disabled in backend before deleting the row
                set_dictionary_enabled(self.get_clean_name(), False)

                if self.delete_callback:
                    self.delete_callback()
                self.setParent(None)
                self.deleteLater()
            else:
                # Default dictionaries just reset to Uninstalled state
                self.is_installed = False
                self.checkbox.setChecked(False)
                self.checkbox.setEnabled(False)
                self.set_uninstalled_style()
        else:
            self.install_callback(self)

    def mark_as_installed(self):
        self.is_installed = True
        self.checkbox.setEnabled(True)
        self.checkbox.setChecked(True)
        self.set_installed_style()
        set_dictionary_enabled(self.get_clean_name(), True)

    def eventFilter(self, obj, event):
        if obj == self.btn_install and self.is_installed:
            if event.type() == QEvent.Type.Enter:
                self.btn_install.setText("Uninstall")
                self.btn_install.setStyleSheet("""
                    QPushButton { background-color: rgba(239, 68, 68, 0.1); color: #EF4444; border: 1px solid #EF4444; border-radius: 4px; font-weight: bold; }
                """)
            elif event.type() == QEvent.Type.Leave:
                self.set_installed_style()
        return super().eventFilter(obj, event)

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

        # --- Import Button ---
        self.btn_import_dict = QPushButton("📥 Import Local Yomitan Dictionary (.zip)")
        self.btn_import_dict.setFixedHeight(35)
        self.btn_import_dict.setStyleSheet("""
            QPushButton { background-color: #3B82F6; color: white; font-weight: bold; border-radius: 5px; margin-bottom: 10px; }
            QPushButton:hover { background-color: #2563EB; }
        """)
        self.btn_import_dict.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_dict.clicked.connect(self.import_local_dictionary)
        content_layout.addWidget(self.btn_import_dict)

        # --- Term Dictionaries ---
        group_term = QGroupBox("Term Dictionaries")
        self.l_term = QVBoxLayout() 
        self.l_term.addWidget(DictionaryRow("Jitendex (Japanese-to-English)", 45.2, self.start_install, 
                                            zip_path=os.path.join(os.getcwd(), "default_zips", "jitendex.zip")))
        self.l_term.addWidget(DictionaryRow("JMnedict (Proper Names)", 12.8, self.start_install, 
                                            zip_path=os.path.join(os.getcwd(), "default_zips", "jmnedict.zip")))
        group_term.setLayout(self.l_term) 
        content_layout.addWidget(group_term)

        # --- Kanji Dictionaries ---
        group_kanji = QGroupBox("Kanji Dictionaries")
        self.l_kanji = QVBoxLayout()
        self.l_kanji.addWidget(DictionaryRow("KANJIDIC (Readings, Meanings)", 6.4, self.start_install, 
                                             zip_path=os.path.join(os.getcwd(), "default_zips", "kanjidic.zip")))
        group_kanji.setLayout(self.l_kanji)
        content_layout.addWidget(group_kanji)

        # --- Pitch Accent Dictionaries ---
        group_pitch = QGroupBox("Pitch Accent Dictionaries")
        self.l_pitch = QVBoxLayout()
        self.l_pitch.addWidget(DictionaryRow("アクセント辞典v2 (Pitch Accent)", 4.2, self.start_install, 
                                             zip_path=os.path.join(os.getcwd(), "default_zips", "アクセント辞典v2_pitch.zip")))
        group_pitch.setLayout(self.l_pitch)
        content_layout.addWidget(group_pitch)

        # --- Frequency Dictionaries ---
        group_freq = QGroupBox("Frequency Dictionaries")
        self.l_freq = QVBoxLayout()
        self.l_freq.addWidget(DictionaryRow("JPDBv2 (Anime / Visual Novels)", 2.1, self.start_install, 
                                            zip_path=os.path.join(os.getcwd(), "default_zips", "jpdb_freq.zip")))
        group_freq.setLayout(self.l_freq)
        content_layout.addWidget(group_freq)
        
        # --- Hidden Fallback Group ---
        self.group_imported = QGroupBox("Imported Dictionaries")
        self.l_imported = QVBoxLayout()
        self.group_imported.setLayout(self.l_imported)
        self.group_imported.hide() 
        content_layout.addWidget(self.group_imported)

        content_layout.addStretch()
        scroll_area.setWidget(content_widget)
        self.dicts_layout.addWidget(scroll_area)

        # --- Progress Bar Container ---
        self.progress_container = QWidget()
        progress_layout = QVBoxLayout(self.progress_container)
        progress_layout.setContentsMargins(5, 10, 5, 0)
        
        self.lbl_dl_name = QLabel("Dictionary Name")
        self.lbl_dl_name.setStyleSheet("font-weight: bold; color: #EF4444;") 
        
        bottom_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(4) 
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { background-color: #333; border: none; border-radius: 2px; }
            QProgressBar::chunk { background-color: #EF4444; border-radius: 2px; }
        """)
        
        self.lbl_dl_stats = QLabel("0/0MB 0%")
        self.lbl_dl_stats.setStyleSheet("font-size: 12px; color: #EF4444; font-weight: bold;")
        
        bottom_row.addWidget(self.progress_bar)
        bottom_row.addWidget(self.lbl_dl_stats)
        
        progress_layout.addWidget(self.lbl_dl_name)
        progress_layout.addLayout(bottom_row)
        
        self.progress_container.hide() 
        self.dicts_layout.addWidget(self.progress_container)
        self.scan_existing_dictionaries()

    def scan_existing_dictionaries(self):
        """Scans the 'dictionaries' folder on startup and restores installed custom dictionaries to the UI."""
        dict_root = Path(os.getcwd()) / "dictionaries"
        if not dict_root.exists():
            return

        for sub_dir in dict_root.iterdir():
            if not sub_dir.is_dir():
                continue
            
            folder_name = sub_dir.name
            
            # Calculate the total size of the extracted folder in MB
            try:
                total_size_bytes = sum(f.stat().st_size for f in sub_dir.glob('**/*') if f.is_file())
                file_size_mb = round(total_size_bytes / (1024 * 1024), 1)
            except Exception:
                file_size_mb = 1.0

            # Rebuild the dictionary row
            new_row = DictionaryRow(
                folder_name,
                file_size_mb,
                self.start_install,
                is_custom=True,
                delete_callback=self.check_imported_group
            )
            
            # Instantly mark it as installed and enable its checkbox
            new_row.mark_as_installed()

            name_lower = folder_name.lower() # or file_name.lower() in the import method
            if "[term]" in name_lower:
                self.l_term.addWidget(new_row)
            elif "[kanji]" in name_lower:
                self.l_kanji.addWidget(new_row)
            elif "[pitch]" in name_lower or "[accent]" in name_lower:
                self.l_pitch.addWidget(new_row)
            elif "[freq]" in name_lower or "[frequency]" in name_lower:
                self.l_freq.addWidget(new_row)
            else:
                self.l_imported.addWidget(new_row)
                self.group_imported.show()

    def check_imported_group(self):
        QTimer.singleShot(50, self.update_imported_visibility)

    def update_imported_visibility(self):
        has_items = False
        for i in range(self.l_imported.count()):
            widget = self.l_imported.itemAt(i).widget()
            if isinstance(widget, DictionaryRow):
                has_items = True
                break
        if not has_items:
            self.group_imported.hide()

    def import_local_dictionary(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Yomitan Dictionary Zip", "", "Zip Files (*.zip)")
        if not file_path:
            return
            
        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 1)
        file_name = os.path.basename(file_path)
        
        new_row = DictionaryRow(
            f"{file_name}", 
            file_size_mb, 
            self.start_install, # Updated callback name
            is_custom=True, 
            delete_callback=self.check_imported_group,
            zip_path=file_path
        )
        
        name_lower = folder_name.lower() 
        if "[term]" in name_lower:
            self.l_term.addWidget(new_row)
        elif "[kanji]" in name_lower:
            self.l_kanji.addWidget(new_row)
        elif "[pitch]" in name_lower or "[accent]" in name_lower:
            self.l_pitch.addWidget(new_row)
        elif "[freq]" in name_lower or "[frequency]" in name_lower:
            self.l_freq.addWidget(new_row)
        else:
            self.l_imported.addWidget(new_row)
            self.group_imported.show()

    # --- EXTRACTION LOGIC ---
    def start_install(self, row_widget):
        if not self.progress_container.isHidden():
            return 
            
        self.current_row = row_widget
        self.current_total_mb = row_widget.size_mb
        
        self.progress_container.show()
        self.lbl_dl_name.setText(row_widget.name)
        self.progress_bar.setValue(0)
        self.lbl_dl_stats.setText(f"0.0/{self.current_total_mb:.1f}MB 0%")
        
        self.current_row.btn_install.setEnabled(False)
        self.current_row.btn_install.setText("Extracting...")

        if row_widget.zip_path:
            # Create a 'dictionaries' folder in your project root
            extract_path = os.path.join(os.getcwd(), "dictionaries", row_widget.name.replace(".zip", ""))
            
            # Start the background thread
            self.worker = DictInstallWorker(row_widget.zip_path, extract_path)
            self.worker.progress.connect(self.update_install_progress)
            self.worker.finished.connect(self.install_finished)
            self.worker.start()
        else:
            # Fallback mock timer for the hardcoded built-in dictionaries
            self.current_mb = 0.0
            self.dl_timer = QTimer()
            self.dl_timer.timeout.connect(self.animate_download) # Keep your old animate_download method around for these!
            self.dl_timer.start(50) 

    def update_install_progress(self, percent, current_mb):
        self.progress_bar.setValue(percent)
        self.lbl_dl_stats.setText(f"{current_mb:.1f}/{self.current_total_mb:.1f}MB {percent}%")

    def install_finished(self):
        self.progress_container.hide()
        self.current_row.btn_install.setEnabled(True)
        self.current_row.mark_as_installed()

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
        content_layout.addWidget(group_capture) 

        # --- AI Fix ---
        group_ai = QGroupBox("AI Fix")
        form_ai = QFormLayout()

        self.chk_ai_fix = QCheckBox("Enable AI Fix (✨)")
        self.chk_ai_fix.setChecked(USER_SETTINGS.get("enable_ai_fix", True))

        self.input_gemini_key = QLineEdit(USER_SETTINGS.get("gemini_api_key", ""))
        self.input_gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_gemini_key.setPlaceholderText("Go to aistudio.google to obtain a key.")

        form_ai.addRow(self.chk_ai_fix)
        form_ai.addRow("Gemini API Key:", self.input_gemini_key)
        
        group_ai.setLayout(form_ai)
        content_layout.addWidget(group_ai)

        # --- AI Translation ---
        group_trans = QGroupBox("AI Translation")
        form_trans = QFormLayout()
        
        self.combo_trans_engine = QComboBox()
        self.combo_trans_engine.addItems(["Google Translate (Free)", "DeepL API (Requires Key)"])
        # Set default based on settings
        if USER_SETTINGS.get("translation_engine", "google") == "deepl":
            self.combo_trans_engine.setCurrentIndex(1)
        form_trans.addRow("Active Engine:", self.combo_trans_engine)

        self.input_api_key = QLineEdit(USER_SETTINGS.get("deepl_api_key", ""))
        self.input_api_key.setPlaceholderText("Enter DeepL API Key")
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        form_trans.addRow("API Key:", self.input_api_key)
        
        self.chk_info_trans = QCheckBox("Enable in Info Box (Aあ)")
        self.chk_info_trans.setChecked(USER_SETTINGS.get("enable_translation", True))
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
        content_layout.addWidget(group_display) 

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
        content_layout.addWidget(group_app) 

        content_layout.addStretch()

        self.btn_save_settings = QPushButton("Save Settings")
        self.btn_save_settings.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        self.btn_save_settings.clicked.connect(self.save_settings)
        content_layout.addWidget(self.btn_save_settings)

        scroll_area.setWidget(content_widget)
        self.settings_layout.addWidget(scroll_area)

    def save_settings(self):
        USER_SETTINGS["enable_ai_fix"] = self.chk_ai_fix.isChecked()
        USER_SETTINGS["gemini_api_key"] = self.input_gemini_key.text().strip()
        
        USER_SETTINGS["enable_translation"] = self.chk_info_trans.isChecked()
        engine_text = self.combo_trans_engine.currentText()
        USER_SETTINGS["translation_engine"] = "deepl" if "DeepL" in engine_text else "google"
        USER_SETTINGS["deepl_api_key"] = self.input_api_key.text().strip()

        self.btn_save_settings.setText("Settings Saved.")
        self.btn_save_settings.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        
        # Reset button text after 2 seconds
        QTimer.singleShot(2000, lambda: self.btn_save_settings.setText("Save Settings"))
        QTimer.singleShot(2000, lambda: self.btn_save_settings.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 10px; border-radius: 5px;"))

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