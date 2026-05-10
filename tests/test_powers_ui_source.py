import ast
from pathlib import Path
import unittest


class PowersPageInitOrderTests(unittest.TestCase):
    def test_shared_controls_are_initialized_before_section_builders(self):
        source_path = Path(__file__).resolve().parents[1] / "aelrith_forge" / "ui" / "pages" / "powers_page.py"
        tree = ast.parse(source_path.read_text())
        powers_page = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PowersPage")
        init_fn = next(node for node in powers_page.body if isinstance(node, ast.FunctionDef) and node.name == "__init__")
        calls = []
        for stmt in init_fn.body:
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
                    calls.append(node.func.attr)
        self.assertIn("_init_controls", calls)
        self.assertLess(calls.index("_init_controls"), calls.index("_build_targets_panel"))
        self.assertLess(calls.index("_init_controls"), calls.index("_build_layout_card"))

    def test_init_controls_defines_shared_widgets_used_by_targets_panel(self):
        source_path = Path(__file__).resolve().parents[1] / "aelrith_forge" / "ui" / "pages" / "powers_page.py"
        tree = ast.parse(source_path.read_text())
        powers_page = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "PowersPage")
        init_controls_fn = next(node for node in powers_page.body if isinstance(node, ast.FunctionDef) and node.name == "_init_controls")
        assigned = set()
        for stmt in init_controls_fn.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                        assigned.add(target.attr)
        expected = {
            "current_power_region_edit",
            "preview_region_edit",
            "auto_check_region_edit",
            "confirm_check_region_edit",
            "popup_region_edit",
            "change_exclusion_region_edit",
            "auto_point_edit",
            "roll_point_edit",
            "yes_point_edit",
            "preview_button",
            "apply_button",
            "power_chips",
            "power_cards",
            "target_controls",
        }
        self.assertTrue(expected.issubset(assigned))

    def test_power_threshold_cards_use_rule_targets_including_passives(self):
        source_path = Path(__file__).resolve().parents[1] / "aelrith_forge" / "ui" / "pages" / "powers_page.py"
        source = source_path.read_text()
        self.assertIn("definition.rule_targets", source)
        self.assertIn("definition.rule_caps", source)

    def test_preview_action_moves_to_runtime_layout_while_apply_stays_in_profile(self):
        source_path = Path(__file__).resolve().parents[1] / "aelrith_forge" / "ui" / "pages" / "powers_page.py"
        source = source_path.read_text()
        self.assertIn('self.info_label = QLabel("Supported mythicals: Cursebrand, Colossus, Subjugator\\nSet Preview OCR region and click points below, then apply.")', source)
        self.assertIn("card.layout.addWidget(self._build_operator_setup_group())", source)
        self.assertIn("actions.addWidget(self.preview_button)", source)
        self.assertIn("actions.addWidget(self.apply_button)", source)
        self.assertLess(
            source.index("def _build_profile_card"),
            source.index("actions.addWidget(self.apply_button)"),
        )
        self.assertLess(
            source.index("def _build_layout_card"),
            source.rindex("actions.addWidget(self.preview_button)"),
        )


if __name__ == "__main__":
    unittest.main()
