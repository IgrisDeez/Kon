from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UiHierarchyCleanupSourceTests(unittest.TestCase):
    def test_settings_page_keeps_only_global_runtime_controls(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'pages' / 'settings_page.py').read_text()
        self.assertIn('Card("Global Runtime Behavior")', source)
        self.assertIn('"Power shard region"', source)
        self.assertIn('"Pick Power Shards"', source)
        self.assertIn('"Preview Power Shards"', source)
        self.assertNotIn('Auto checkbox', source)
        self.assertNotIn('Roll button', source)
        self.assertNotIn('Yes button', source)
        self.assertNotIn('pickAutoRequested', source)
        self.assertNotIn('pickRollRequested', source)
        self.assertNotIn('pickYesRequested', source)
        self.assertNotIn('roll_domain_combo', source)

    def test_specs_tab_owns_specs_click_points(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'pages' / 'targets_page.py').read_text()
        self.assertIn('pickPointRequested = Signal(str)', source)
        self.assertIn('"Auto button click"', source)
        self.assertIn('"Reroll button click"', source)
        self.assertIn('"Confirm reroll click"', source)
        self.assertIn('"coords": {', source)

    def test_powers_normal_setup_is_preview_plus_clicks_with_advanced_hidden_group(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'pages' / 'powers_page.py').read_text()
        self.assertIn('label("Normal Operator Setup", "section")', source)
        self.assertIn('"Preview OCR region"', source)
        self.assertIn('"Show Advanced Detection Regions"', source)
        self.assertIn('label("Advanced Detection Regions", "section")', source)
        self.assertIn('"Current power OCR region"', source)
        self.assertIn('"Popup detection region"', source)
        self.assertIn('"Change-detection exclusion region"', source)

    def test_main_window_routes_specs_point_picking_to_specs_tab(self):
        source = (ROOT / 'aelrith_forge' / 'ui' / 'main_window.py').read_text()
        self.assertIn('self.target_page.pickPointRequested.connect(self.pick_specs_point)', source)
        self.assertIn('def pick_specs_point(self, name: str):', source)
        self.assertIn('self.target_page.set_point(name, format_point(point))', source)
        self.assertNotIn('self.settings_page.pickAutoRequested', source)

    def test_controller_maps_hidden_power_fields_to_runtime_layout(self):
        source = (ROOT / 'aelrith_forge' / 'backend' / 'controller.py').read_text()
        self.assertIn('power_layout["stats_region"] = power_layout["current_power_region"]', source)
        self.assertIn('power_layout["protected_region"] = power_layout["change_detection_exclusion_region"]', source)
        self.assertIn('popup_candidate = data.get("popup_region")', source)
        self.assertIn('change_exclusion_candidate = data.get("protected_region")', source)


if __name__ == '__main__':
    unittest.main()
