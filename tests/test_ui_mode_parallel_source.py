from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UiModeParallelSourceTests(unittest.TestCase):
    def test_sidebar_renames_targets_to_specs(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'main_window.py').read_text()
        self.assertIn('["Main", "Specs", "Powers", "Settings", "Debug", "Tools"]', source)

    def test_main_page_has_dual_mode_start_actions(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'pages' / 'main_page.py').read_text()
        self.assertIn('startSpecsRequested = Signal()', source)
        self.assertIn('startPowersRequested = Signal()', source)
        self.assertIn('QPushButton("Start Specs")', source)
        self.assertIn('QPushButton("Start Powers")', source)
        self.assertIn('Active Mode', source)

    def test_specs_and_powers_tabs_share_parallel_section_order(self):
        targets_source = (ROOT / 'aelrith_forge' / 'ui' / 'pages' / 'targets_page.py').read_text()
        powers_source = (ROOT / 'aelrith_forge' / 'ui' / 'pages' / 'powers_page.py').read_text()
        for source in (targets_source, powers_source):
            self.assertIn('layout.addWidget(self._build_profile_card())', source)
            self.assertIn('layout.addWidget(self._build_active_summary_card())', source)
            self.assertIn('layout.addWidget(self._build_targets_panel())', source)
        self.assertIn('layout.addWidget(self._build_runtime_layout_card())', targets_source)
        self.assertIn('layout.addWidget(self._build_layout_card())', powers_source)
        self.assertIn('Card("Spec Profile")', targets_source)
        self.assertIn('Card("Power Profile")', powers_source)
        self.assertIn('Card("Runtime Layout")', targets_source)
        self.assertIn('Card("Runtime Layout")', powers_source)

    def test_tools_page_splits_specs_and_powers_subsystem_sections(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'pages' / 'tools_page.py').read_text()
        self.assertIn('Card("Shared / General Tools")', source)
        self.assertIn('Card("Specs Subsystem Tests")', source)
        self.assertIn('Card("Powers Subsystem Tests")', source)
        self.assertIn('self.previewRequested.emit("specs")', source)
        self.assertIn('self.previewRequested.emit("powers")', source)
        self.assertIn('self.testPopupRequested.emit("specs")', source)
        self.assertIn('self.testPopupRequested.emit("powers")', source)
        self.assertIn('previewPowerShardRequested = Signal()', source)
        self.assertIn('exportLiveProofRequested = Signal()', source)
        self.assertIn('self._button("Export Live Proof Pack")', source)
        self.assertIn('self._button("Test Passive Shard OCR")', source)
        self.assertIn('self._button("Test Power Shard OCR")', source)
        self.assertIn('self.scroll = QScrollArea()', source)
        self.assertIn('def _action_group(self, title: str, *rows: QWidget) -> QFrame:', source)
        self.assertIn('def _button_row(self, *buttons: QPushButton) -> QWidget:', source)
        self.assertIn('self._action_group(', source)
        self.assertIn('"Capture"', source)
        self.assertIn('"Preview OCR"', source)
        self.assertIn('"Validation"', source)
        self.assertIn('Card("Diagnostics")', source)
        self.assertIn('def set_diagnostics_readout(self, health: dict):', source)
        self.assertIn('self.export_live_proof_button.setEnabled(True)', source)

    def test_main_window_routes_mode_specific_actions(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'main_window.py').read_text()
        self.assertIn('self.main_page.startSpecsRequested.connect(lambda: self.start_bot("specs"))', source)
        self.assertIn('self.main_page.startPowersRequested.connect(lambda: self.start_bot("powers"))', source)
        self.assertIn('self.tools_page.exportLiveProofRequested.connect(self.export_live_proof_pack)', source)
        self.assertIn('self.tools_page.previewRequested.connect(self.preview_ocr)', source)
        self.assertIn('self.tools_page.previewShardRequested.connect(self.preview_passive_shards)', source)
        self.assertIn('self.tools_page.previewPowerShardRequested.connect(self.preview_power_shards)', source)
        self.assertIn('def export_live_proof_pack(self):', source)
        self.assertIn('def _settings_for_domain(self, roll_domain: str) -> dict:', source)
        self.assertIn('settings["roll_domain"] = "powers" if str(roll_domain).strip().lower() == "powers" else "specs"', source)

    def test_ocr_previews_hide_main_window_during_capture(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'main_window.py').read_text()
        self.assertIn('def _run_with_window_hidden_for_ocr_preview(self, capture):', source)
        self.assertIn('self.hide()', source)
        self.assertIn('time.sleep(0.18)', source)
        self.assertIn('return capture()', source)
        self.assertIn('self.showMaximized()', source)
        self.assertIn('self.preview_capture_notice = QLabel("Preview restored")', source)
        self.assertIn('self._set_preview_capture_notice(True, "Preparing preview")', source)
        self.assertIn('self._set_preview_capture_notice(True, "Window hidden")', source)
        self.assertIn('self._set_preview_capture_notice(True, "Capture complete")', source)
        self.assertIn('self._set_preview_capture_notice(True, "Preview restored")', source)
        self.assertIn('OCR preview capture: hiding main window temporarily.', source)
        self.assertIn('self.controller.bot._record_timing_event(', source)
        self.assertIn('lambda: self.controller.preview_ocr(region_text)', source)
        self.assertIn('lambda: self.controller.preview_passive_shards', source)
        self.assertIn('lambda: self.controller.preview_power_shards', source)

    def test_main_page_exposes_macro_health_strip(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'pages' / 'main_page.py').read_text()
        self.assertIn('self.macro_health_value = self._value_label("Startup: none")', source)
        self.assertIn('self.auto_checkbox_health_value = self._value_label("Auto: unknown")', source)
        self.assertIn('self.verify_timing_value = self._value_label("Verify: none")', source)
        self.assertIn('def set_macro_health(self, health: dict):', source)

    def test_theme_uses_monochrome_grayscale_palette(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'theme.py').read_text()
        for value in sorted(set(re.findall(r'#[0-9a-fA-F]{6}', source))):
            r, g, b = value[1:3].lower(), value[3:5].lower(), value[5:7].lower()
            self.assertEqual((r, g), (g, b), f"{value} should be grayscale")

    def test_main_window_apply_summary_helpers_are_mode_aware(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'main_window.py').read_text()
        self.assertIn('def _specs_summary_lines(self, settings: dict) -> list[str]:', source)
        self.assertIn('def _powers_summary_lines(self, settings: dict) -> list[str]:', source)
        self.assertIn('def _apply_summary_mode(self, settings: dict | None = None) -> str:', source)
        self.assertIn('self._confirm_apply(settings, summary_mode)', source)
        self.assertIn('self._compact_target_summary(settings, summary_mode)', source)


if __name__ == '__main__':
    unittest.main()
