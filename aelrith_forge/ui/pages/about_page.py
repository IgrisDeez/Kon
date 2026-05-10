from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ... import APP_DISPLAY_NAME
from ..widgets.cards import Card


class AboutPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        card = Card()
        title = QLabel(APP_DISPLAY_NAME)
        title.setProperty("role", "title")
        credit = QLabel("Copyright © 2026 Igers. All rights reserved.")
        credit.setProperty("role", "muted")
        usage = QLabel("Proprietary software. Unauthorized copying, modification, redistribution, or derivative use is prohibited without written permission from Igers.")
        usage.setWordWrap(True)
        usage.setProperty("role", "tiny")
        card.layout.addWidget(title)
        card.layout.addWidget(credit)
        card.layout.addWidget(usage)

        layout.addWidget(card)
        layout.addStretch(1)
