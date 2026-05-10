from __future__ import annotations

from PySide6.QtCore import Signal

from .cards import CollapsibleCard
from .stat_row import StatRangeRow


class SpecCard(CollapsibleCard):
    rangesChanged = Signal()

    def __init__(self, title: str, labels: list[str], caps: list[float], ranges, parent=None, expanded: bool = False):
        super().__init__(title, parent=parent, expanded=expanded)
        self.rows: list[StatRangeRow] = []
        for label, cap, (low, high) in zip(labels, caps, ranges):
            row = StatRangeRow(label, cap, low, high)
            row.rangeChanged.connect(lambda *_: self.rangesChanged.emit())
            self.content_layout.addWidget(row)
            self.rows.append(row)

    def get_ranges(self) -> list[tuple[float, float]]:
        return [row.values() for row in self.rows]

    def set_ranges(self, ranges):
        for row, (low, high) in zip(self.rows, ranges):
            row.set_range(low, high)
        self.rangesChanged.emit()
