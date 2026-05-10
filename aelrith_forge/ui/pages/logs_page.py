from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QTextEdit, QVBoxLayout, QWidget

from ... import APP_DISPLAY_NAME
from ...backend.log_schema import summarize_log_message
from ..theme import Colors
from ..widgets.cards import Card


class LogsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        summary_card = Card("Last Decision Chain")
        summary_card.setProperty("secondaryCard", True)
        grid = QGridLayout()
        grid.setHorizontalSpacing(11)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, 88)
        grid.setColumnStretch(1, 1)
        summary_card.layout.addLayout(grid)
        self.debug_fields = {}
        for row, key in enumerate(("Classification", "Trait", "OCR", "Recovery", "Popup", "Shards")):
            title = QLabel(key)
            title.setProperty("role", "muted")
            value = QLabel("-")
            value.setWordWrap(True)
            value.setProperty("role", "statusValue")
            grid.addWidget(title, row, 0)
            grid.addWidget(value, row, 1)
            self.debug_fields[key.lower()] = value

        log_card = Card("Runtime Log")
        log_card.setProperty("focusCard", True)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.document().setMaximumBlockCount(360)
        self.log_output.setMinimumHeight(230)
        log_card.layout.addWidget(self.log_output)

        raw_card = Card("Raw Debug Trace")
        raw_card.setProperty("secondaryCard", True)
        self.decision_chain = QPlainTextEdit()
        self.decision_chain.setReadOnly(True)
        self.decision_chain.setMinimumHeight(118)
        self.decision_chain.setPlainText("No decisions recorded yet.")
        raw_card.layout.addWidget(self.decision_chain)

        preview_card = Card("Discord Message Preview")
        preview_card.setProperty("secondaryCard", True)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(118)
        preview_card.layout.addWidget(self.preview)

        lower_row = QHBoxLayout()
        lower_row.setSpacing(8)
        lower_row.addWidget(raw_card, 3)
        lower_row.addWidget(preview_card, 2)

        layout.addWidget(summary_card, 1)
        layout.addWidget(log_card, 3)
        layout.addLayout(lower_row, 2)
        self.update_preview("", "Fortune Chosen", "Drop 30 | Luck 10")

    def _level_color(self, level: str) -> str:
        return {
            "ok": Colors.good,
            "warn": Colors.warn,
            "error": Colors.error,
            "info": Colors.text,
        }.get(level, Colors.text)

    def _meta_color(self, category: str) -> str:
        return {
            "STARTUP": "#97a2af",
            "OCR": "#93a5bb",
            "RECOVERY": "#c0a478",
            "ROLL": "#97b8a3",
            "DECISION": "#8d98a6",
            "WEBHOOK": "#9aa6b7",
            "SETTINGS": "#7d8793",
            "HISTORY": "#7d8793",
            "USER": "#7d8793",
        }.get(category, "#8f99a6")

    def _render_log_html(self, entry: dict) -> str:
        timestamp = escape(str(entry.get("time", "") or "")[-8:] or "--:--:--")
        category = escape(str(entry.get("category", "RUNTIME") or "RUNTIME"))
        subsystem = escape(str(entry.get("subsystem", "Runtime") or "Runtime"))
        level = str(entry.get("level", "info") or "info")
        event_code = escape(str(entry.get("event_code", "") or ""))
        summary = escape(summarize_log_message(entry, 220))
        raw = escape(str(entry.get("message", "") or ""))
        meta_color = self._meta_color(category)
        level_color = self._level_color(level)
        detail_html = ""
        if raw != summary:
            detail_html = f'<div style="color:#8d96a2; margin-top:2px;">{raw}</div>'
        return (
            '<div style="margin:0 0 8px 0; padding-bottom:6px; border-bottom:1px solid #232b35;">'
            f'<div><span style="color:#7f8793; font-size:10px;">{timestamp}</span>'
            f'<span style="color:{meta_color}; font-weight:700;">  {category}</span>'
            f'<span style="color:#7f8793;">  {subsystem}</span>'
            f'<span style="color:{level_color}; font-weight:700;">  {level.upper()}</span></div>'
            f'<div style="color:#e8edf3; margin-top:2px;">{summary}</div>'
            f'<div style="color:#717b88; font-size:10px; margin-top:1px;">{event_code}</div>'
            f'{detail_html}'
            '</div>'
        )

    def load_log_entries(self, entries: list[dict]):
        self.log_output.clear()
        if not entries:
            self.log_output.setHtml('<span style="color:#7f8793;">No runtime log entries saved yet.</span>')
            return
        for entry in entries[-220:]:
            self.log_output.append(self._render_log_html(entry))

    def append_log_entry(self, entry: dict):
        if not entry:
            return
        if "No runtime log entries saved yet." in self.log_output.toPlainText():
            self.log_output.clear()
        self.log_output.append(self._render_log_html(entry))

    def append_log(self, text: str, level: str = "info"):
        self.append_log_entry({"time": "", "level": level, "category": "RUNTIME", "subsystem": "Runtime", "event_code": "RUNTIME_INFO", "message": text, "summary": text})

    def update_preview(
        self,
        ping: str,
        spec: str,
        rolled: str,
        ocr_text: str = "current spec read will appear here",
        domain: str = "specs",
        passive: str = "",
    ):
        ping_line = f"{ping.strip()}\n" if ping and ping.strip() else ""
        preview_domain = "powers" if str(domain or "").strip().lower() == "powers" else "specs"
        title = "Power Roll Found" if preview_domain == "powers" else "God Roll Found"
        intro = (
            "A kept Power roll matched the active target rules."
            if preview_domain == "powers"
            else "A kept roll matched the active target rules."
        )
        label = "Power" if preview_domain == "powers" else "Trait"
        passive_line = f"Passive: {passive.strip() or 'unknown'}\n" if preview_domain == "powers" else ""
        why_kept = (
            "configured power target thresholds were met"
            if preview_domain == "powers"
            else "configured target thresholds were met"
        )
        self.preview.setPlainText(
            f"{ping_line}"
            f"{APP_DISPLAY_NAME} | {title}\n"
            f"----------------------------------------\n"
            f"{intro}\n\n"
            f"{label}: {spec or 'Unknown'}\n"
            f"Result: Kept\n"
            f"Rolled: {rolled or 'Waiting for a kept roll'}\n"
            f"{passive_line}"
            f"Why kept: {why_kept}\n\n"
            f"OCR Read\n"
            f"{(ocr_text or 'current spec read will appear here')[:220]}"
        )

    def update_decision_chain(self, text: str):
        self.decision_chain.setPlainText(text or "No decisions recorded yet.")
        parsed = {}
        for line in (text or "").splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                parsed[key.strip().lower()] = value.strip()
        for key, label_key in (
            ("classification", "classification"),
            ("trait", "trait"),
            ("ocr", "ocr"),
            ("recovery", "recovery"),
            ("popup", "popup"),
            ("shards", "shards"),
        ):
            self.debug_fields[key].setText(parsed.get(label_key, "-"))
