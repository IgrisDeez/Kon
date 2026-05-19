from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton, QScrollArea
except ModuleNotFoundError:
    raise unittest.SkipTest("PySide6 is not installed")

from aelrith_forge import APP_DISPLAY_NAME, APP_PUBLIC_VERSION
from aelrith_forge.backend.controller import BotController
from aelrith_forge.ui import main_window as main_window_module
from aelrith_forge.ui.main_window import MainWindow
from aelrith_forge.ui.pages.logs_page import LogsPage
from aelrith_forge.ui.pages.powers_page import PowersPage
from aelrith_forge.ui.pages.settings_page import SettingsPage
from aelrith_forge.ui.pages.tools_page import ToolsPage
from aelrith_forge.ui.widgets.numeric import FocusWheelDoubleSpinBox, FocusWheelSpinBox
from aelrith_forge.ui.widgets.stat_row import SmoothSlider


class FakeWheelEvent:
    def __init__(self):
        self.ignored = False

    def ignore(self):
        self.ignored = True


class UiWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_unfocused_numeric_controls_ignore_wheel_events(self):
        for widget in (FocusWheelSpinBox(), FocusWheelDoubleSpinBox(), SmoothSlider()):
            event = FakeWheelEvent()
            widget.clearFocus()
            widget.wheelEvent(event)
            self.assertTrue(event.ignored)

    def test_powers_page_default_setup_and_round_trip(self):
        page = PowersPage()
        self.addCleanup(page.deleteLater)

        self.assertEqual(page.preview_button.text(), "Preview OCR")
        self.assertEqual(page.apply_button.text(), "Confirm and Apply")
        self.assertTrue(page._advanced_region_panel.isHidden())

        page.preview_region_edit.setText("10,20,30,40")
        page.current_power_region_edit.setText("11,21,31,41")
        page.auto_check_region_edit.setText("12,22,32,42")
        page.confirm_check_region_edit.setText("13,23,33,43")
        page.popup_region_edit.setText("14,24,34,44")
        page.change_exclusion_region_edit.setText("15,25,35,45")
        page.auto_point_edit.setText("101,201")
        page.roll_point_edit.setText("102,202")
        page.yes_point_edit.setText("103,203")
        page.power_chips["cursebrand"].setChecked(False)

        collected = page.collect_power_settings()
        self.assertEqual(collected["powers_layout"]["preview_region"], "10,20,30,40")
        self.assertEqual(collected["powers_layout"]["current_power_region"], "11,21,31,41")
        self.assertEqual(collected["powers_layout"]["coords"]["auto"], "101,201")
        self.assertEqual(collected["powers_layout"]["popup_region"], "14,24,34,44")
        self.assertFalse(collected["enabled_powers"]["cursebrand"])

        second = PowersPage()
        self.addCleanup(second.deleteLater)
        second.load_settings(collected)
        self.assertEqual(second.preview_region_edit.text(), "10,20,30,40")
        self.assertEqual(second.current_power_region_edit.text(), "11,21,31,41")
        self.assertEqual(second.auto_check_region_edit.text(), "12,22,32,42")
        self.assertEqual(second.confirm_check_region_edit.text(), "13,23,33,43")
        self.assertEqual(second.popup_region_edit.text(), "14,24,34,44")
        self.assertEqual(second.change_exclusion_region_edit.text(), "15,25,35,45")
        self.assertEqual(second.auto_point_edit.text(), "101,201")
        self.assertEqual(second.roll_point_edit.text(), "102,202")
        self.assertEqual(second.yes_point_edit.text(), "103,203")
        self.assertFalse(second.power_chips["cursebrand"].isChecked())
        self.assertTrue(second._advanced_region_panel.isHidden())
        second._set_advanced_regions_visible(True)
        self.assertFalse(second._advanced_region_panel.isHidden())

    def test_main_window_offscreen_construction_still_loads_all_pages(self):
        controller = BotController()
        window = MainWindow(controller)
        self.addCleanup(window.close)

        pages = [type(window.stack.widget(i)).__name__ for i in range(window.stack.count())]
        self.assertEqual(
            pages,
            ["MainPage", "TargetsPage", "PowersPage", "SettingsPage", "LogsPage", "ToolsPage"],
        )
        self.assertEqual(window.passive_shards_value.text(), "-")
        self.assertEqual(window.power_shards_value.text(), "-")
        self.assertEqual(window.windowTitle(), APP_DISPLAY_NAME)
        self.assertTrue(any(label.text() == APP_PUBLIC_VERSION for label in window.findChildren(QLabel)))
        self.assertTrue(hasattr(window.settings_page, "power_shard_region_edit"))
        window.settings_page.power_shard_region_edit.setText("10,20,30,40")
        window.settings_page.power_alerts_check.setChecked(True)
        window.settings_page.power_interval_spin.setValue(7)
        collected = window.settings_page.collect_settings()
        self.assertEqual(collected["power_shard_region"], "10,20,30,40")
        self.assertTrue(collected["power_shard_alerts"])
        self.assertEqual(collected["power_shard_report_interval"], 420)
        self.assertTrue(hasattr(window, "preview_capture_notice"))
        self.assertEqual(window.preview_capture_notice.text(), "Preview restored")
        self.assertTrue(hasattr(window.main_page, "macro_health_value"))
        self.assertTrue(hasattr(window.tools_page, "macro_timing_readout"))

    def test_main_window_skips_auto_update_check_in_source_runtime(self):
        old_check = main_window_module.updater.is_portable_runtime
        main_window_module.updater.is_portable_runtime = lambda: False
        try:
            controller = BotController()
            window = MainWindow(controller)
            self.addCleanup(window.close)

            window.check_for_updates_on_startup()

            self.assertFalse(window._update_check_started)
        finally:
            main_window_module.updater.is_portable_runtime = old_check

    def test_main_page_mode_badges_track_display_and_running_state(self):
        controller = BotController()
        window = MainWindow(controller)
        self.addCleanup(window.close)

        page = window.main_page
        page.set_display_mode("powers")
        self.assertTrue(page.powers_mode_badge.property("modeActive"))
        self.assertFalse(page.specs_mode_badge.property("modeActive"))

        page.set_active_mode("specs")
        page.set_running(True)
        self.assertEqual(page.mode_badge.text(), "Specs")
        self.assertEqual(page.mode_badge.property("modeTone"), "specs")
        self.assertTrue(page.specs_mode_badge.property("modeActive"))
        self.assertFalse(page.powers_mode_badge.property("modeActive"))
        self.assertEqual(page.start_specs_button.text(), "Running...")
        self.assertFalse(page.start_specs_button.isEnabled())
        self.assertTrue(page.stop_button.isEnabled())

    def test_settings_page_power_shard_settings_round_trip(self):
        page = SettingsPage()
        self.addCleanup(page.deleteLater)

        page.power_shard_region_edit.setText("10,20,30,40")
        page.power_alerts_check.setChecked(True)
        page.power_interval_spin.setValue(7)
        page.power_low_threshold_spin.setValue(12000)
        page.power_very_low_threshold_spin.setValue(7000)
        page.power_critical_threshold_spin.setValue(1500)
        page.power_empty_threshold_spin.setValue(5)
        page.power_alert_cooldown_spin.setValue(45)
        page.stop_on_empty_power_shards_check.setChecked(True)

        collected = page.collect_settings()
        self.assertEqual(collected["power_shard_region"], "10,20,30,40")
        self.assertTrue(collected["power_shard_alerts"])
        self.assertEqual(collected["power_shard_report_interval"], 420)
        self.assertEqual(collected["power_shard_low_threshold"], 12000)
        self.assertEqual(collected["power_shard_very_low_threshold"], 7000)
        self.assertEqual(collected["power_shard_critical_threshold"], 1500)
        self.assertEqual(collected["power_shard_empty_threshold"], 5)
        self.assertEqual(collected["power_shard_alert_cooldown"], 2700)
        self.assertTrue(collected["stop_on_empty_power_shards"])

        second = SettingsPage()
        self.addCleanup(second.deleteLater)
        second.load_settings(collected)
        self.assertEqual(second.power_shard_region_edit.text(), "10,20,30,40")
        self.assertTrue(second.power_alerts_check.isChecked())
        self.assertEqual(second.power_interval_spin.value(), 7)
        self.assertEqual(second.power_low_threshold_spin.value(), 12000)
        self.assertEqual(second.power_very_low_threshold_spin.value(), 7000)
        self.assertEqual(second.power_critical_threshold_spin.value(), 1500)
        self.assertEqual(second.power_empty_threshold_spin.value(), 5)
        self.assertEqual(second.power_alert_cooldown_spin.value(), 45)
        self.assertTrue(second.stop_on_empty_power_shards_check.isChecked())

    def test_logs_page_power_preview_uses_power_roll_wording(self):
        page = LogsPage()
        self.addCleanup(page.deleteLater)

        page.update_preview("", "Cursebrand", "Damage 30 | Crit Chance 4", domain="powers", passive="NPC increased damage 15")

        preview = page.preview.toPlainText()
        self.assertIn("Power Roll Found", preview)
        self.assertIn("Power: Cursebrand", preview)
        self.assertIn("Passive: NPC increased damage 15", preview)

    def test_tools_page_keeps_live_proof_export_enabled_while_running(self):
        page = ToolsPage()
        self.addCleanup(page.deleteLater)

        self.assertIsInstance(page.scroll, QScrollArea)
        self.assertEqual(page.export_live_proof_button.text(), "Export Live Proof Pack")
        page.set_running(True)

        self.assertTrue(page.export_live_proof_button.isEnabled())
        self.assertFalse(page.capture_debug_button.isEnabled())
        self.assertFalse(page.preview_shards_button.isEnabled())

        page.set_running(False)
        self.assertTrue(page.capture_debug_button.isEnabled())
        self.assertTrue(page.preview_shards_button.isEnabled())

    def test_tools_page_groups_actions_without_changing_signals(self):
        page = ToolsPage()
        self.addCleanup(page.deleteLater)

        labels = [label.text() for label in page.findChildren(QLabel)]
        for title in ("Capture", "Preview OCR", "Validation", "Webhook", "Timing / Recovery"):
            self.assertIn(title, labels)
        self.assertTrue(page.findChildren(QFrame))

        events = []
        page.captureDebugRequested.connect(lambda: events.append("capture_debug"))
        page.captureScreenshotRequested.connect(lambda: events.append("capture_screenshot"))
        page.exportLiveProofRequested.connect(lambda: events.append("export_proof"))
        page.previewShardRequested.connect(lambda: events.append("passive_shards"))
        page.previewPowerShardRequested.connect(lambda: events.append("power_shards"))
        page.previewRequested.connect(lambda domain: events.append(f"preview:{domain}"))
        page.testPopupRequested.connect(lambda domain: events.append(f"popup:{domain}"))
        page.testClassificationRequested.connect(lambda domain: events.append(f"classify:{domain}"))
        page.testWebhookRequested.connect(lambda: events.append("webhook"))

        page.capture_debug_button.click()
        page.capture_screenshot_button.click()
        page.export_live_proof_button.click()
        page.preview_shards_button.click()
        page.preview_power_shards_button.click()
        page.preview_ocr_specs_button.click()
        page.preview_ocr_powers_button.click()
        page.test_popup_specs_button.click()
        page.test_popup_powers_button.click()
        page.test_classification_specs_button.click()
        page.test_classification_powers_button.click()
        page.test_webhook_button.click()

        self.assertEqual(
            events,
            [
                "capture_debug",
                "capture_screenshot",
                "export_proof",
                "passive_shards",
                "power_shards",
                "preview:specs",
                "preview:powers",
                "popup:specs",
                "popup:powers",
                "classify:specs",
                "classify:powers",
                "webhook",
            ],
        )

    def test_tools_page_action_groups_keep_labels_above_buttons(self):
        page = ToolsPage()
        self.addCleanup(page.deleteLater)
        page.resize(760, 420)
        page.show()
        self.app.processEvents()

        action_groups = [
            group for group in page.findChildren(QFrame)
            if group.property("actionGroup") is True
        ]
        self.assertGreaterEqual(len(action_groups), 7)
        for group in action_groups:
            title_labels = [
                child for child in group.findChildren(QLabel)
                if child.objectName().startswith("toolActionGroup_")
            ]
            buttons = group.findChildren(QPushButton)
            if not title_labels or not buttons:
                continue
            label_bottom = title_labels[0].mapTo(group, title_labels[0].rect().bottomLeft()).y()
            first_button_top = min(
                button.mapTo(group, button.rect().topLeft()).y()
                for button in buttons
            )
            self.assertLess(label_bottom + 4, first_button_top)

    def test_macro_health_readouts_update_without_changing_controls(self):
        controller = BotController()
        window = MainWindow(controller)
        self.addCleanup(window.close)
        controller.bot.last_startup_route_snapshot = {"route_reason": "spec_safe_filler_weak_rolling_signal_no_blind_click"}
        controller.bot.last_recovery_route_snapshot = {"route_reason": "manual_reroll_recovered"}
        controller.bot.last_auto_checkbox_classifier_summary = {
            "state": "unknown",
            "effective_state": "ambiguous",
            "confidence": "weak",
        }
        controller.bot.auto_checkbox_read_count = 4
        controller.bot.auto_checkbox_ambiguous_read_count = 3
        controller.bot.last_verification_cache_stats = {"cache_hits": 1, "cache_misses": 1, "polls_seen": 1, "polls_planned": 2}
        controller.bot.recent_route_budget_events = [
            {"name": "startup_verify_budget", "elapsed_ms": 42, "result": "confirmed"}
        ]

        window._refresh_macro_health()

        self.assertIn("spec_safe_filler_weak_rolling_signal_no_blind_click", window.main_page.macro_health_value.text())
        self.assertIn("ambiguous", window.main_page.auto_checkbox_health_value.text())
        self.assertIn("startup_verify_budget", window.main_page.verify_timing_value.text())
        self.assertIn("cache 1/1", window.tools_page.macro_timing_readout.text())
        self.assertIn("3 / 4", window.tools_page.checkbox_ambiguity_readout.text())


if __name__ == "__main__":
    unittest.main()
