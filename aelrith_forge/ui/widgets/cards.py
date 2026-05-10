from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget


def label(text: str, role: str | None = None) -> QLabel:
    widget = QLabel(text)
    if role:
        widget.setProperty("role", role)
    return widget


class Card(QFrame):
    def __init__(self, title: str | None = None, parent=None, near: bool = False):
        super().__init__(parent)
        self.setProperty("card", True)
        if near:
            self.setProperty("near", True)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 12, 14, 14)
        self.layout.setSpacing(10)
        if title:
            self.title_label = label(title, "section")
            self.layout.addWidget(self.title_label)


class StatusStrip(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("strip", True)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(12, 6, 12, 6)
        self.layout.setSpacing(12)
        self.layout.addStretch(1)

    def add_metric(self, name: str, value: str = "-") -> QLabel:
        group = QWidget()
        group.setProperty("container", True)
        group.setProperty("statusMetric", True)
        row = QHBoxLayout(group)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        name_label = label(f"{name}", "statusLabel")
        value_label = label(value, "statusMetricValue")
        row.addWidget(name_label)
        row.addWidget(value_label)
        self.layout.insertWidget(self.layout.count() - 1, group)
        return value_label


class CollapsibleCard(QFrame):
    def __init__(self, title: str, parent=None, expanded: bool = True):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setProperty("collapsibleCard", True)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(10, 7, 10, 8)
        self.outer.setSpacing(6)

        self.button = QToolButton()
        self.button.setProperty("collapsibleHeader", True)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setText(title)
        self.button.setCheckable(True)
        self.button.setChecked(expanded)
        self.button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.button.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.button.clicked.connect(self._toggle)
        self.outer.addWidget(self.button)

        self.content = QWidget()
        self.content.setProperty("container", True)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(2, 3, 2, 0)
        self.content_layout.setSpacing(5)
        self.outer.addWidget(self.content)
        self.content.setVisible(expanded)

    def _toggle(self, checked: bool):
        self.button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.content.setVisible(checked)


class Pill(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setProperty("badge", True)
        self.setProperty("pill", True)
        self.setAlignment(Qt.AlignCenter)
