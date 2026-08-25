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
                             QFileDialog, QPlainTextEdit)
from PyQt6.QtCore import Qt, QTimer, QEvent, QThread, pyqtSignal

from ui import ResultOverlay, SnippingWidget, signals, USER_SETTINGS, save_settings_disk
from dictionary import set_dictionary_enabled, init_local_dictionaries_to_db

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
            self.default_lbl_text = "App is running. Press 'Alt' to snip and 'Ctrl + Alt' for manual adjustments.\nWorkspace Translation ON: Click history to translate, Double-Click to copy."
        else:
            self.default_lbl_text = "App is running. Press 'Alt' to snip and 'Ctrl + Alt' for manual adjustments.\nClick any history item to instantly copy it to your clipboard."
        
        self.lbl.setText(self.default_lbl_text)

    def evaluate_engine_dropdown(self):
        if hasattr(self, 'combo_trans_engine'):
            is_any_enabled = self.chk_info_trans.isChecked() or self.chk_workspace_trans.isChecked()
            self.combo_trans_engine.setEnabled(is_any_enabled)

            self.toggle_api_key_field()

    def toggle_api_key_field(self):
        is_any_enabled = self.chk_info_trans.isChecked() or self.chk_workspace_trans.isChecked()
        engine_text = self.combo_trans_engine.currentText()

        if hasattr(self, 'input_gemini_key') and hasattr(self, 'input_nvidia_key'):
            self.input_deepl_key.setVisible("DeepL" in engine_text)
            self.input_nvidia_key.setVisible("NVIDIA" in engine_text)

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

        # TAB 4: Anki
        self.tab_anki = QWidget()
        self.anki_layout = QVBoxLayout(self.tab_anki)
        self.init_anki_tab()
        self.tabs.addTab(self.tab_anki, "Anki")

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

        # --- Dynamic Category Groups (Hidden by Default) ---
        self.group_term = QGroupBox("Term Dictionaries")
        self.l_term = QVBoxLayout()
        self.group_term.setLayout(self.l_term)
        self.group_term.hide()
        content_layout.addWidget(self.group_term)

        self.group_kanji = QGroupBox("Kanji Dictionaries")
        self.l_kanji = QVBoxLayout()
        self.group_kanji.setLayout(self.l_kanji)
        self.group_kanji.hide()
        content_layout.addWidget(self.group_kanji)

        self.group_pitch = QGroupBox("Pitch Accent Dictionaries")
        self.l_pitch = QVBoxLayout()
        self.group_pitch.setLayout(self.l_pitch)
        self.group_pitch.hide()
        content_layout.addWidget(self.group_pitch)

        self.group_freq = QGroupBox("Frequency Dictionaries")
        self.l_freq = QVBoxLayout()
        self.group_freq.setLayout(self.l_freq)
        self.group_freq.hide()
        content_layout.addWidget(self.group_freq)
        
        self.group_imported = QGroupBox("Other Dictionaries")
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
        dict_root = Path(os.getcwd()) / "dictionaries"
        if not dict_root.exists():
            return

        for sub_dir in dict_root.iterdir():
            if not sub_dir.is_dir():
                continue
            
            folder_name = sub_dir.name
            
            try:
                total_size_bytes = sum(f.stat().st_size for f in sub_dir.glob('**/*') if f.is_file())
                file_size_mb = round(total_size_bytes / (1024 * 1024), 1)
            except Exception:
                file_size_mb = 1.0

            new_row = DictionaryRow(
                folder_name,
                file_size_mb,
                self.start_install,
                is_custom=True,
                delete_callback=self.check_group_visibility
            )
            
            new_row.mark_as_installed()

            name_lower = folder_name.lower()
            if "[term]" in name_lower: self.l_term.addWidget(new_row)
            elif "[kanji]" in name_lower: self.l_kanji.addWidget(new_row)
            elif "[pitch]" in name_lower or "[accent]" in name_lower: self.l_pitch.addWidget(new_row)
            elif "[freq]" in name_lower or "[frequency]" in name_lower: self.l_freq.addWidget(new_row)
            else: self.l_imported.addWidget(new_row)
            
        # Update visibility for all groups once the scan finishes
        self.update_group_visibility()

    def check_group_visibility(self):
        QTimer.singleShot(50, self.update_group_visibility)

    def update_group_visibility(self):
        groups = [
            (self.group_term, self.l_term),
            (self.group_kanji, self.l_kanji),
            (self.group_pitch, self.l_pitch),
            (self.group_freq, self.l_freq),
            (self.group_imported, self.l_imported)
        ]
        
        for group, layout in groups:
            has_items = False
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if isinstance(widget, DictionaryRow):
                    has_items = True
                    break
            group.setVisible(has_items)

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
            self.start_install,
            is_custom=True, 
            delete_callback=self.check_group_visibility, # Updated callback!
            zip_path=file_path
        )
        
        name_lower = file_name.lower()
        if "[term]" in name_lower: self.l_term.addWidget(new_row)
        elif "[kanji]" in name_lower: self.l_kanji.addWidget(new_row)
        elif "[pitch]" in name_lower or "[accent]" in name_lower: self.l_pitch.addWidget(new_row)
        elif "[freq]" in name_lower or "[frequency]" in name_lower: self.l_freq.addWidget(new_row)
        else: self.l_imported.addWidget(new_row)
        
        # Instantly reveal the category group if it was previously hidden
        self.update_group_visibility()

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
            self.dl_timer.timeout.connect(self.animate_download)
            self.dl_timer.start(50) 

    def update_install_progress(self, percent, current_mb):
        self.progress_bar.setValue(percent)
        self.lbl_dl_stats.setText(f"{current_mb:.1f}/{self.current_total_mb:.1f}MB {percent}%")

    def install_finished(self):
        self.progress_container.hide()
        self.current_row.btn_install.setEnabled(True)
        self.current_row.mark_as_installed()

        from dictionary import init_local_dictionaries_to_db
        init_local_dictionaries_to_db()

    def init_anki_tab(self):
        group_target = QGroupBox("Target Deck & Note Type")
        form_target = QFormLayout()
        
        self.input_anki_deck = QLineEdit(USER_SETTINGS.get("anki_deck", "Default"))
        form_target.addRow("Target Deck:", self.input_anki_deck)

        self.input_anki_model = QLineEdit(USER_SETTINGS.get("anki_model", "Basic"))
        form_target.addRow("Note Type (Model):", self.input_anki_model)
        
        self.btn_fetch_fields = QPushButton("Connect & Fetch Fields")
        self.btn_fetch_fields.setStyleSheet("background-color: #3B82F6; color: white; font-weight: bold; padding: 5px; border-radius: 4px;")
        self.btn_fetch_fields.clicked.connect(self.fetch_anki_fields)
        form_target.addRow("", self.btn_fetch_fields)
        
        group_target.setLayout(form_target)
        self.anki_layout.addWidget(group_target)

        self.group_mapping = QGroupBox("Field Mapping")
        self.form_mapping = QFormLayout()
        
        self.lbl_mapping_status = QLabel("Enter your Note Type and click 'Fetch Fields' to map your data.")
        self.lbl_mapping_status.setStyleSheet("color: #9CA3AF; font-style: italic;")
        self.form_mapping.addRow(self.lbl_mapping_status)
        
        self.group_mapping.setLayout(self.form_mapping)
        self.anki_layout.addWidget(self.group_mapping)

        # --- custom css ---
        group_css = QGroupBox("Custom Dictionary CSS Styling")
        layout_css = QVBoxLayout()
        
        lbl_css_hint = QLabel("Style your dictionary payload using the <b>.sjr-dictionary</b> wrapper class:")
        lbl_css_hint.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        layout_css.addWidget(lbl_css_hint)

        self.input_anki_css = QPlainTextEdit(USER_SETTINGS.get("anki_custom_css", ""))
        self.input_anki_css.setPlaceholderText("Write your custom CSS here...")
        self.input_anki_css.setFixedHeight(130)
        self.input_anki_css.setStyleSheet("font-family: monospace; font-size: 13px; background-color: #1E1E2E; color: #CDD6F4; border: 1px solid #444; border-radius: 4px;")
        layout_css.addWidget(self.input_anki_css)

        group_css.setLayout(layout_css)
        self.anki_layout.addWidget(group_css)

        self.anki_layout.addStretch()

    def fetch_anki_fields(self):
        model_name = self.input_anki_model.text().strip()
        if not model_name:
            self.lbl_mapping_status.setText("Please enter a Note Type first.")
            self.lbl_mapping_status.setStyleSheet("color: #EF4444; font-weight: bold;")
            return

        self.btn_fetch_fields.setText("Fetching...")
        QApplication.processEvents()

        # Call the Anki bridge
        from anki_export import invoke
        fields = invoke("modelFieldNames", modelName=model_name)

        if isinstance(fields, dict) and "error" in fields:
            self.lbl_mapping_status.setText(f"Anki Error: {fields['error']}\nIs Anki open?")
            self.lbl_mapping_status.setStyleSheet("color: #EF4444; font-weight: bold;")
            self.btn_fetch_fields.setText("Connect & Fetch Fields")
            return

        while self.form_mapping.rowCount() > 0:
            self.form_mapping.removeRow(0)

        lbl_success = QLabel("Fields fetched! Map your data to Anki below:")
        lbl_success.setStyleSheet("color: #10B981; font-weight: bold; margin-bottom: 5px;")
        self.form_mapping.addRow(lbl_success)

        app_data_points = [
            ("term", "Expression (Kanji):"),
            ("reading", "Reading (Furigana):"),
            ("meaning", "Definition (Glossary):"),
            ("sentence", "Context Sentence:"),
            ("image", "Screenshot (Image):")
        ]

        self.mapping_combos = {}
        saved_map = USER_SETTINGS.get("anki_field_map", {})

        for key, label in app_data_points:
            combo = QComboBox()
            combo.addItem("-- Ignore --")
            combo.addItems(fields)
            
            if key in saved_map and saved_map[key] in fields:
                combo.setCurrentText(saved_map[key])
            
            self.mapping_combos[key] = combo
            self.form_mapping.addRow(label, combo)

        self.btn_fetch_fields.setText("Connect & Fetch Fields")

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

        # --- Unified AI & Translation ---
        group_ai = QGroupBox("Unified AI & Translation Backend")
        form_ai = QFormLayout()

        self.combo_ai_engine = QComboBox()
        self.combo_ai_engine.addItems([
            "Google (Gemini & Translate)", 
            "NVIDIA NIM (Cloud)", 
            "Local LLM (Ollama/LM Studio)", 
            "DeepL (Text Only)"
        ])
        
        # Set dropdown based on saved engine
        engine_map = {"google": 0, "nvidia": 1, "local": 2, "deepl": 3}
        self.combo_ai_engine.setCurrentIndex(engine_map.get(USER_SETTINGS.get("ai_engine", "google"), 0))
        form_ai.addRow("Active Engine:", self.combo_ai_engine)

        self.input_api_key = QLineEdit(USER_SETTINGS.get("global_api_key", ""))
        self.input_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.input_api_key.setPlaceholderText("Leave blank for Local LLMs")
        form_ai.addRow("API Key:", self.input_api_key)

        self.input_base_url = QLineEdit(USER_SETTINGS.get("local_base_url", ""))
        self.input_base_url.setPlaceholderText("http://localhost:11434/v1")
        form_ai.addRow("Local Base URL:", self.input_base_url)

        self.input_vision_model = QLineEdit(USER_SETTINGS.get("vision_model", ""))
        self.input_vision_model.setPlaceholderText("e.g. meta/llama-3.2-90b-vision-instruct")
        form_ai.addRow("Vision Model (AI Fix):", self.input_vision_model)

        self.input_text_model = QLineEdit(USER_SETTINGS.get("text_model", ""))
        self.input_text_model.setPlaceholderText("e.g. meta/llama-3.1-70b-instruct")
        form_ai.addRow("Text Model (Translate):", self.input_text_model)

        # Toggles
        self.chk_ai_fix = QCheckBox("Enable AI OCR Fix (✨)")
        self.chk_ai_fix.setChecked(USER_SETTINGS.get("enable_ai_fix", True))
        
        self.chk_info_trans = QCheckBox("Enable Info Box Translation (Aあ)")
        self.chk_info_trans.setChecked(USER_SETTINGS.get("enable_translation", True))
        
        form_ai.addRow(self.chk_ai_fix)
        form_ai.addRow(self.chk_info_trans)

        group_ai.setLayout(form_ai)
        content_layout.addWidget(group_ai)

        # --- AnkiConnect Integration ---
        group_anki = QGroupBox("AnkiConnect (Card Mining)")
        form_anki = QFormLayout()

        self.input_anki_deck = QLineEdit(USER_SETTINGS.get("anki_deck", "Default"))
        form_anki.addRow("Target Deck:", self.input_anki_deck)

        self.input_anki_model = QLineEdit(USER_SETTINGS.get("anki_model", "Basic"))
        form_anki.addRow("Note Type (Model):", self.input_anki_model)

        group_anki.setLayout(form_anki)
        content_layout.addWidget(group_anki)

        # --- Display Features ---
        group_display = QGroupBox("Dictionary Display")
        l_display = QVBoxLayout()
        
        self.chk_show_pitch = QCheckBox("Show Pitch Accent Graphs")
        self.chk_show_pitch.setChecked(USER_SETTINGS.get("show_pitch", True))
        
        self.chk_show_freq = QCheckBox("Show Frequency Tags (e.g., Common)")
        self.chk_show_freq.setChecked(USER_SETTINGS.get("show_freq", True))
        
        self.chk_show_jlpt = QCheckBox("Show JLPT Difficulty (N5 - N1)")
        self.chk_show_jlpt.setChecked(USER_SETTINGS.get("show_jlpt", True))
        
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
        USER_SETTINGS["enable_translation"] = self.chk_info_trans.isChecked()
        
        engine_text = self.combo_ai_engine.currentText()
        if "Google" in engine_text:
            USER_SETTINGS["ai_engine"] = "google"
        elif "NVIDIA" in engine_text:
            USER_SETTINGS["ai_engine"] = "nvidia"
        elif "Local" in engine_text:
            USER_SETTINGS["ai_engine"] = "local"
        elif "DeepL" in engine_text:
            USER_SETTINGS["ai_engine"] = "deepl"
            
        USER_SETTINGS["global_api_key"] = self.input_api_key.text().strip()
        USER_SETTINGS["local_base_url"] = self.input_base_url.text().strip()
        USER_SETTINGS["vision_model"] = self.input_vision_model.text().strip()
        USER_SETTINGS["text_model"] = self.input_text_model.text().strip()

        USER_SETTINGS["show_pitch"] = self.chk_show_pitch.isChecked()
        USER_SETTINGS["show_freq"] = self.chk_show_freq.isChecked()
        USER_SETTINGS["show_jlpt"] = self.chk_show_jlpt.isChecked()

        USER_SETTINGS["anki_deck"] = self.input_anki_deck.text().strip() or "Default"
        USER_SETTINGS["anki_model"] = self.input_anki_model.text().strip() or "Basic"
        USER_SETTINGS["anki_deck"] = self.input_anki_deck.text().strip()
        USER_SETTINGS["anki_model"] = self.input_anki_model.text().strip()
        USER_SETTINGS["anki_custom_css"] = self.input_anki_css.toPlainText()

        if hasattr(self, 'mapping_combos'):
            field_map = {}
            for key, combo in self.mapping_combos.items():
                val = combo.currentText()
                if val != "-- Ignore --":
                    field_map[key] = val
            USER_SETTINGS["anki_field_map"] = field_map

        save_settings_disk()
        self.btn_save_settings.setText("Settings Saved.")
        self.btn_save_settings.setStyleSheet("background-color: #10B981; color: white; font-weight: bold; padding: 10px; border-radius: 5px;")
        
        from PyQt6.QtCore import QTimer
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

# --- KEY DETECTION ---
modifier_state = {
    "ctrl_held": False
}

def on_press(key):
    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        modifier_state["ctrl_held"] = True

    if key == keyboard.Key.alt_l:
        if modifier_state["ctrl_held"]:
            signals.trigger_manual_snip.emit()
        else:
            signals.trigger_quick_snip.emit()

def on_release(key):
    if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
        modifier_state["ctrl_held"] = False

    
if __name__ == '__main__':
    app = QApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    result_ui = ResultOverlay()
    snip_ui = SnippingWidget()

    from dictionary import init_local_dictionaries_to_db
    init_local_dictionaries_to_db()
    
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    
    main_window = ControlPanel(listener)
    main_window.show()
    
    sys.exit(app.exec())