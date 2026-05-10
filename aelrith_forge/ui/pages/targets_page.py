from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ...backend.bot import DEFAULT_CONFIG, DEFAULT_REAL_RULES, PRESET_RULES, STAT_CAPS, STAT_LABELS
from ...backend.controller import format_point
from ..widgets.cards import Card, label
from ..widgets.numeric import FocusWheelDoubleSpinBox, FocusWheelSpinBox
from ..widgets.spec_card import SpecCard


class TargetsPage(QWidget):
    FORM_LABEL_WIDTH = 112

    applyRequested = Signal()
    loadPresetRequested = Signal(str)
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
        layout.addWidget(self._build_runtime_layout_card())
        layout.addStretch(1)

    def _init_controls(self):
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["real", "test"])
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESET_RULES.keys()))
        self.nudge_spin = FocusWheelSpinBox()
        self.nudge_spin.setRange(0, 100)
        self.nudge_spin.setSuffix(" px")
        self.start_delay_spin = FocusWheelDoubleSpinBox()
        self.start_delay_spin.setRange(0.0, 60.0)
        self.start_delay_spin.setSingleStep(0.5)
        self.start_delay_spin.setSuffix(" s")
        self.region_edit = QLineEdit()
        self.region_edit.setPlaceholderText("x,y,w,h")
        self.auto_point_edit = QLineEdit()
        self.auto_point_edit.setPlaceholderText("x,y")
        self.roll_point_edit = QLineEdit()
        self.roll_point_edit.setPlaceholderText("x,y")
        self.yes_point_edit = QLineEdit()
        self.yes_point_edit.setPlaceholderText("x,y")

        self.load_preset_button = QPushButton("Load Preset")
        self.load_preset_button.setProperty("utility", True)
        self.preview_button = QPushButton("Preview OCR")
        self.preview_button.setProperty("utility", True)
        self.apply_button = QPushButton("Confirm and Apply")
        self.apply_button.setProperty("primary", True)
        for button in (self.load_preset_button, self.preview_button, self.apply_button):
            button.setMinimumHeight(30)

        self.fortune_chip = self._make_chip("Fortune Chosen")
        self.executioner_chip = self._make_chip("Executioner")
        self.rampage_chip = self._make_chip("Rampage")

        self.fortune_card = SpecCard("Fortune Chosen", STAT_LABELS["fortune"], STAT_CAPS["fortune"], DEFAULT_REAL_RULES["fortune"], expanded=True)
        self.executioner_card = SpecCard("Executioner", STAT_LABELS["executioner"], STAT_CAPS["executioner"], DEFAULT_REAL_RULES["executioner"], expanded=True)
        self.rampage_card = SpecCard("Rampage", STAT_LABELS["rampage"], STAT_CAPS["rampage"], DEFAULT_REAL_RULES["rampage"], expanded=True)

        self.target_controls = [
            self.mode_combo,
            self.preset_combo,
            self.nudge_spin,
            self.start_delay_spin,
            self.region_edit,
            self.auto_point_edit,
            self.roll_point_edit,
            self.yes_point_edit,
            self.load_preset_button,
            self.preview_button,
            self.apply_button,
            self.fortune_chip,
            self.executioner_chip,
            self.rampage_chip,
            self.fortune_card,
            self.executioner_card,
            self.rampage_card,
        ]

    def _build_profile_card(self) -> Card:
        card = Card("Spec Profile")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        grid.setColumnMinimumWidth(0, self.FORM_LABEL_WIDTH)
        grid.setColumnMinimumWidth(2, self.FORM_LABEL_WIDTH)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        card.layout.addLayout(grid)

        self._add_field(grid, 0, 0, "Mode", self.mode_combo)
        self._add_field(grid, 0, 2, "Preset", self.preset_combo)
        self._add_field(grid, 1, 0, "Auto Nudge", self.nudge_spin)
        self._add_field(grid, 1, 2, "Start Delay", self.start_delay_spin)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(self.load_preset_button)
        actions.addStretch(1)
        actions.addWidget(self.apply_button)
        card.layout.addLayout(actions)

        self.load_preset_button.clicked.connect(lambda: self.loadPresetRequested.emit(self.preset_combo.currentText()))
        self.apply_button.clicked.connect(self.applyRequested)
        return card

    def _build_active_summary_card(self) -> Card:
        card = Card("Active Specs")
        self.active_targets_label = QLabel("No specs applied")
        self.active_targets_label.setProperty("container", True)
        self.active_targets_label.setProperty("summary", True)
        self.active_targets_label.setWordWrap(True)
        self.active_targets_label.setProperty("role", "muted")
        card.layout.addWidget(self.active_targets_label)
        return card

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
        chip_row.addWidget(self.fortune_chip)
        chip_row.addWidget(self.executioner_chip)
        chip_row.addWidget(self.rampage_chip)
        chip_row.addStretch(1)
        layout.addLayout(chip_row)

        layout.addWidget(self.fortune_card)
        layout.addWidget(self.executioner_card)
        layout.addWidget(self.rampage_card)
        return panel

    def _build_runtime_layout_card(self) -> Card:
        card = Card("Runtime Layout")
        card.setProperty("secondaryCard", True)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        grid.setColumnMinimumWidth(0, self.FORM_LABEL_WIDTH)
        grid.setColumnStretch(1, 1)
        card.layout.addLayout(grid)
        self._add_pickable_field(grid, 0, "Current spec OCR region", self.region_edit, "stats_region")
        self._add_pickable_field(grid, 1, "Auto button click", self.auto_point_edit, "auto", point=True)
        self._add_pickable_field(grid, 2, "Reroll button click", self.roll_point_edit, "roll", point=True)
        self._add_pickable_field(grid, 3, "Confirm reroll click", self.yes_point_edit, "yes", point=True)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(self.preview_button)
        actions.addStretch(1)
        card.layout.addLayout(actions)

        self.preview_button.clicked.connect(self.previewRequested)
        return card

    def _add_field(self, grid: QGridLayout, row: int, col: int, title: str, widget, span: int = 1):
        title_label = QLabel(title)
        title_label.setProperty("role", "muted")
        title_label.setFixedWidth(self.FORM_LABEL_WIDTH)
        grid.addWidget(title_label, row, col)
        grid.addWidget(widget, row, col + 1, 1, span)

    def _add_pickable_field(self, grid: QGridLayout, row: int, title: str, widget: QLineEdit, key: str, point: bool = False):
        title_label = QLabel(title)
        title_label.setProperty("role", "muted")
        title_label.setFixedWidth(self.FORM_LABEL_WIDTH)
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

    def _make_chip(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(True)
        button.setProperty("chip", True)
        return button

    def collect_target_settings(self) -> dict:
        fortune_chosen = self.fortune_card.get_ranges()
        return {
            "mode": self.mode_combo.currentText(),
            "preset": self.preset_combo.currentText(),
            "nudge": self.nudge_spin.value(),
            "start_delay": self.start_delay_spin.value(),
            "stats_region": self.region_edit.text().strip(),
            "coords": {
                "auto": self.auto_point_edit.text().strip(),
                "roll": self.roll_point_edit.text().strip(),
                "yes": self.yes_point_edit.text().strip(),
            },
            "enabled_specs": {
                "fortune_chosen": self.fortune_chip.isChecked(),
                "executioner": self.executioner_chip.isChecked(),
                "rampage": self.rampage_chip.isChecked(),
            },
            "real_rules": {
                "fortune": fortune_chosen,
                "chosen": fortune_chosen,
                "executioner": self.executioner_card.get_ranges(),
                "rampage": self.rampage_card.get_ranges(),
            },
        }

    def load_settings(self, settings: dict):
        self.mode_combo.setCurrentText(str(settings.get("mode", "real")))
        self.preset_combo.setCurrentText(str(settings.get("preset", "Default")))
        self.nudge_spin.setValue(int(settings.get("nudge", 10)))
        self.start_delay_spin.setValue(float(settings.get("start_delay", 2.0)))
        self.region_edit.setText(str(settings.get("stats_region", "920,520,320,85")))

        coords = settings.get("coords") or {}
        self.auto_point_edit.setText(str(coords.get("auto", format_point(DEFAULT_CONFIG["AUTO_CHECKBOX"]))))
        self.roll_point_edit.setText(str(coords.get("roll", format_point(DEFAULT_CONFIG["ROLL_BUTTON"]))))
        self.yes_point_edit.setText(str(coords.get("yes", format_point(DEFAULT_CONFIG["YES_BUTTON"]))))

        enabled = settings.get("enabled_specs") or {}
        self.fortune_chip.setChecked(bool(enabled.get("fortune_chosen", True)))
        self.executioner_chip.setChecked(bool(enabled.get("executioner", True)))
        self.rampage_chip.setChecked(bool(enabled.get("rampage", True)))

        rules = settings.get("real_rules") or {}
        self.fortune_card.set_ranges(rules.get("fortune", DEFAULT_REAL_RULES["fortune"]))
        self.executioner_card.set_ranges(rules.get("executioner", DEFAULT_REAL_RULES["executioner"]))
        self.rampage_card.set_ranges(rules.get("rampage", DEFAULT_REAL_RULES["rampage"]))

    def apply_preset_rules(self, rules: dict):
        self.fortune_card.set_ranges(rules["fortune"])
        self.executioner_card.set_ranges(rules["executioner"])
        self.rampage_card.set_ranges(rules["rampage"])

    def set_stats_region(self, region_text: str):
        self.region_edit.setText(region_text)

    def set_point(self, name: str, point_text: str):
        if name == "auto":
            self.auto_point_edit.setText(point_text)
        elif name == "roll":
            self.roll_point_edit.setText(point_text)
        elif name == "yes":
            self.yes_point_edit.setText(point_text)

    def set_active_targets_summary(self, text: str):
        summary = str(text or "").strip()
        if len(summary) > 180:
            summary = summary[:177].rstrip() + "..."
        self.active_targets_label.setText(summary or "No specs applied")

    def set_running(self, running: bool):
        for widget in self.target_controls:
            widget.setEnabled(not running)
