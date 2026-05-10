from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QGridLayout,
    QLabel,
    QSizePolicy,
    QStyle,
    QStyleOptionSlider,
    QVBoxLayout,
    QWidget,
)

from .numeric import FocusWheelDoubleSpinBox, FocusWheelSlider


class SmoothSlider(FocusWheelSlider):
    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.setTracking(True)
        self.setMouseTracking(True)

    def _value_from_position(self, x_pos: float) -> int:
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.CC_Slider, option, QStyle.SC_SliderHandle, self)
        span = max(1, groove.width() - handle.width())
        position = int(round(x_pos - groove.x() - (handle.width() / 2)))
        position = max(0, min(position, span))
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), position, span)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setSliderDown(True)
            self.setValue(self._value_from_position(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self.setValue(self._value_from_position(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)


class StatRangeRow(QWidget):
    rangeChanged = Signal(str, float, float)

    def __init__(self, stat_name: str, cap: float, low: float, high: float, parent=None):
        super().__init__(parent)
        self.stat_name = stat_name
        self.cap = float(cap)
        self._syncing = False
        self.scale = 20
        self.setProperty("statRow", True)

        layout = QGridLayout(self)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(5)

        left_box = QWidget()
        left_box.setProperty("container", True)
        left_layout = QVBoxLayout(left_box)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)
        name = QLabel(stat_name)
        name.setMinimumWidth(112)
        name.setProperty("role", "statusValue")
        cap_label = QLabel(f"Cap {self.cap:.1f}")
        cap_label.setProperty("role", "tiny")
        left_layout.addWidget(name)
        left_layout.addWidget(cap_label)

        threshold_box = QWidget()
        threshold_box.setProperty("container", True)
        threshold_layout = QVBoxLayout(threshold_box)
        threshold_layout.setContentsMargins(0, 0, 0, 0)
        threshold_layout.setSpacing(3)
        threshold_label = QLabel("Threshold")
        threshold_label.setProperty("role", "muted")
        self.threshold_spin = self._make_spin()
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_spin, alignment=Qt.AlignLeft)

        auto_label = QLabel("Max = cap")
        auto_label.setProperty("role", "tiny")
        auto_label.setAlignment(Qt.AlignRight | Qt.AlignTop)

        self.threshold_slider = self._make_slider()

        layout.addWidget(left_box, 0, 0, 2, 1)
        layout.addWidget(threshold_box, 0, 1)
        layout.addWidget(auto_label, 0, 2, alignment=Qt.AlignRight | Qt.AlignTop)
        layout.addWidget(self.threshold_slider, 1, 1, 1, 2)
        layout.setColumnStretch(2, 1)

        self.threshold_spin.valueChanged.connect(self._from_spin)
        self.threshold_slider.valueChanged.connect(self._from_slider)
        self.set_range(low, high)

    def _make_spin(self) -> FocusWheelDoubleSpinBox:
        spin = FocusWheelDoubleSpinBox()
        spin.setDecimals(2)
        spin.setSingleStep(0.05)
        spin.setRange(0.0, self.cap)
        spin.setButtonSymbols(QAbstractSpinBox.PlusMinus)
        spin.setAlignment(Qt.AlignRight)
        spin.setFixedWidth(78)
        return spin

    def _make_slider(self) -> SmoothSlider:
        slider = SmoothSlider()
        slider.setRange(0, int(round(self.cap * self.scale)))
        slider.setSingleStep(1)
        slider.setPageStep(2)
        slider.setMinimumWidth(220)
        slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return slider

    def values(self) -> tuple[float, float]:
        threshold = self.threshold_spin.value()
        return threshold, self.cap

    def set_range(self, low: float, high: float):
        threshold = max(0.0, min(float(low), self.cap))
        self._set_threshold(threshold, emit=False)

    def _set_threshold(self, threshold: float, emit: bool = True):
        if self._syncing:
            return
        threshold = round(float(threshold), 2)
        self._syncing = True
        self.threshold_spin.setValue(threshold)
        self.threshold_slider.setValue(int(round(threshold * self.scale)))
        self._syncing = False
        if emit:
            self.rangeChanged.emit(self.stat_name, threshold, self.cap)

    def _from_spin(self, value: float):
        if self._syncing:
            return
        self._set_threshold(value)

    def _from_slider(self, raw: int):
        if self._syncing:
            return
        self._set_threshold(raw / self.scale)
