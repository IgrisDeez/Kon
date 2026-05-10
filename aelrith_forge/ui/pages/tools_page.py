from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..widgets.cards import Card, label


class ToolsPage(QWidget):
    captureDebugRequested = Signal()
    captureScreenshotRequested = Signal()
    exportLiveProofRequested = Signal()
    previewRequested = Signal(str)
    previewShardRequested = Signal()
    previewPowerShardRequested = Signal()
    testPopupRequested = Signal(str)
    testClassificationRequested = Signal(str)
    testWebhookRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        content = QWidget()
        content.setProperty("container", True)
        self.scroll.setWidget(content)
        shell.addWidget(self.scroll)

        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 2, 2)
        self.content_layout.setSpacing(10)
        self.content_layout.addWidget(self._build_shared_tools())
        self.content_layout.addWidget(self._build_specs_tools())
        self.content_layout.addWidget(self._build_powers_tools())
        self.content_layout.addWidget(self._build_network_tools())
        self.content_layout.addWidget(self._build_diagnostics_readout())
        self.content_layout.addStretch(1)

    def _button(self, text: str) -> QPushButton:
        button = QPushButton(text)
        button.setProperty("utility", True)
        button.setMinimumHeight(28)
        button.setMinimumWidth(max(126, min(280, len(text) * 7 + 34)))
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if not hasattr(self, "tool_buttons"):
            self.tool_buttons = []
        self.tool_buttons.append(button)
        return button

    def _button_row(self, *buttons: QPushButton) -> QWidget:
        row_widget = QWidget()
        row_widget.setProperty("container", True)
        row = QHBoxLayout(row_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        for button in buttons:
            row.addWidget(button)
        row.addStretch(1)
        return row_widget

    def _action_group(self, title: str, *rows: QWidget) -> QFrame:
        group = QFrame()
        group.setProperty("actionGroup", True)
        group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(9)
        title_label = label(title, "panelEyebrow")
        title_label.setObjectName(f"toolActionGroup_{title.replace(' ', '_').replace('/', '_')}")
        title_label.setMinimumHeight(17)
        layout.addWidget(title_label)
        for row in rows:
            layout.addWidget(row)
        return group

    def _build_shared_tools(self) -> Card:
        card = Card("Shared / General Tools")
        card.setProperty("secondaryCard", True)
        self.capture_debug_button = self._button("Capture Debug Report")
        self.capture_screenshot_button = self._button("Capture Current Screenshot")
        self.export_live_proof_button = self._button("Export Live Proof Pack")
        self.preview_shards_button = self._button("Test Passive Shard OCR")
        self.preview_power_shards_button = self._button("Test Power Shard OCR")
        self.capture_debug_button.clicked.connect(self.captureDebugRequested)
        self.capture_screenshot_button.clicked.connect(self.captureScreenshotRequested)
        self.export_live_proof_button.clicked.connect(self.exportLiveProofRequested)
        self.preview_shards_button.clicked.connect(self.previewShardRequested)
        self.preview_power_shards_button.clicked.connect(self.previewPowerShardRequested)
        card.layout.addWidget(self._action_group(
            "Capture",
            self._button_row(self.capture_debug_button, self.capture_screenshot_button, self.export_live_proof_button),
        ))
        card.layout.addWidget(self._action_group(
            "Preview OCR",
            self._button_row(self.preview_shards_button, self.preview_power_shards_button),
        ))
        return card

    def _build_specs_tools(self) -> Card:
        card = Card("Specs Subsystem Tests")
        card.setProperty("secondaryCard", True)
        self.preview_ocr_specs_button = self._button("OCR Preview (Specs)")
        self.test_popup_specs_button = self._button("Test Popup Detection (Specs)")
        self.test_classification_specs_button = self._button("Test Current Roll Classification (Specs)")
        self.preview_ocr_specs_button.clicked.connect(lambda: self.previewRequested.emit("specs"))
        self.test_popup_specs_button.clicked.connect(lambda: self.testPopupRequested.emit("specs"))
        self.test_classification_specs_button.clicked.connect(lambda: self.testClassificationRequested.emit("specs"))
        card.layout.addWidget(self._action_group("Preview OCR", self._button_row(self.preview_ocr_specs_button)))
        card.layout.addWidget(self._action_group(
            "Validation",
            self._button_row(self.test_popup_specs_button, self.test_classification_specs_button),
        ))
        return card

    def _build_powers_tools(self) -> Card:
        card = Card("Powers Subsystem Tests")
        card.setProperty("secondaryCard", True)
        self.preview_ocr_powers_button = self._button("OCR Preview (Powers)")
        self.test_popup_powers_button = self._button("Test Popup Detection (Powers)")
        self.test_classification_powers_button = self._button("Test Current Roll Classification (Powers)")
        self.preview_ocr_powers_button.clicked.connect(lambda: self.previewRequested.emit("powers"))
        self.test_popup_powers_button.clicked.connect(lambda: self.testPopupRequested.emit("powers"))
        self.test_classification_powers_button.clicked.connect(lambda: self.testClassificationRequested.emit("powers"))
        card.layout.addWidget(self._action_group("Preview OCR", self._button_row(self.preview_ocr_powers_button)))
        card.layout.addWidget(self._action_group(
            "Validation",
            self._button_row(self.test_popup_powers_button, self.test_classification_powers_button),
        ))
        return card

    def _build_network_tools(self) -> Card:
        card = Card("Webhook")
        card.setProperty("secondaryCard", True)
        self.test_webhook_button = self._button("Test Webhook")
        self.test_webhook_button.clicked.connect(self.testWebhookRequested)
        card.layout.addWidget(self._action_group("Webhook", self._button_row(self.test_webhook_button)))
        return card

    def _build_diagnostics_readout(self) -> Card:
        card = Card("Diagnostics")
        card.setProperty("secondaryCard", True)
        self.macro_timing_readout = QLabel("Recent startup/recovery timing: none")
        self.macro_timing_readout.setWordWrap(True)
        self.macro_timing_readout.setProperty("role", "tiny")
        self.checkbox_ambiguity_readout = QLabel("Auto checkbox ambiguity: 0")
        self.checkbox_ambiguity_readout.setWordWrap(True)
        self.checkbox_ambiguity_readout.setProperty("role", "tiny")
        diagnostics_body = QWidget()
        diagnostics_body.setProperty("container", True)
        diagnostics_layout = QVBoxLayout(diagnostics_body)
        diagnostics_layout.setContentsMargins(0, 0, 0, 0)
        diagnostics_layout.setSpacing(5)
        diagnostics_layout.addWidget(self.macro_timing_readout)
        diagnostics_layout.addWidget(self.checkbox_ambiguity_readout)
        card.layout.addWidget(self._action_group("Timing / Recovery", diagnostics_body))
        return card

    def set_diagnostics_readout(self, health: dict):
        health = health or {}
        latest_verify = health.get("latest_verify") or {}
        auto = health.get("auto_checkbox") or {}
        cache = health.get("verification_cache") or {}
        elapsed = latest_verify.get("elapsed_ms", 0)
        result = latest_verify.get("result", "unknown")
        name = latest_verify.get("name", "verify")
        polls = f"{cache.get('polls_seen', 0)}/{cache.get('polls_planned', 0)}"
        hits = cache.get("cache_hits", 0)
        misses = cache.get("cache_misses", 0)
        self.macro_timing_readout.setText(
            f"Recent startup/recovery timing: {name} | {elapsed}ms | {result} | polls {polls} | cache {hits}/{misses}"
        )
        self.checkbox_ambiguity_readout.setText(
            f"Auto checkbox ambiguity: {auto.get('ambiguous_reads', 0)} / {auto.get('reads', 0)} reads"
        )

    def set_running(self, running: bool):
        for button in getattr(self, "tool_buttons", []):
            button.setEnabled(not running)
        if hasattr(self, "export_live_proof_button"):
            self.export_live_proof_button.setEnabled(True)
