from __future__ import annotations

from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...backend.log_schema import summarize_log_message
from ..theme import Colors
from ..widgets.cards import Card, Pill, label
from ..widgets.tables import add_row, fill_table, make_table


class MainPage(QWidget):
    startSpecsRequested = Signal()
    startPowersRequested = Signal()
    stopRequested = Signal()
    debugRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._event_entries: list[dict] = []
        self._display_mode = "specs"
        self._active_mode = "idle"

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

        root = QVBoxLayout(content)
        root.setContentsMargins(0, 0, 2, 2)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self._build_control_card(), 1)
        top.addWidget(self._build_current_cards(), 2)
        top.addWidget(self._build_session_card(), 1)
        root.addLayout(top)
        root.addWidget(self._build_events_card())
        root.addStretch(1)

    def _build_control_card(self) -> Card:
        card = Card("Operator Control")

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_row.addWidget(label("Active Mode", "panelEyebrow"))
        self.mode_badge = Pill("Idle")
        self.mode_badge.setProperty("modeBadge", True)
        self.mode_badge.setProperty("modeTone", "idle")
        mode_row.addWidget(self.mode_badge)
        mode_row.addStretch(1)
        card.layout.addLayout(mode_row)
        card.layout.addSpacing(3)

        mode_scope_row = QHBoxLayout()
        mode_scope_row.setSpacing(6)
        self.specs_mode_badge = Pill("Specs")
        self.specs_mode_badge.setProperty("modeBadge", True)
        self.specs_mode_badge.setProperty("modeTone", "specs")
        self.specs_mode_badge.setProperty("modeActive", True)
        self.powers_mode_badge = Pill("Powers")
        self.powers_mode_badge.setProperty("modeBadge", True)
        self.powers_mode_badge.setProperty("modeTone", "powers")
        self.powers_mode_badge.setProperty("modeActive", False)
        mode_scope_row.addWidget(self.specs_mode_badge)
        mode_scope_row.addWidget(self.powers_mode_badge)
        mode_scope_row.addStretch(1)
        card.layout.addLayout(mode_scope_row)
        card.layout.addSpacing(2)

        button_row = QHBoxLayout()
        button_row.setSpacing(7)
        self.start_specs_button = QPushButton("Start Specs")
        self.start_powers_button = QPushButton("Start Powers")
        self.stop_button = QPushButton("Stop")
        for button in (self.start_specs_button, self.start_powers_button, self.stop_button):
            button.setMinimumHeight(31)
        for button in (self.start_specs_button, self.start_powers_button):
            button.setProperty("startAction", True)
            button.setProperty("activeMode", False)
        self.start_specs_button.setProperty("modeTone", "specs")
        self.start_powers_button.setProperty("modeTone", "powers")
        self.stop_button.setProperty("danger", True)
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.start_specs_button, 1)
        button_row.addWidget(self.start_powers_button, 1)
        button_row.addWidget(self.stop_button, 1)
        card.layout.addLayout(button_row)

        summary_shell = QFrame()
        summary_shell.setProperty("summaryPanel", True)
        summary_layout = QVBoxLayout(summary_shell)
        summary_layout.setContentsMargins(9, 7, 9, 8)
        summary_layout.setSpacing(4)
        summary_layout.addWidget(label("Scope", "panelEyebrow"))

        self.active_targets_label = QLabel("No active targets")
        self.active_targets_label.setWordWrap(True)
        self.active_targets_label.setProperty("role", "statusValue")
        self.active_targets_label.setProperty("summaryContent", True)
        summary_layout.addWidget(self.active_targets_label)

        self.target_profile_label = QLabel("Profile: Default")
        self.target_profile_label.setProperty("role", "tiny")
        self.target_profile_label.setWordWrap(True)
        summary_layout.addWidget(self.target_profile_label)
        card.layout.addSpacing(4)
        card.layout.addWidget(summary_shell)
        card.layout.addStretch(1)

        self.start_specs_button.clicked.connect(self.startSpecsRequested)
        self.start_powers_button.clicked.connect(self.startPowersRequested)
        self.stop_button.clicked.connect(self.stopRequested)
        return card

    def _build_current_cards(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        roll_card = Card("Current Roll")
        roll_card.setProperty("focusCard", True)
        self.roll_card_title = roll_card.title_label
        self.current_item_value = self._value_label("Waiting")
        self.current_state_value = self._value_label("Idle")
        self.current_roll_value = self._value_label("-")
        self.current_item_block = self._metric_block("Spec", self.current_item_value)
        self.current_item_block_label = self.current_item_block.findChild(QLabel, "metricTitle")
        roll_card.layout.addWidget(self.current_item_block)
        roll_card.layout.addWidget(self._metric_block("State", self.current_state_value))
        roll_card.layout.addWidget(self._metric_block("Roll", self.current_roll_value))

        detection_card = Card("Current Detection")
        detection_card.setProperty("focusCard", True)
        self.detection_card_title = detection_card.title_label
        self.current_detection_value = self._value_label("No OCR decision yet")
        self.current_ocr_value = self._value_label("-")
        self.current_detection_block = self._metric_block("Spec Detection", self.current_detection_value)
        self.current_detection_block_label = self.current_detection_block.findChild(QLabel, "metricTitle")
        detection_card.layout.addWidget(self.current_detection_block)
        detection_card.layout.addWidget(self._metric_block("OCR Pass", self.current_ocr_value))

        layout.addWidget(roll_card, 1)
        layout.addWidget(detection_card, 1)
        self.set_display_mode(self._display_mode)
        return panel

    def _build_session_card(self) -> Card:
        card = Card("Session")
        self.passive_shard_value = self._value_label("-")
        self.power_shard_value = self._value_label("-")
        self.runtime_value = self._value_label("00:00")
        self.startup_result_value = self._value_label("Not started")
        self.recovery_state_value = self._value_label("-")
        self.health_value = self._value_label("Standing by")
        self.macro_health_value = self._value_label("Startup: none")
        self.auto_checkbox_health_value = self._value_label("Auto: unknown")
        self.verify_timing_value = self._value_label("Verify: none")
        card.layout.addWidget(self._metric_block("Passive Shards", self.passive_shard_value))
        card.layout.addWidget(self._metric_block("Power Shards", self.power_shard_value))
        card.layout.addWidget(self._metric_block("Runtime", self.runtime_value))
        card.layout.addWidget(self._metric_block("Startup", self.startup_result_value))
        card.layout.addWidget(self._metric_block("Recovery", self.recovery_state_value))
        card.layout.addWidget(self._metric_block("Health", self.health_value))
        card.layout.addWidget(self._metric_block("Macro Health", self.macro_health_value))
        card.layout.addWidget(self._metric_block("Auto Confidence", self.auto_checkbox_health_value))
        card.layout.addWidget(self._metric_block("Verify Timing", self.verify_timing_value))
        card.layout.addStretch(1)
        return card

    def _build_events_card(self) -> Card:
        card = Card("Recent Events")
        card.setProperty("eventCard", True)

        feed_shell = QFrame()
        feed_shell.setProperty("container", True)
        feed_layout = QVBoxLayout(feed_shell)
        feed_layout.setContentsMargins(0, 0, 0, 0)
        feed_layout.setSpacing(6)

        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        header_row.addWidget(label("Operator Feed", "panelEyebrow"))
        header_row.addWidget(label("Full detail in Debug", "tiny"))
        header_row.addStretch(1)
        self.view_debug_button = QPushButton("View Debug")
        self.view_debug_button.setProperty("utility", True)
        self.view_debug_button.setMinimumHeight(27)
        self.view_debug_button.clicked.connect(self.debugRequested)
        header_row.addWidget(self.view_debug_button)
        feed_layout.addLayout(header_row)

        self.event_log = QTextEdit()
        self.event_log.setReadOnly(True)
        self.event_log.document().setMaximumBlockCount(180)
        self.event_log.setMinimumHeight(136)
        self.event_log.setMaximumHeight(204)
        self.event_log.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.event_log.setProperty("eventFeed", True)
        self.event_log.setHtml(self._empty_event_html())
        feed_layout.addWidget(self.event_log, 1)

        history_shell = QFrame()
        history_shell.setProperty("container", True)
        history_shell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        history_layout = QVBoxLayout(history_shell)
        history_layout.setContentsMargins(0, 2, 0, 0)
        history_layout.setSpacing(8)

        lower_header = QHBoxLayout()
        lower_header.setSpacing(8)
        lower_header.addWidget(label("Live History", "panelEyebrow"))
        lower_header.addStretch(1)
        self.toggle_near_button = QPushButton("Show Near-Misses")
        self.toggle_near_button.setProperty("utility", True)
        self.toggle_near_button.setCheckable(True)
        self.toggle_near_button.toggled.connect(self._set_near_miss_visibility)
        lower_header.addWidget(self.toggle_near_button)
        history_layout.addLayout(lower_header)

        self.recent_god_table = make_table(["Time", "Spec", "Rolled"], min_rows=4)
        self.recent_near_table = make_table(["Time", "Spec", "Stats", "Missed By"], min_rows=4)
        self.god_panel = self._table_panel("Kept Rolls", self.recent_god_table)
        self.near_panel = self._table_panel("Near-Misses", self.recent_near_table)

        history_row = QHBoxLayout()
        history_row.setSpacing(8)
        history_row.addWidget(self.god_panel, 3)
        history_row.addWidget(self.near_panel, 4)
        history_row.setStretch(0, 3)
        history_row.setStretch(1, 4)
        history_layout.addLayout(history_row, 1)

        card.layout.addWidget(feed_shell)
        card.layout.addWidget(history_shell, 1)
        self._set_near_miss_visibility(False)
        return card

    def _table_panel(self, title: str, table) -> QFrame:
        panel = QFrame()
        panel.setProperty("tableSubcard", True)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        panel.setMinimumHeight(188)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)
        header = QHBoxLayout()
        header.setSpacing(6)
        header.addWidget(label(title, "section"))
        header.addStretch(1)
        layout.addLayout(header)
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(table, 1)
        return panel

    def _metric_block(self, title: str, value: QLabel) -> QFrame:
        panel = QFrame()
        panel.setProperty("metricBlock", True)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        panel.setMinimumHeight(66)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 9, 10, 9)
        layout.setSpacing(5)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        title_label.setProperty("role", "metricBlockLabel")
        title_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        title_label.setMinimumHeight(16)
        layout.addWidget(title_label)
        layout.addWidget(value)
        return panel

    def _value_label(self, text: str) -> QLabel:
        widget = QLabel(text)
        widget.setProperty("role", "metricBlockValue")
        widget.setProperty("stateTone", "idle")
        widget.setWordWrap(True)
        widget.setMinimumHeight(28)
        widget.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return widget

    def _empty_event_html(self) -> str:
        return ('<div style="color:#7f8793; padding:2px 0;">Awaiting operator action.</div>')

    def _refresh_event_feed(self):
        visible = [entry for entry in self._event_entries if entry.get("operator_visible")]
        if not visible:
            self.event_log.setHtml(self._empty_event_html())
            return
        body = "".join(self._render_event_html(entry) for entry in visible[-40:])
        html = ('<html><body style="margin:0; padding:0; background:#0e1319;">' f'{body}' '</body></html>')
        self.event_log.setHtml(html)
        self.event_log.moveCursor(QTextCursor.End)

    def _level_color(self, level: str) -> str:
        return {
            "ok": Colors.good,
            "warn": Colors.warn,
            "error": Colors.error,
            "info": "#dce2e9",
        }.get(level, "#dce2e9")

    def _tag_color(self, category: str) -> str:
        mapping = {
            "STARTUP": "#8f99a6",
            "OCR": "#91a4ba",
            "RECOVERY": "#b1a58f",
            "ROLL": "#96b4a1",
            "DECISION": "#8a93a2",
            "WEBHOOK": "#95a2b3",
            "SETTINGS": "#7e8894",
            "HISTORY": "#7e8894",
            "USER": "#7e8894",
            "ERROR": "#c88a91",
        }
        return mapping.get(category, "#8b95a2")

    def _render_event_html(self, entry: dict) -> str:
        timestamp = escape(str(entry.get("time", "") or "")[-8:] or "--:--:--")
        category = escape(str(entry.get("category", "RUNTIME") or "RUNTIME"))
        summary = escape(summarize_log_message(entry, 162))
        level = str(entry.get("level", "info") or "info")
        level_color = self._level_color(level)
        tag_color = self._tag_color(category)
        return (
            '<div style="margin:0 0 7px 0; padding:0 0 7px 0; border-bottom:1px solid #1f2731; line-height:1.32;">'
            f'<div><span style="color:#7f8793; font-size:10px;">{timestamp}</span>'
            f'<span style="color:{tag_color}; font-weight:700;">  {category}</span>'
            f'<span style="color:{level_color}; font-weight:700;">  {level.upper()}</span></div>'
            f'<div style="color:#e5eaf0; margin-top:2px;">{summary}</div>'
            '</div>'
        )

    def load_event_entries(self, entries: list[dict]):
        self._event_entries = [entry for entry in entries if entry]
        self._refresh_event_feed()

    def append_log_entry(self, entry: dict):
        if not entry:
            return
        self._event_entries.append(entry)
        if len(self._event_entries) > 180:
            self._event_entries = self._event_entries[-180:]
        if entry.get("operator_visible"):
            self._refresh_event_feed()

    def set_status(self, text: str):
        self.current_state_value.setText(text or "Idle")
        self._apply_metric_tone(self.current_state_value, text)
        lowered = (text or "").lower()
        if "recovery" in lowered or "manual" in lowered:
            self.recovery_state_value.setText(text)
            self._apply_metric_tone(self.recovery_state_value, "warn")
        elif "rolling" in lowered:
            self.recovery_state_value.setText("Stable")
            self._apply_metric_tone(self.recovery_state_value, "good")
        elif "stopped" in lowered:
            self.health_value.setText("Stopped")
            self._apply_metric_tone(self.health_value, "error")

    def _apply_metric_tone(self, widget: QLabel, text: str):
        lowered = (text or "idle").lower()
        tone = "idle"
        if any(token in lowered for token in ("error", "failed", "stop", "blocked", "popup")):
            tone = "error"
        elif any(token in lowered for token in ("recovery", "manual", "warn", "preview")):
            tone = "warn"
        elif any(token in lowered for token in ("running", "rolling", "active", "stable", "good")):
            tone = "good"
        widget.setProperty("stateTone", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def set_shards(self, text: str):
        self.set_passive_shards(text)

    def set_passive_shards(self, text: str):
        self.passive_shard_value.setText(text or "-")

    def set_power_shards(self, text: str):
        self.power_shard_value.setText(text or "-")

    def set_session_time(self, text: str):
        self.runtime_value.setText(text or "00:00")

    def set_macro_health(self, health: dict):
        health = health or {}
        latest_verify = health.get("latest_verify") or {}
        auto = health.get("auto_checkbox") or {}
        startup_route = str(health.get("startup_route") or "none")
        recovery_route = str(health.get("recovery_route") or "none")
        checkbox_state = str(auto.get("state") or "unknown")
        checkbox_confidence = str(auto.get("confidence") or "unknown")
        ambiguous_reads = int(auto.get("ambiguous_reads") or 0)
        verify_name = str(latest_verify.get("name") or "verify")
        verify_elapsed = latest_verify.get("elapsed_ms", 0)
        verify_result = str(latest_verify.get("result") or "unknown")
        self.macro_health_value.setText(f"Startup: {startup_route}\nRecovery: {recovery_route}")
        self.auto_checkbox_health_value.setText(
            f"Auto: {checkbox_state} ({checkbox_confidence})\nAmbiguous reads: {ambiguous_reads}"
        )
        self.verify_timing_value.setText(f"{verify_name}: {verify_elapsed}ms\n{verify_result}")
        self._apply_metric_tone(self.macro_health_value, startup_route + " " + recovery_route)
        self._apply_metric_tone(self.auto_checkbox_health_value, checkbox_state + " " + checkbox_confidence)
        self._apply_metric_tone(self.verify_timing_value, verify_result)

    def set_active_targets_summary(self, text: str):
        summary = " | ".join(line.strip() for line in (text or "").splitlines() if line.strip())
        if len(summary) > 150:
            summary = summary[:147].rstrip() + "..."
        self.active_targets_label.setText(summary or "No active targets")

    def set_target_profile(self, text: str):
        self.target_profile_label.setText(f"Profile: {text or 'Default'}")

    def set_display_mode(self, mode: str):
        normalized = str(mode or "specs").strip().lower() or "specs"
        self._display_mode = "powers" if normalized == "powers" else "specs"
        item_label = "Power" if self._display_mode == "powers" else "Spec"
        item_title = "Current Power" if self._display_mode == "powers" else "Current Roll"
        detection_title = "Power Detection" if self._display_mode == "powers" else "Current Detection"
        detection_label = "Power Detection" if self._display_mode == "powers" else "Spec Detection"
        self.roll_card_title.setText(item_title)
        self.detection_card_title.setText(detection_title)
        if self.current_item_block_label is not None:
            self.current_item_block_label.setText(item_label)
        if self.current_detection_block_label is not None:
            self.current_detection_block_label.setText(detection_label)
        if not self.current_item_value.text().strip() or self.current_item_value.text().strip().lower() in {"waiting", "unknown"}:
            self.current_item_value.setText("Waiting")
        self._refresh_mode_badges()

    def set_active_mode(self, mode: str):
        normalized = str(mode or "idle").strip().lower() or "idle"
        self._active_mode = normalized if normalized in {"idle", "specs", "powers"} else "idle"
        mapping = {"idle": "Idle", "specs": "Specs", "powers": "Powers"}
        self.mode_badge.setText(mapping[self._active_mode])
        self.mode_badge.setProperty("modeTone", self._active_mode)
        self._refresh_label_style(self.mode_badge)
        self._refresh_mode_badges()
        self._refresh_start_button_state()

    def _refresh_button_style(self, button: QPushButton):
        button.style().unpolish(button)
        button.style().polish(button)

    def _refresh_label_style(self, widget: QLabel):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _refresh_mode_badges(self):
        specs_active = self._active_mode == "specs" or (self._active_mode == "idle" and self._display_mode == "specs")
        powers_active = self._active_mode == "powers" or (self._active_mode == "idle" and self._display_mode == "powers")
        for badge, active in (
            (self.specs_mode_badge, specs_active),
            (self.powers_mode_badge, powers_active),
        ):
            if badge.property("modeActive") != active:
                badge.setProperty("modeActive", active)
                self._refresh_label_style(badge)

    def _refresh_start_button_state(self):
        specs_active = self._active_mode == "specs"
        powers_active = self._active_mode == "powers"
        for button, active in (
            (self.start_specs_button, specs_active),
            (self.start_powers_button, powers_active),
        ):
            if button.property("activeMode") != active:
                button.setProperty("activeMode", active)
                self._refresh_button_style(button)

    def append_event(self, text: str, level: str = "info"):
        self.append_log_entry({
            "time": "",
            "level": level,
            "category": "RUNTIME",
            "message": text,
            "summary": text,
            "operator_visible": True,
        })

    def update_decision_chain(self, text: str):
        data = {}
        for line in (text or "").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip().lower()] = value.strip()
        if data:
            self.current_detection_value.setText(data.get("classification", "No classification yet"))
            self.current_item_value.setText(data.get("trait", "unknown"))
            self.current_roll_value.setText(data.get("values", "-"))
            self.current_ocr_value.setText(data.get("ocr", "-"))
            self.recovery_state_value.setText(data.get("recovery", self.recovery_state_value.text()))
            popup = data.get("popup", "")
            shards = data.get("shards", "")
            if "true" in popup.lower():
                self.health_value.setText("Popup visible")
            elif shards and shards != "- | -":
                self.health_value.setText("Shard OCR active")

    def set_history(self, god_rolls: list, near_misses: list):
        fill_table(self.recent_god_table, [[entry.time, entry.spec, entry.rolled] for entry in god_rolls[:8]])
        fill_table(self.recent_near_table, [[entry.time, entry.spec, entry.stats, entry.miss_distance] for entry in near_misses[:8]])

    def add_god_roll(self, entry):
        add_row(self.recent_god_table, [entry.time, entry.spec, entry.rolled], top=True)
        self._trim_table(self.recent_god_table, 8)
        self.append_log_entry({
            "time": entry.time,
            "level": "ok",
            "category": "ROLL",
            "message": f"GOD roll kept | {entry.spec}",
            "summary": f"GOD roll kept | {entry.spec}",
            "operator_visible": True,
        })

    def add_near_miss(self, entry):
        add_row(self.recent_near_table, [entry.time, entry.spec, entry.stats, entry.miss_distance], top=True)
        self._trim_table(self.recent_near_table, 8)
        self.append_log_entry({
            "time": entry.time,
            "level": "warn",
            "category": "ROLL",
            "message": f"Near miss | {entry.spec}",
            "summary": f"Near miss | {entry.spec}",
            "operator_visible": True,
        })

    def _set_near_miss_visibility(self, visible: bool):
        self.near_panel.setVisible(visible)
        if hasattr(self, "toggle_near_button"):
            self.toggle_near_button.setText("Hide Near-Misses" if visible else "Show Near-Misses")

    def _trim_table(self, table, limit: int):
        while table.rowCount() > limit:
            table.removeRow(table.rowCount() - 1)

    def set_running(self, running: bool):
        self.start_specs_button.setText("Running..." if running and self._active_mode == "specs" else "Start Specs")
        self.start_powers_button.setText("Running..." if running and self._active_mode == "powers" else "Start Powers")
        self._refresh_start_button_state()
        self.start_specs_button.setEnabled(not running)
        self.start_powers_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.health_value.setText("Running" if running else "Standing by")
        self._apply_metric_tone(self.health_value, "running" if running else "idle")
