import os
import sys
import time
import json
import unittest
import numpy as np
from PIL import Image

# Ensure src is on python path
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

# Set Qt offscreen platform before importing PyQt6
os.environ["QT_QPA_PLATFORM"] = "offscreen"


class TestDeinflectBrutal(unittest.TestCase):
    def setUp(self):
        import deinflect
        self.deinflect = deinflect

    def test_rules_loaded_comprehensively(self):
        self.assertGreater(len(self.deinflect.RULES), 500, "Deinflect rules should contain over 500 rules.")

    def test_plain_past(self):
        # 食べた -> 食べる (past)
        res = self.deinflect.get_base_forms("食べた")
        terms = [r["term"] for r in res]
        self.assertIn("食べる", terms)
        for r in res:
            if r["term"] == "食べる":
                self.assertIn("past", r["grammar_path"])

    def test_te_form(self):
        # 食べて -> 食べる (-te)
        res = self.deinflect.get_base_forms("食べて")
        terms = [r["term"] for r in res]
        self.assertIn("食べる", terms)

    def test_polite_past(self):
        # 食べました -> 食べる
        res = self.deinflect.get_base_forms("食べました")
        terms = [r["term"] for r in res]
        self.assertIn("食べる", terms)

    def test_negative(self):
        # 行かない -> 行く (negative)
        res = self.deinflect.get_base_forms("行かない")
        terms = [r["term"] for r in res]
        self.assertIn("行く", terms)

    def test_potential(self):
        # 飲める -> 飲む (potential)
        res = self.deinflect.get_base_forms("飲める")
        terms = [r["term"] for r in res]
        self.assertIn("飲む", terms)

    def test_complex_multi_level_conjugation(self):
        # 走らせられたくなかったら (causative + passive + tai + negative + conditional)
        res = self.deinflect.get_base_forms("走らせられたくなかったら")
        self.assertIsInstance(res, list)
        self.assertGreater(len(res), 1)
        # Ensure it terminates quickly without infinite loops
        self.assertLess(len(res), 50)

    def test_edge_cases_and_invalid_inputs(self):
        self.assertEqual(self.deinflect.get_base_forms(""), [])
        self.assertEqual(self.deinflect.get_base_forms(None), [])
        self.assertEqual(self.deinflect.get_base_forms(12345), [])
        self.assertEqual(self.deinflect.get_base_forms("hello"), [{"term": "hello", "grammar_path": []}])
        
        # Extremely long string
        long_str = "ああああああ" * 50
        res = self.deinflect.get_base_forms(long_str)
        self.assertIsInstance(res, list)


class TestDictionaryAndSQLiteBrutal(unittest.TestCase):
    def setUp(self):
        import dictionary
        self.dict_mod = dictionary

    def test_parse_yomitan_content(self):
        p = self.dict_mod.parse_yomitan_content
        self.assertEqual(p(None), "")
        self.assertEqual(p(""), "")
        self.assertEqual(p(123), "123")
        self.assertEqual(p({"tag": "span", "content": "test"}), "<span>test</span>")
        self.assertEqual(p({"tag": "rt", "content": "よみ"}), '<span style="color: #9CA3AF; font-size: 0.85em;">(よみ)</span>')
        self.assertEqual(p({"tag": "br"}), "<br>")
        self.assertEqual(p([{"tag": "b", "content": "hello"}, " world"]), "<b>hello</b> world")

    def test_clean_dict_name_helper(self):
        c = self.dict_mod._clean_dict_name
        self.assertEqual(c("[Kanji] KANJIDIC (English) (Recommended) (Kanji)"), "kanjidic (english) (recommended)")
        self.assertEqual(c("KANJIDIC (English) (Recommended).zip"), "kanjidic (english) (recommended)")
        self.assertEqual(c("jitendex-yomitan"), "jitendex-yomitan")
        self.assertEqual(c("[Term] JMdict (English).zip"), "jmdict (english)")
        self.assertEqual(c(""), "")
        self.assertEqual(c(None), "")

    def test_is_dict_enabled_matching(self):
        self.dict_mod.ENABLED_DICTIONARIES.clear()
        # When empty, should default to True so lookups work before UI init
        self.assertTrue(self.dict_mod.is_dict_enabled("[Kanji] KANJIDIC (English) (Recommended) (Kanji)"))

        # Enable via clean name (as main.py does)
        self.dict_mod.set_dictionary_enabled("KANJIDIC (English) (Recommended)", True)
        self.assertTrue(self.dict_mod.is_dict_enabled("[Kanji] KANJIDIC (English) (Recommended) (Kanji)"))
        self.assertTrue(self.dict_mod.is_dict_enabled("KANJIDIC (English) (Recommended)"))

        # Disable
        self.dict_mod.set_dictionary_enabled("KANJIDIC (English) (Recommended)", False)
        # Clear enabled set to test offline query cleanly
        self.dict_mod.ENABLED_DICTIONARIES.clear()

    def test_query_sqlite_word_and_kanji(self):
        self.dict_mod.ENABLED_DICTIONARIES.clear()
        
        # Test word lookup
        res_cat = self.dict_mod.query_sqlite("猫")
        self.assertIsNotNone(res_cat, "Word '猫' should be found in local SQLite database.")
        self.assertIn("meanings_list", res_cat)
        self.assertGreater(len(res_cat["meanings_list"]), 0)
        self.assertIn("meaning", res_cat)
        self.assertTrue(len(res_cat["meaning"]) > 0)

        # Test kanji lookup
        res_sun = self.dict_mod.query_sqlite("日")
        self.assertIsNotNone(res_sun, "Kanji '日' should be found in local SQLite database.")
        self.assertIn("meanings_list", res_sun)

    def test_get_real_data_with_deinflection(self):
        self.dict_mod.ENABLED_DICTIONARIES.clear()
        # '食べた' should deinflect to '食べる' and succeed offline without hitting Jisho
        res = self.dict_mod.get_real_data("食べた")
        self.assertIsNotNone(res)
        self.assertIn("meanings_list", res)
        self.assertIn("grammar", res)
        self.assertIn("past", res["grammar"])

    def test_query_sqlite_injection_resiliency(self):
        # Ensure queries with dangerous characters do not raise SQL errors
        bad_inputs = ["' OR '1'='1", "'; DROP TABLE words; --", "\x00", "SELECT * FROM", "None"]
        for bad in bad_inputs:
            try:
                res = self.dict_mod.query_sqlite(bad)
                # Should return None safely without crashing
                self.assertIsNone(res)
            except Exception as e:
                self.fail(f"query_sqlite crashed on input {repr(bad)}: {e}")


class TestModelAndPreprocessingBrutal(unittest.TestCase):
    def setUp(self):
        import model
        self.model = model

    def test_tokenizer_normal_and_extreme(self):
        t = self.model.tokenize_sentence("吾輩は猫である。名前はまだ無い。")
        self.assertIsInstance(t, list)
        self.assertGreater(len(t), 3)
        self.assertEqual(t[0]["surface"], "吾輩")

        # Mixed inputs
        t_mixed = self.model.tokenize_sentence("English 12345 漢字 カタカナ ひらがな 🎮 !@#$%^")
        self.assertIsInstance(t_mixed, list)
        self.assertGreater(len(t_mixed), 0)

        # Empty and whitespace
        self.assertEqual(self.model.tokenize_sentence(""), [])
        self.assertEqual(self.model.tokenize_sentence("   \n\t  "), [])

        # Very long text
        t_long = self.model.tokenize_sentence("猫" * 500)
        self.assertIsInstance(t_long, list)
        self.assertEqual(len(t_long), 500)

    def test_preprocess_image_modes_and_dimensions(self):
        # Standard RGB
        img_rgb = Image.new("RGB", (200, 80), (255, 255, 255))
        res_rgb = self.model.preprocess_image(img_rgb)
        self.assertIsInstance(res_rgb, Image.Image)

        # 1-bit bilevel mode ('1')
        img_1 = Image.new("1", (50, 50), 1)
        res_1 = self.model.preprocess_image(img_1)
        self.assertIsInstance(res_1, Image.Image)

        # Palette mode ('P')
        img_p = Image.new("P", (50, 50))
        res_p = self.model.preprocess_image(img_p)
        self.assertIsInstance(res_p, Image.Image)

        # RGBA mode ('RGBA')
        img_rgba = Image.new("RGBA", (80, 40), (200, 100, 50, 200))
        res_rgba = self.model.preprocess_image(img_rgba)
        self.assertIsInstance(res_rgba, Image.Image)

        # Grayscale ('L')
        img_l = Image.new("L", (100, 100), 128)
        res_l = self.model.preprocess_image(img_l)
        self.assertIsInstance(res_l, Image.Image)

        # Microscopic 1x1 image (must not crash CLAHE or bilateralFilter)
        img_tiny = Image.new("RGB", (1, 1), (0, 0, 0))
        res_tiny = self.model.preprocess_image(img_tiny)
        self.assertIsInstance(res_tiny, Image.Image)
        self.assertGreaterEqual(res_tiny.size[0], 16)
        self.assertGreaterEqual(res_tiny.size[1], 16)

        # Extreme aspect ratios
        img_tall = Image.new("RGB", (2, 500), (255, 255, 255))
        res_tall = self.model.preprocess_image(img_tall)
        self.assertIsInstance(res_tall, Image.Image)

        img_wide = Image.new("RGB", (500, 2), (255, 255, 255))
        res_wide = self.model.preprocess_image(img_wide)
        self.assertIsInstance(res_wide, Image.Image)

    def test_preprocess_color_isolation(self):
        img = Image.new("RGB", (100, 100), (0, 255, 0))
        lower = np.array([35, 50, 50])
        upper = np.array([85, 255, 255])
        res = self.model.preprocess_image(img, extract_color_range=(lower, upper))
        self.assertIsInstance(res, Image.Image)


class TestTranslationAndAIFixBrutal(unittest.TestCase):
    def setUp(self):
        import translation
        import ai_fix
        self.translation = translation
        self.ai_fix = ai_fix

    def test_translation_empty_and_caching(self):
        self.assertEqual(self.translation.translate_text(""), "")
        self.assertEqual(self.translation.translate_text("   "), "")

        # Test cache hit
        self.translation.TRANSLATION_CACHE["google__テスト"] = "Test"
        cached = self.translation.translate_text("テスト", engine="google")
        self.assertEqual(cached, "Test")

    def test_nvidia_url_sanitization(self):
        # Even with an invalid or dummy key, verify that build.nvidia.com URL is properly stripped
        res = self.translation.translate_text(
            "猫",
            engine="nvidia",
            api_key="nvapi-dummy-key",
            text_model="https://build.nvidia.com/nvidia/riva-translate-4b-instruct-v2"
        )
        self.assertIsInstance(res, str)
        # Should not crash, and error message should reference the clean model name, not the raw URL
        self.assertNotIn("https://build.nvidia.com/", res)

    def test_missing_api_keys_handling(self):
        # DeepL missing key
        res_deepl = self.translation.translate_text("猫", engine="deepl", api_key="")
        self.assertIn("Error:", res_deepl)

        # NVIDIA missing key
        res_nvidia = self.translation.translate_text("猫", engine="nvidia", api_key="")
        self.assertIn("Error:", res_nvidia)

        # Unknown engine
        res_unknown = self.translation.translate_text("猫", engine="unknown_super_translator")
        self.assertIn("Unknown translation engine", res_unknown)

    def test_ai_fix_missing_file_and_keys(self):
        # Non-existent image file
        res_no_file = self.ai_fix.fix_japanese_ocr("non_existent_path.png", "猫", engine="google")
        self.assertIn("Error:", res_no_file)

        # Missing Gemini API key
        dummy_file = "temp_test_snip.png"
        Image.new("RGB", (10, 10)).save(dummy_file)
        try:
            res_no_key = self.ai_fix.fix_japanese_ocr(dummy_file, "猫", engine="google", api_key="")
            self.assertIn("Error:", res_no_key)

            res_nvidia_no_key = self.ai_fix.fix_japanese_ocr(dummy_file, "猫", engine="nvidia", api_key="")
            self.assertIn("Error:", res_nvidia_no_key)
        finally:
            if os.path.exists(dummy_file):
                os.remove(dummy_file)


class TestAnkiExportBrutal(unittest.TestCase):
    def setUp(self):
        import anki_export
        self.anki = anki_export

    def test_generate_html_ruby(self):
        ruby = self.anki.generate_html_ruby
        # Okurigana trailing separation: 染まる -> <ruby>染<rt>そ</rt></ruby>まる
        res_somaru = ruby("染まる")
        self.assertIn("<ruby>", res_somaru)
        self.assertTrue(res_somaru.endswith("まる"))

        # Pure kana
        self.assertEqual(ruby("ここ"), "ここ")
        self.assertEqual(ruby("テスト"), "テスト")

        # Empty string
        self.assertEqual(ruby(""), "")

    def test_clean_term(self):
        clean = self.anki.clean_term
        self.assertEqual(clean("<ruby>見<rt>み</rt></ruby>える"), "見える")
        self.assertEqual(clean("見[み]え"), "見え")
        self.assertEqual(clean("&nbsp;食べる&nbsp;"), "食べる")
        self.assertEqual(clean(""), "")
        self.assertEqual(clean(None), "")

    def test_auto_highlight(self):
        hl = self.anki.auto_highlight("猫が好きです。", "猫")
        self.assertIn('class="highlight"', hl)
        self.assertIn("猫", hl)

        # Empty inputs
        self.assertEqual(self.anki.auto_highlight("", "猫"), "")
        self.assertEqual(self.anki.auto_highlight("猫が好きです。", ""), "猫が好きです。")

    def test_anki_offline_graceful_handling(self):
        # With Anki closed/unreachable, invoke should return an error dict, not raise an unhandled exception
        orig_url = self.anki.ANKI_URL
        try:
            self.anki.ANKI_URL = "http://127.0.0.1:59999"
            res = self.anki.invoke("version")
            self.assertIsInstance(res, dict)
            self.assertIn("error", res)

            alive = self.anki.is_anki_alive()
            self.assertFalse(alive)

            decks = self.anki.get_deck_names()
            self.assertIsInstance(decks, list)

            exists = self.anki.check_card_exists("Default", "猫")
            self.assertFalse(exists)
        finally:
            self.anki.ANKI_URL = orig_url


class TestUIAndWidgetsBrutal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_pitch_graph_widget(self):
        from ui import PitchGraphWidget, USER_SETTINGS
        USER_SETTINGS["show_pitch"] = True

        # Test Heiban (0)
        pg = PitchGraphWidget("ねこ", pitch_drop=0)
        self.assertEqual(pg.pitch_drop, 0)
        self.assertGreater(pg.width(), 0)

        # Test Atamadaka (1)
        pg.update_pitch("ほん", 1)
        self.assertEqual(pg.pitch_drop, 1)

        # Test drop = -1 (hidden)
        pg.update_pitch("ことば", -1)
        self.assertEqual(pg.width(), 0)

        # Small kana counting: きょう (kyo-u = 2 morae)
        pg.update_pitch("きょう", 0)
        self.assertGreater(pg.width(), 0)

        # Empty string
        pg.update_pitch("", 0)
        self.assertGreaterEqual(pg.width(), 0)

        # Pitch disabled in settings
        USER_SETTINGS["show_pitch"] = False
        pg.update_pitch("ねこ", 0)
        self.assertEqual(pg.width(), 0)
        USER_SETTINGS["show_pitch"] = True

    def test_result_overlay_instantiation_and_display(self):
        from ui import ResultOverlay
        overlay = ResultOverlay()
        
        # Display valid token list
        tokens = [
            {"surface": "吾輩", "base_form": "吾輩", "pos": "名詞"},
            {"surface": "は", "base_form": "は", "pos": "助詞"},
            {"surface": "猫", "base_form": "猫", "pos": "名詞"}
        ]
        overlay.display_words(tokens, 100, 100)
        self.assertEqual(overlay.lbl_sentence.text(), "吾輩は猫")

        # Rebuild sentence after word edit
        overlay.rebuild_sentence()
        self.assertEqual(overlay.lbl_sentence.text(), "吾輩は猫")

        # Display empty tokens: must guard safely without clearing or crashing
        overlay.display_words([], 100, 100)
        overlay.display_words(None, 100, 100)
        self.assertEqual(overlay.lbl_sentence.text(), "吾輩は猫")

        overlay.hide()

    def test_snipping_widget_cancellation(self):
        from ui import SnippingWidget
        from PyQt6.QtCore import Qt, QPoint
        from PyQt6.QtGui import QKeyEvent, QMouseEvent

        snip = SnippingWidget()
        snip.state = "DRAGGING"

        # Test Escape cancels
        key_event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        snip.keyPressEvent(key_event)
        self.assertEqual(snip.state, "HIDDEN")

        # Test Right-click cancels
        from PyQt6.QtCore import QPointF
        snip.state = "IDLE"
        mouse_event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(50.0, 50.0),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier
        )
        snip.mousePressEvent(mouse_event)
        self.assertEqual(snip.state, "HIDDEN")

    def test_hotkey_matching_logic(self):
        import main
        from pynput import keyboard

        # Alt
        self.assertTrue(main.matches_hotkey("Alt", keyboard.Key.alt))
        self.assertTrue(main.matches_hotkey("Alt", keyboard.Key.alt_l))
        self.assertTrue(main.matches_hotkey("Alt", keyboard.Key.alt_r))

        # Space
        self.assertTrue(main.matches_hotkey("Space", keyboard.Key.space))

        # Single char
        class MockCharKey:
            char = 'a'
        self.assertTrue(main.matches_hotkey("A", MockCharKey()))

        # Non-matching
        self.assertFalse(main.matches_hotkey("Ctrl", keyboard.Key.alt))

    def test_minimize_to_tray_close_event_behavior(self):
        import main
        from PyQt6.QtGui import QCloseEvent
        from ui import USER_SETTINGS
        
        # Test 1: When minimize_to_tray is True, closeEvent ignores and hides
        USER_SETTINGS["minimize_to_tray"] = True
        panel = main.ControlPanel(None)
        close_ev = QCloseEvent()
        panel.closeEvent(close_ev)
        self.assertFalse(close_ev.isAccepted())
        panel.startup_worker.wait()
        
        # Test 2: When minimize_to_tray is False, closeEvent accepts and triggers quit
        USER_SETTINGS["minimize_to_tray"] = False
        panel2 = main.ControlPanel(None)
        quit_called = []
        panel2.quit_application = lambda: quit_called.append(True)
        close_ev2 = QCloseEvent()
        panel2.closeEvent(close_ev2)
        self.assertTrue(close_ev2.isAccepted())
        self.assertTrue(len(quit_called) > 0)
        panel2.startup_worker.wait()
        
        USER_SETTINGS["minimize_to_tray"] = False

    def test_history_tab_features(self):
        import main
        from ui import signals
        panel = main.ControlPanel(None)
        
        # Initial empty state
        self.assertEqual(panel.history_stack.currentIndex(), 0)
        self.assertEqual(panel.lbl_history_count.text(), "0 items")
        
        # Add sentences
        panel.add_to_history("吾輩は猫である。")
        panel.add_to_history("名前はまだ無い。")
        self.assertEqual(panel.history_stack.currentIndex(), 1)
        self.assertEqual(panel.history_list.count(), 2)
        self.assertEqual(panel.lbl_history_count.text(), "2 items")
        
        # Search / filter
        panel.filter_history("猫")
        self.assertEqual(panel.lbl_history_count.text(), "1/2 items")
        panel.filter_history("存在しない")
        self.assertEqual(panel.lbl_history_count.text(), "0/2 items")
        panel.filter_history("")
        self.assertEqual(panel.lbl_history_count.text(), "2 items")
        
        # Copy All
        panel.copy_all_history()
        
        # Double-click inspect signal emission
        emitted_signals = []
        signals.show_results.connect(lambda tokens, x, y: emitted_signals.append((tokens, x, y)))
        panel.inspect_history_item(panel.history_list.item(0))
        self.assertEqual(len(emitted_signals), 1)
        self.assertGreater(len(emitted_signals[0][0]), 0) # Token list not empty
        
        # Clear
        panel.clear_history()
        self.assertEqual(panel.history_list.count(), 0)
        self.assertEqual(panel.history_stack.currentIndex(), 0)
        self.assertEqual(panel.lbl_history_count.text(), "0 items")
        panel.startup_worker.wait()

    def test_dictionary_tab_upgrades(self):
        import main
        import dictionary
        panel = main.ControlPanel(None)
        
        # Stats banner
        stats = dictionary.get_dictionary_stats()
        self.assertIn("total_terms", stats)
        self.assertIn("active_dicts", stats)
        self.assertIn("Definitions Indexed", panel.lbl_dict_stats.text())
        
        # Dictionary filter
        panel.filter_dictionaries("non_existent_dict_xyz")
        panel.filter_dictionaries("")
        panel.startup_worker.wait()


class TestConcurrentAndFuzzBrutal(unittest.TestCase):
    def test_concurrent_database_lookups(self):
        from concurrent.futures import ThreadPoolExecutor
        import dictionary
        dictionary.ENABLED_DICTIONARIES.clear()

        test_terms = ["猫", "日", "食べる", "行く", "本", "走る", "漢字", "犬", "山", "川"] * 5
        
        def lookup_term(term):
            res = dictionary.get_real_data(term)
            dictionary.close_thread_connection()
            return res

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(lookup_term, test_terms))

        self.assertEqual(len(results), len(test_terms))
        for r in results:
            self.assertIsInstance(r, dict)
            self.assertIn("meanings_list", r)

    def test_fuzz_deinflection(self):
        import random
        import deinflect

        hiragana = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんっゃゅょ"
        katakana = "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンッャュョ"
        kanji = "日一国会人年大十二本中長出三同時政事自行社見月分話"

        all_chars = hiragana + katakana + kanji

        for _ in range(50):
            length = random.randint(1, 20)
            fuzz_str = "".join(random.choice(all_chars) for _ in range(length))
            t0 = time.perf_counter()
            res = deinflect.get_base_forms(fuzz_str)
            dt = time.perf_counter() - t0
            self.assertIsInstance(res, list)
            self.assertLess(dt, 0.05, f"Deinflection took too long ({dt:.3f}s) for {fuzz_str}")

    def test_complex_unicode_tokenization(self):
        import model
        crazy_text = (
            "ﾊﾝｶｸｶﾀｶﾅ "
            "ＦｕｌｌＷｉｄｔｈ "
            "Emoji: 🐱🦊🎌🍱 "
            "ZeroWidth:\u200b\u200c\u200d "
            "Mixed: 猫のｹｰｷを🍰食べる！"
        )
        tokens = model.tokenize_sentence(crazy_text)
        self.assertIsInstance(tokens, list)
        self.assertGreater(len(tokens), 0)

    def test_settings_integrity_and_fallbacks(self):
        import ui
        # Check all default keys exist
        for key, val in ui.DEFAULT_SETTINGS.items():
            self.assertIn(key, ui.USER_SETTINGS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
