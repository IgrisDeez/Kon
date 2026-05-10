from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ...backend.powers import POWER_DEFAULT_RULES, SUPPORTED_POWER_DEFINITIONS, power_display_name
from ..widgets.cards import Card, label
from ..widgets.spec_card import SpecCard


class PowersPage(QWidget):
    NORMAL_FORM_LABEL_WIDTH = 112
    ADVANCED_FORM_LABEL_WIDTH = 164

    applyRequested = Signal()
    previewRequested = Signal()
    pickRegionRequested = Signal(str)
    pickPointRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_controls()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        root.addWidget(scroll)

        self.content = QWidget()
        self.content.setProperty("container", True)
        scroll.setWidget(self.content)
        layout = QVBoxLayout(self.content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_profile_card())
        layout.addWidget(self._build_active_summary_card())
        layout.addWidget(self._build_targets_panel())
        layout.addWidget(self._build_layout_card())
        layout.addStretch(1)

    def _init_controls(self):
        self.preview_region_edit = QLineEdit()
        self.preview_region_edit.setPlaceholderText("x,y,w,h")
        self.current_power_region_edit = QLineEdit()
        self.auto_check_region_edit = QLineEdit()
        self.confirm_check_region_edit = QLineEdit()
        self.popup_region_edit = QLineEdit()
        self.change_exclusion_region_edit = QLineEdit()

        self.auto_point_edit = QLineEdit()
        self.roll_point_edit = QLineEdit()
        self.yes_point_edit = QLineEdit()
        for widget in (self.auto_point_edit, self.roll_point_edit, self.yes_point_edit):
            widget.setPlaceholderText("x,y")

        self.preview_button = QPushButton("Preview OCR")
        self.preview_button.setProperty("utility", True)
        self.preview_button.clicked.connect(self.previewRequested)

        self.apply_button = QPushButton("Confirm and Apply")
        self.apply_button.setProperty("primary", True)
        self.apply_button.clicked.connect(self.applyRequested)
        for button in (self.preview_button, self.apply_button):
            button.setMinimumHeight(30)

        self.advanced_toggle_button = QPushButton("Show Advanced Detection Regions")
        self.advanced_toggle_button.setProperty("utility", True)
        self.advanced_toggle_button.setCheckable(True)
        self.advanced_toggle_button.setMinimumHeight(30)
        self.advanced_toggle_button.toggled.connect(self._set_advanced_regions_visible)

        self.power_chips = {}
        self.power_cards = {}
        self.target_controls = []
        self._advanced_region_panel: QWidget | None = None

    def _build_profile_card(self) -> Card:
        card = Card("Power Profile")
        self.info_label = QLabel("Supported mythicals: Cursebrand, Colossus, Subjugator\nSet Preview OCR region and click points below, then apply.")
        self.info_label.setWordWrap(True)
        self.info_label.setProperty("summary", True)
        self.info_label.setProperty("role", "muted")
        card.layout.addWidget(self.info_label)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addStretch(1)
        actions.addWidget(self.apply_button)
        card.layout.addLayout(actions)
        return card

    def _build_active_summary_card(self) -> Card:
        card = Card("Active Powers")
        self.active_targets_label = QLabel("No powers applied")
        self.active_targets_label.setProperty("container", True)
        self.active_targets_label.setProperty("summary", True)
        self.active_targets_label.setProperty("role", "muted")
        self.active_targets_label.setWordWrap(True)
        card.layout.addWidget(self.active_targets_label)
        return card

    def _build_layout_card(self) -> Card:
        card = Card("Runtime Layout")
        card.setProperty("secondaryCard", True)

        card.layout.addWidget(self._build_operator_setup_group())

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(self.preview_button)
        actions.addStretch(1)
        card.layout.addLayout(actions)

        toggle_row = QHBoxLayout()
        toggle_row.setSpacing(6)
        toggle_row.addWidget(self.advanced_toggle_button)
        toggle_row.addStretch(1)
        card.layout.addLayout(toggle_row)

        self._advanced_region_panel = self._build_advanced_region_group()
        self._advanced_region_panel.setVisible(False)
        card.layout.addWidget(self._advanced_region_panel)
        return card

    def _build_operator_setup_group(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("summaryPanel", True)
        grid = QGridLayout(panel)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        grid.setContentsMargins(9, 7, 9, 8)
        grid.setColumnMinimumWidth(0, self.NORMAL_FORM_LABEL_WIDTH)
        grid.setColumnStretch(1, 1)

        grid.addWidget(label("Normal Operator Setup", "section"), 0, 0, 1, 3)
        self._add_pickable_field(grid, 1, "Preview OCR region", self.preview_region_edit, "preview_region")
        self._add_pickable_field(grid, 2, "Auto button click", self.auto_point_edit, "auto", point=True)
        self._add_pickable_field(grid, 3, "Reroll button click", self.roll_point_edit, "roll", point=True)
        self._add_pickable_field(grid, 4, "Confirm reroll click", self.yes_point_edit, "yes", point=True)
        return panel

    def _build_advanced_region_group(self) -> QWidget:
        panel = QFrame()
        panel.setProperty("secondaryCard", True)
        grid = QGridLayout(panel)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        grid.setContentsMargins(9, 7, 9, 8)
        grid.setColumnMinimumWidth(0, self.ADVANCED_FORM_LABEL_WIDTH)
        grid.setColumnStretch(1, 1)

        grid.addWidget(label("Advanced Detection Regions", "section"), 0, 0, 1, 3)
        self._add_pickable_field(
            grid,
            1,
            "Current power OCR region",
            self.current_power_region_edit,
            "current_power_region",
            label_width=self.ADVANCED_FORM_LABEL_WIDTH,
        )
        self._add_pickable_field(
            grid,
            2,
            "Auto button OCR / check region",
            self.auto_check_region_edit,
            "auto_check_region",
            label_width=self.ADVANCED_FORM_LABEL_WIDTH,
        )
        self._add_pickable_field(
            grid,
            3,
            "Confirm reroll OCR / check region",
            self.confirm_check_region_edit,
            "confirm_check_region",
            label_width=self.ADVANCED_FORM_LABEL_WIDTH,
        )
        self._add_pickable_field(
            grid,
            4,
            "Popup detection region",
            self.popup_region_edit,
            "popup_region",
            label_width=self.ADVANCED_FORM_LABEL_WIDTH,
        )
        self._add_pickable_field(
            grid,
            5,
            "Change-detection exclusion region",
            self.change_exclusion_region_edit,
            "change_detection_exclusion_region",
            label_width=self.ADVANCED_FORM_LABEL_WIDTH,
        )
        return panel

    def _build_targets_panel(self) -> QWidget:
        panel = QWidget()
        panel.setProperty("container", True)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.addWidget(label("Desired Roll Thresholds", "section"))
        header.addStretch(1)
        layout.addLayout(header)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(7)
        chip_row.addWidget(label("Enabled", "muted"))
        self.power_chips.clear()
        for key in SUPPORTED_POWER_DEFINITIONS:
            chip = QPushButton(power_display_name(key))
            chip.setCheckable(True)
            chip.setChecked(True)
            chip.setProperty("chip", True)
            self.power_chips[key] = chip
            chip_row.addWidget(chip)
        chip_row.addStretch(1)
        layout.addLayout(chip_row)

        self.power_cards.clear()
        for key, definition in SUPPORTED_POWER_DEFINITIONS.items():
            labels = [
                f"{target.label}{' (Optional)' if not target.required else ''}"
                for target in definition.rule_targets
            ]
            card = SpecCard(definition.name, labels, definition.rule_caps, POWER_DEFAULT_RULES[key], expanded=True)
            self.power_cards[key] = card
            layout.addWidget(card)

        self.target_controls = [
            self.preview_region_edit,
            self.current_power_region_edit,
            self.auto_check_region_edit,
            self.confirm_check_region_edit,
            self.popup_region_edit,
            self.change_exclusion_region_edit,
            self.auto_point_edit,
            self.roll_point_edit,
            self.yes_point_edit,
            self.preview_button,
            self.apply_button,
            self.advanced_toggle_button,
            *self.power_chips.values(),
            *self.power_cards.values(),
        ]
        return panel

    def _set_advanced_regions_visible(self, visible: bool):
        if self._advanced_region_panel is not None:
            self._advanced_region_panel.setVisible(visible)
        self.advanced_toggle_button.setText(
            "Hide Advanced Detection Regions" if visible else "Show Advanced Detection Regions"
        )

    def _add_pickable_field(
        self,
        grid: QGridLayout,
        row: int,
        title: str,
        widget: QLineEdit,
        key: str,
        point: bool = False,
        label_width: int | None = None,
    ):
        title_label = QLabel(title)
        title_label.setProperty("role", "muted")
        title_label.setFixedWidth(label_width or self.NORMAL_FORM_LABEL_WIDTH)
        widget.setPlaceholderText("x,y" if point else "x,y,w,h")
        button = QPushButton("Pick")
        button.setProperty("utility", True)
        button.setMinimumHeight(30)
        if point:
            button.clicked.connect(lambda _checked=False, field_key=key: self.pickPointRequested.emit(field_key))
        else:
            button.clicked.connect(lambda _checked=False, field_key=key: self.pickRegionRequested.emit(field_key))
        grid.addWidget(title_label, row, 0)
        grid.addWidget(widget, row, 1)
        grid.addWidget(button, row, 2)

    def collect_power_settings(self) -> dict:
        preview_region = self.preview_region_edit.text().strip()
        current_power_region = self.current_power_region_edit.text().strip() or preview_region
        auto_check_region = self.auto_check_region_edit.text().strip()
        confirm_check_region = self.confirm_check_region_edit.text().strip()
        popup_region = self.popup_region_edit.text().strip()
        change_exclusion_region = self.change_exclusion_region_edit.text().strip()
        return {
            "powers_layout": {
                "current_power_region": current_power_region,
                "stats_region": current_power_region,
                "preview_region": preview_region,
                "auto_check_region": auto_check_region,
                "confirm_check_region": confirm_check_region,
                "popup_region": popup_region,
                "change_detection_exclusion_region": change_exclusion_region,
                "protected_region": change_exclusion_region,
                "coords": {
                    "auto": self.auto_point_edit.text().strip(),
                    "roll": self.roll_point_edit.text().strip(),
                    "yes": self.yes_point_edit.text().strip(),
                },
            },
            "enabled_powers": {key: widget.isChecked() for key, widget in self.power_chips.items()},
            "powers_rules": {key: card.get_ranges() for key, card in self.power_cards.items()},
        }

    def load_settings(self, settings: dict):
        layout = settings.get("powers_layout") or {}
        coords = layout.get("coords") or {}
        preview_region = layout.get("preview_region", layout.get("current_power_region", layout.get("stats_region", "0,0,0,0")))
        current_power_region = layout.get("current_power_region", layout.get("stats_region", preview_region))
        change_exclusion_region = layout.get("change_detection_exclusion_region", layout.get("protected_region", "0,0,0,0"))
        self.preview_region_edit.setText(str(preview_region))
        self.current_power_region_edit.setText(str(current_power_region))
        self.auto_check_region_edit.setText(str(layout.get("auto_check_region", "0,0,0,0")))
        self.confirm_check_region_edit.setText(str(layout.get("confirm_check_region", "0,0,0,0")))
        self.popup_region_edit.setText(str(layout.get("popup_region", "0,0,0,0")))
        self.change_exclusion_region_edit.setText(str(change_exclusion_region))
        self.auto_point_edit.setText(str(coords.get("auto", "0,0")))
        self.roll_point_edit.setText(str(coords.get("roll", "0,0")))
        self.yes_point_edit.setText(str(coords.get("yes", "0,0")))

        enabled = settings.get("enabled_powers") or {}
        for key, chip in self.power_chips.items():
            chip.setChecked(bool(enabled.get(key, True)))

        rules = settings.get("powers_rules") or {}
        for key, card in self.power_cards.items():
            card.set_ranges(rules.get(key, POWER_DEFAULT_RULES[key]))

    def set_active_targets_summary(self, text: str):
        summary = str(text or "").strip()
        if len(summary) > 180:
            summary = summary[:177].rstrip() + "..."
        self.active_targets_label.setText(summary or "No powers applied")

    def set_running(self, running: bool):
        for widget in self.target_controls:
            widget.setEnabled(not running)
