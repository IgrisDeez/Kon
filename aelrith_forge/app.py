from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from . import APP_DISPLAY_NAME, APP_VERSION
from .backend.controller import BotController
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Kon")
    apply_theme(app)

    controller = BotController()
    window = MainWindow(controller)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
