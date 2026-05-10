from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from aelrith_forge.backend.controller import BotController
from aelrith_forge.ui.main_window import MainWindow


class MainWindowApplySummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.controller = BotController()
        self.window = MainWindow(self.controller)
        self.settings_calls: list[dict] = []
        self.log_calls: list[str] = []

        self._apply_patch = patch.object(
            self.controller,
            "apply_settings",
            side_effect=lambda settings: self.settings_calls.append(settings),
        )
        self._log_patch = patch.object(
            self.controller,
            "add_log",
            side_effect=lambda text: self.log_calls.append(text),
        )
        self._apply_patch.start()
        self._log_patch.start()
        self.addCleanup(self._apply_patch.stop)
        self.addCleanup(self._log_patch.stop)
        self.addCleanup(self.window.close)

    def _load_roll_domain(self, roll_domain: str):
        settings = self.controller.normalize_settings(dict(self.controller.settings))
        settings["roll_domain"] = roll_domain
        self.controller.settings = settings
        self.window._load_settings(settings)

    def _trigger_apply(
        self,
        page,
        forced_roll_domain: str,
        expected_mode: str,
        expected_tokens: tuple[str, ...],
        unexpected_tokens: tuple[str, ...],
        log_expected_tokens: tuple[str, ...],
    ):
        self._load_roll_domain(forced_roll_domain)
        self.window.stack.setCurrentWidget(page)
        with patch.object(self.window, "_confirm_apply", return_value=True) as confirm_apply:
            with patch.object(self.window, "sender", return_value=None):
                self.window.apply_settings()

        self.assertTrue(self.settings_calls)
        self.assertTrue(self.log_calls)
        self.assertTrue(confirm_apply.called)
        confirm_settings, confirm_mode = confirm_apply.call_args.args
        self.assertEqual(confirm_mode, expected_mode)
        confirm_text = "\n".join(self.window._target_summary_lines(confirm_settings, confirm_mode))
        for token in expected_tokens:
            self.assertIn(token, confirm_text)
        for token in unexpected_tokens:
            self.assertNotIn(token, confirm_text)
        self.assertIn("Desired targets applied |", self.log_calls[-1])
        for token in log_expected_tokens:
            self.assertIn(token, self.log_calls[-1])
        for token in unexpected_tokens:
            self.assertNotIn(token, self.log_calls[-1])

    def test_specs_apply_uses_specs_summary(self):
        self._trigger_apply(
            self.window.target_page,
            "powers",
            "specs",
            ("Fortune Chosen", "Executioner", "Rampage", "CURRENT SPEC required"),
            ("Cursebrand", "Colossus", "Subjugator"),
            ("Fortune Chosen", "Executioner"),
        )

    def test_powers_apply_uses_powers_summary(self):
        self._trigger_apply(
            self.window.powers_page,
            "specs",
            "powers",
            ("Cursebrand", "Colossus", "Subjugator", "NPC increased damage", "Boss damage bonus", "NPC movement slow"),
            ("Fortune Chosen", "Executioner", "Rampage", "CURRENT SPEC required"),
            ("Cursebrand", "Colossus"),
        )


if __name__ == "__main__":
    unittest.main()
