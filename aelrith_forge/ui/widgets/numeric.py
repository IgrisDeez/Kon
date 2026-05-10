from __future__ import annotations

from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QSlider, QSpinBox


def _widget_or_child_has_focus(widget) -> bool:
    focused = QApplication.focusWidget()
    return focused is widget or (focused is not None and widget.isAncestorOf(focused))


class FocusWheelSpinBox(QSpinBox):
    def wheelEvent(self, event):
        if _widget_or_child_has_focus(self):
            super().wheelEvent(event)
        else:
            event.ignore()


class FocusWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event):
        if _widget_or_child_has_focus(self):
            super().wheelEvent(event)
        else:
            event.ignore()


class FocusWheelSlider(QSlider):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
