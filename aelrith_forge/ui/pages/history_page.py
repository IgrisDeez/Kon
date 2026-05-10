from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTabWidget, QVBoxLayout, QWidget

from ..widgets.cards import Card
from ..widgets.tables import add_row, fill_table, make_table, selected_row_text


class HistoryPage(QWidget):
    copyRequested = Signal()
    exportRequested = Signal(str)
    openFolderRequested = Signal()
    clearRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.copy_button = QPushButton("Copy selected")
        self.export_button = QPushButton("Export")
        self.open_folder_button = QPushButton("Open screenshot folder")
        self.clear_button = QPushButton("Clear history")
        self.clear_button.setProperty("danger", True)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.export_button)
        actions.addWidget(self.open_folder_button)
        actions.addWidget(self.clear_button)
        layout.addLayout(actions)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.god_table = make_table(
            ["Time", "Spec", "Full rolled stats", "Screenshot path", "Webhook sent"],
            min_rows=10,
        )
        self.near_table = make_table(
            ["Time", "Spec", "Rolled stats", "Failed condition", "Miss distance", "Screenshot saved"],
            min_rows=10,
        )

        self.tabs.addTab(self._wrap_table(self.god_table), "God Rolls")
        self.tabs.addTab(self._wrap_table(self.near_table), "Near-Misses")

        self.copy_button.clicked.connect(self.copyRequested)
        self.export_button.clicked.connect(lambda: self.exportRequested.emit(self.current_kind()))
        self.open_folder_button.clicked.connect(self.openFolderRequested)
        self.clear_button.clicked.connect(lambda: self.clearRequested.emit(self.current_kind()))

    def _wrap_table(self, table):
        card = Card()
        card.layout.addWidget(table)
        return card

    def current_kind(self) -> str:
        return "god" if self.tabs.currentIndex() == 0 else "near"

    def current_table(self):
        return self.god_table if self.current_kind() == "god" else self.near_table

    def selected_text(self) -> str:
        return selected_row_text(self.current_table())

    def set_history(self, god_rolls: list, near_misses: list):
        fill_table(
            self.god_table,
            [
                [
                    entry.time,
                    entry.spec,
                    entry.rolled,
                    entry.screenshot_path,
                    "Yes" if entry.webhook_sent else "No",
                ]
                for entry in god_rolls
            ],
        )
        fill_table(
            self.near_table,
            [
                [
                    entry.time,
                    entry.spec,
                    entry.stats,
                    entry.failed_condition,
                    entry.miss_distance,
                    entry.screenshot_saved,
                ]
                for entry in near_misses
            ],
        )

    def add_god_roll(self, entry):
        add_row(
            self.god_table,
            [entry.time, entry.spec, entry.rolled, entry.screenshot_path, "Yes" if entry.webhook_sent else "No"],
            top=True,
        )

    def add_near_miss(self, entry):
        add_row(
            self.near_table,
            [
                entry.time,
                entry.spec,
                entry.stats,
                entry.failed_condition,
                entry.miss_distance,
                entry.screenshot_saved,
            ],
            top=True,
        )
