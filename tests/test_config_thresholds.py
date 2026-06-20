"""Stdlib-only tests for config_manager's OCR-threshold / debug helpers.

Each test points config_manager's CONFIG_PATH/CONFIGS_DIR at a throwaway temp
dir, so the real configs/config.json is never touched. No Tk, OCR, or Node.

Run directly:

    python tests/test_config_thresholds.py
"""

import json
import os
import sys
import tempfile
import unittest

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE_DIR)

import config_manager


class ConfigThresholdTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = (config_manager.CONFIGS_DIR, config_manager.CONFIG_PATH)
        config_manager.CONFIGS_DIR = self._tmp.name
        config_manager.CONFIG_PATH = os.path.join(self._tmp.name, "config.json")

    def tearDown(self):
        config_manager.CONFIGS_DIR, config_manager.CONFIG_PATH = self._saved
        self._tmp.cleanup()

    def _write_config(self, data):
        with open(config_manager.CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _read_config(self):
        with open(config_manager.CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # --- thresholds ---

    def test_defaults_when_absent(self):
        self.assertEqual(
            config_manager.load_ocr_thresholds(), config_manager.DEFAULT_OCR_THRESHOLDS
        )

    def test_round_trip(self):
        custom = {"pass1_cutoff": 0.6, "pass1_anchor": 0.5, "pass2_whole": 0.9, "pass2_token": 0.7}
        config_manager.save_ocr_thresholds(custom)
        self.assertEqual(config_manager.load_ocr_thresholds(), custom)

    def test_clamping_out_of_range(self):
        config_manager.save_ocr_thresholds(
            {"pass1_cutoff": 1.5, "pass1_anchor": -0.2, "pass2_whole": 2.0, "pass2_token": 0.5}
        )
        loaded = config_manager.load_ocr_thresholds()
        self.assertEqual(loaded["pass1_cutoff"], 1.0)
        self.assertEqual(loaded["pass1_anchor"], 0.0)
        self.assertEqual(loaded["pass2_whole"], 1.0)
        self.assertEqual(loaded["pass2_token"], 0.5)

    def test_merges_missing_keys_from_default(self):
        self._write_config({"ocr_thresholds": {"pass1_cutoff": 0.42}})
        loaded = config_manager.load_ocr_thresholds()
        self.assertEqual(loaded["pass1_cutoff"], 0.42)
        self.assertEqual(loaded["pass1_anchor"], config_manager.DEFAULT_OCR_THRESHOLDS["pass1_anchor"])
        self.assertEqual(loaded["pass2_whole"], config_manager.DEFAULT_OCR_THRESHOLDS["pass2_whole"])
        self.assertEqual(loaded["pass2_token"], config_manager.DEFAULT_OCR_THRESHOLDS["pass2_token"])

    def test_save_preserves_other_keys(self):
        self._write_config({"ocr_hotkey": "<F7>", "show_thumbnails": False})
        config_manager.save_ocr_thresholds(config_manager.DEFAULT_OCR_THRESHOLDS)
        data = self._read_config()
        self.assertEqual(data["ocr_hotkey"], "<F7>")
        self.assertEqual(data["show_thumbnails"], False)
        self.assertIn("ocr_thresholds", data)

    # --- debug hotkey ---

    def test_debug_hotkey_default_and_round_trip(self):
        self.assertEqual(config_manager.load_debug_hotkey(), "<F9>")
        config_manager.save_debug_hotkey("<ctrl>+<F9>")
        self.assertEqual(config_manager.load_debug_hotkey(), "<ctrl>+<F9>")

    # --- auto capture ---

    def test_debug_auto_capture_default_and_round_trip(self):
        self.assertFalse(config_manager.load_debug_auto_capture())
        config_manager.save_debug_auto_capture(True)
        self.assertTrue(config_manager.load_debug_auto_capture())
        config_manager.save_debug_auto_capture(False)
        self.assertFalse(config_manager.load_debug_auto_capture())


if __name__ == "__main__":
    unittest.main()
