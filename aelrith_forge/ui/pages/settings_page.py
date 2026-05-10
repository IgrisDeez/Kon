from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...backend.bot import DEFAULT_CONFIG
from ...backend.controller import format_region
from ..widgets.cards import Card
from ..widgets.numeric import FocusWheelDoubleSpinBox, FocusWheelSpinBox


class SettingsPage(QWidget):
    FORM_LABEL_WIDTH = 168

    LOCKED_AUTO_VERIFY_DELAY = float(DEFAULT_CONFIG["AUTO_VERIFY_DELAY"])
    LOCKED_AUTO_VERIFY_POLLS = int(DEFAULT_CONFIG["AUTO_VERIFY_POLLS"])
    LOCKED_AUTO_VERIFY_POLL_DELAY = float(DEFAULT_CONFIG["AUTO_VERIFY_POLL_DELAY"])

    applyRequested = Signal()
    resetRequested = Signal()
    testWebhookRequested = Signal()
    pickShardRegionRequested = Signal()
    previewShardRequested = Signal()
    pickPowerShardRegionRequested = Signal()
    previewPowerShardRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        root.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(self._build_ocr_section())
        layout.addWidget(self._build_runtime_section())
        layout.addWidget(self._build_webhook_section())
        layout.addWidget(self._build_ui_section())

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.reset_button = QPushButton("Reset Settings")
        self.reset_button.setProperty("danger", True)
        self.reset_button.setMinimumWidth(132)
        self.reset_button.clicked.connect(self.resetRequested)
        action_row.addWidget(self.reset_button)
        action_row.addStretch(1)
        self.apply_button = QPushButton("Apply Settings")
        self.apply_button.setProperty("primary", True)
        self.apply_button.setMinimumWidth(132)
        self.apply_button.clicked.connect(self.applyRequested)
        action_row.addWidget(self.apply_button)
        layout.addLayout(action_row)
        layout.addStretch(1)

    def _build_ocr_section(self) -> Card:
        card = Card("OCR Settings")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, self.FORM_LABEL_WIDTH)
        grid.setColumnStretch(1, 1)
        card.layout.addLayout(grid)

        self.tesseract_edit = QLineEdit()
        self.popup_region_edit = QLineEdit()
        self.protected_region_edit = QLineEdit()
        self.passive_shard_region_edit = QLineEdit()
        self.power_shard_region_edit = QLineEdit()
        self.passive_shard_region_edit.setPlaceholderText("x,y,w,h or 0,0,0,0")
        self.power_shard_region_edit.setPlaceholderText("x,y,w,h or 0,0,0,0")
        self.pick_shard_region_button = QPushButton("Pick Shards")
        self.pick_shard_region_button.setProperty("utility", True)
        self.preview_shard_button = QPushButton("Preview Shards")
        self.preview_shard_button.setProperty("utility", True)
        self.pick_power_shard_region_button = QPushButton("Pick Power Shards")
        self.pick_power_shard_region_button.setProperty("utility", True)
        self.preview_power_shard_button = QPushButton("Preview Power Shards")
        self.preview_power_shard_button.setProperty("utility", True)
        self.stop_on_empty_shards_check = QCheckBox("Stop on empty shards")
        self.stop_on_empty_shards_check.setToolTip("Stop the run if passive shard OCR reads empty.")
        self.stop_on_empty_power_shards_check = QCheckBox("Stop on empty power shards")
        self.stop_on_empty_power_shards_check.setToolTip("Stop the run if Power shard OCR reads empty.")
        self.pick_shard_region_button.clicked.connect(self.pickShardRegionRequested)
        self.preview_shard_button.clicked.connect(self.previewShardRequested)
        self.pick_power_shard_region_button.clicked.connect(self.pickPowerShardRegionRequested)
        self.preview_power_shard_button.clicked.connect(self.previewPowerShardRequested)

        self._add_row(grid, 0, "Tesseract path", self.tesseract_edit)
        self._add_row(grid, 1, "Popup region", self.popup_region_edit)
        self._add_row(grid, 2, "Protected banner region", self.protected_region_edit)
        self._add_point_row(
            grid,
            3,
            "Passive shard region",
            self.passive_shard_region_edit,
            self.pick_shard_region_button,
            self.preview_shard_button,
        )
        self._add_point_row(
            grid,
            4,
            "Power shard region",
            self.power_shard_region_edit,
            self.pick_power_shard_region_button,
            self.preview_power_shard_button,
        )
        grid.addWidget(self.stop_on_empty_shards_check, 5, 0, 1, 2)
        grid.addWidget(self.stop_on_empty_power_shards_check, 6, 0, 1, 2)
        return card

    def _build_runtime_section(self) -> Card:
        card = Card("Global Runtime Behavior")
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, self.FORM_LABEL_WIDTH)
        grid.setColumnStretch(1, 1)
        card.layout.addLayout(grid)

        self.loop_delay_spin = self._double_spin(0.01, 5.0, " s", 0.01)
        self.stuck_timeout_spin = self._double_spin(0.5, 60.0, " s", 0.5)
        self.verify_delay_spin = self._double_spin(0.01, 5.0, " s", 0.01)
        self.verify_polls_spin = FocusWheelSpinBox()
        self.verify_polls_spin.setRange(1, 30)
        self.verify_poll_delay_spin = self._double_spin(0.01, 5.0, " s", 0.01)
        self._lock_auto_verify_controls()

        self._add_row(grid, 0, "Loop delay", self.loop_delay_spin)
        self._add_row(grid, 1, "Stuck timeout", self.stuck_timeout_spin)
        self._add_row(grid, 2, "Auto verify delay", self.verify_delay_spin)
        self._add_row(grid, 3, "Auto verify polls", self.verify_polls_spin)
        self._add_row(grid, 4, "Auto verify poll delay", self.verify_poll_delay_spin)
        return card

    def _build_webhook_section(self) -> Card:
        card = Card("Webhook Settings")
        card.setProperty("secondaryCard", True)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, self.FORM_LABEL_WIDTH)
        grid.setColumnStretch(1, 1)
        card.layout.addLayout(grid)
        self.webhook_edit = QLineEdit()
        self.webhook_edit.setPlaceholderText("Discord webhook URL")
        self.webhook_edit.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.webhook_edit.setToolTip("Webhook URL is hidden until you edit the field.")
        self.test_webhook_button = QPushButton("Test Webhook")
        self.test_webhook_button.setProperty("utility", True)
        self.test_webhook_button.clicked.connect(self.testWebhookRequested)
        self.player_ping_edit = QLineEdit()
        self.player_ping_edit.setPlaceholderText("@user, role mention, or blank")
        self.passive_alerts_check = QCheckBox("Passive shard alerts")
        self.passive_alerts_check.setToolTip("Send the passive shard count when it changes.")
        self.passive_interval_spin = FocusWheelSpinBox()
        self.passive_interval_spin.setRange(1, 240)
        self.passive_interval_spin.setSuffix(" min")
        self.power_alerts_check = QCheckBox("Power shard alerts")
        self.power_alerts_check.setToolTip("Send the Power shard count when it changes.")
        self.power_interval_spin = FocusWheelSpinBox()
        self.power_interval_spin.setRange(1, 240)
        self.power_interval_spin.setSuffix(" min")
        self.power_low_threshold_spin = FocusWheelSpinBox()
        self.power_low_threshold_spin.setRange(0, 99999999)
        self.power_very_low_threshold_spin = FocusWheelSpinBox()
        self.power_very_low_threshold_spin.setRange(0, 99999999)
        self.power_critical_threshold_spin = FocusWheelSpinBox()
        self.power_critical_threshold_spin.setRange(0, 99999999)
        self.power_empty_threshold_spin = FocusWheelSpinBox()
        self.power_empty_threshold_spin.setRange(0, 99999999)
        self.power_alert_cooldown_spin = FocusWheelSpinBox()
        self.power_alert_cooldown_spin.setRange(1, 1440)
        self.power_alert_cooldown_spin.setSuffix(" min")
        self.live_status_check = QCheckBox("Live status message")
        self.live_status_check.setToolTip("Maintain one live run status message.")
        self.status_interval_spin = FocusWheelSpinBox()
        self.status_interval_spin.setRange(1, 240)
        self.status_interval_spin.setSuffix(" min")
        self.failure_screenshots_check = QCheckBox("Failure screenshots")
        self.failure_screenshots_check.setToolTip("Attach screenshots to important failure alerts.")
        self.popup_screenshot_check = QCheckBox("Popup-stuck screenshot")
        self.popup_screenshot_check.setToolTip("Capture when the reroll popup stays stuck.")
        self.macro_stop_screenshot_check = QCheckBox("Macro-stop screenshot")
        self.macro_stop_screenshot_check.setToolTip("Capture when the macro stops unexpectedly.")
        self._add_row(grid, 0, "Webhook URL", self.webhook_edit)
        grid.addWidget(self.test_webhook_button, 0, 2)
        self._add_row(grid, 1, "Player Ping", self.player_ping_edit)
        grid.addWidget(self.passive_alerts_check, 2, 0, 1, 2)
        self._add_row(grid, 3, "Shard report interval", self.passive_interval_spin)
        grid.addWidget(self.power_alerts_check, 4, 0, 1, 2)
        self._add_row(grid, 5, "Power shard interval", self.power_interval_spin)
        self._add_row(grid, 6, "Power low threshold", self.power_low_threshold_spin)
        self._add_row(grid, 7, "Power very low threshold", self.power_very_low_threshold_spin)
        self._add_row(grid, 8, "Power critical threshold", self.power_critical_threshold_spin)
        self._add_row(grid, 9, "Power empty threshold", self.power_empty_threshold_spin)
        self._add_row(grid, 10, "Power alert cooldown", self.power_alert_cooldown_spin)
        grid.addWidget(self.live_status_check, 11, 0, 1, 2)
        self._add_row(grid, 12, "Status update interval", self.status_interval_spin)
        grid.addWidget(self.failure_screenshots_check, 13, 0, 1, 2)
        grid.addWidget(self.popup_screenshot_check, 14, 0, 1, 2)
        grid.addWidget(self.macro_stop_screenshot_check, 15, 0, 1, 2)
        return card

    def _build_ui_section(self) -> Card:
        card = Card("UI Settings")
        card.setProperty("secondaryCard", True)
        card.layout.setSpacing(5)
        self.compact_tables_check = QCheckBox("Compact table rows")
        self.show_timer_check = QCheckBox("Show session timer")
        self.clean_debug_artifacts_check = QCheckBox("Clean debug artifacts on start")
        self.auto_debug_snapshots_check = QCheckBox("Auto diagnostic snapshots")
        self.auto_debug_snapshots_check.setToolTip("Capture diagnostic snapshots on serious failures.")
        self.debug_snapshot_retention_spin = FocusWheelSpinBox()
        self.debug_snapshot_retention_spin.setRange(1, 50)
        self.debug_snapshot_retention_spin.setSuffix(" snapshots")
        card.layout.addWidget(self.compact_tables_check)
        card.layout.addWidget(self.show_timer_check)
        card.layout.addWidget(self.clean_debug_artifacts_check)
        card.layout.addWidget(self.auto_debug_snapshots_check)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, self.FORM_LABEL_WIDTH)
        grid.setColumnStretch(1, 1)
        card.layout.addLayout(grid)
        self._add_row(grid, 0, "Snapshot retention", self.debug_snapshot_retention_spin)
        return card

    def _lock_auto_verify_controls(self):
        for widget, value in (
            (self.verify_delay_spin, self.LOCKED_AUTO_VERIFY_DELAY),
            (self.verify_polls_spin, self.LOCKED_AUTO_VERIFY_POLLS),
            (self.verify_poll_delay_spin, self.LOCKED_AUTO_VERIFY_POLL_DELAY),
        ):
            widget.setValue(value)
            widget.setEnabled(False)
            widget.setToolTip("Locked to the current stable engine defaults.")

    def _add_row(self, grid: QGridLayout, row: int, title: str, widget):
        from PySide6.QtWidgets import QLabel

        title_label = QLabel(title)
        title_label.setProperty("role", "muted")
        title_label.setFixedWidth(self.FORM_LABEL_WIDTH)
        grid.addWidget(title_label, row, 0)
        grid.addWidget(widget, row, 1)

    def _add_point_row(self, grid: QGridLayout, row: int, title: str, widget, *buttons):
        from PySide6.QtWidgets import QLabel

        title_label = QLabel(title)
        title_label.setProperty("role", "muted")
        title_label.setFixedWidth(self.FORM_LABEL_WIDTH)
        widget.setPlaceholderText("x,y,w,h")
        grid.addWidget(title_label, row, 0)
        grid.addWidget(widget, row, 1)
        button_col = 2
        for button in buttons:
            grid.addWidget(button, row, button_col)
            button_col += 1

    def _double_spin(self, minimum: float, maximum: float, suffix: str, step: float) -> FocusWheelDoubleSpinBox:
        spin = FocusWheelDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        spin.setSuffix(suffix)
        return spin

    def collect_settings(self) -> dict:
        return {
            "tesseract_cmd": self.tesseract_edit.text().strip(),
            "popup_region": self.popup_region_edit.text().strip(),
            "protected_region": self.protected_region_edit.text().strip(),
            "passive_shard_region": self.passive_shard_region_edit.text().strip(),
            "power_shard_region": self.power_shard_region_edit.text().strip(),
            "webhook_url": self.webhook_edit.text().strip(),
            "player_ping": self.player_ping_edit.text().strip(),
            "passive_shard_alerts": self.passive_alerts_check.isChecked(),
            "passive_shard_report_interval": self.passive_interval_spin.value() * 60,
            "stop_on_empty_passive_shards": self.stop_on_empty_shards_check.isChecked(),
            "power_shard_alerts": self.power_alerts_check.isChecked(),
            "power_shard_report_interval": self.power_interval_spin.value() * 60,
            "power_shard_low_threshold": self.power_low_threshold_spin.value(),
            "power_shard_very_low_threshold": self.power_very_low_threshold_spin.value(),
            "power_shard_critical_threshold": self.power_critical_threshold_spin.value(),
            "power_shard_empty_threshold": self.power_empty_threshold_spin.value(),
            "power_shard_alert_cooldown": self.power_alert_cooldown_spin.value() * 60,
            "stop_on_empty_power_shards": self.stop_on_empty_power_shards_check.isChecked(),
            "webhook_live_status_enabled": self.live_status_check.isChecked(),
            "webhook_status_update_interval": self.status_interval_spin.value() * 60,
            "webhook_failure_screenshots": self.failure_screenshots_check.isChecked(),
            "webhook_screenshot_on_popup_stuck": self.popup_screenshot_check.isChecked(),
            "webhook_screenshot_on_macro_stop": self.macro_stop_screenshot_check.isChecked(),
            "loop_delay": self.loop_delay_spin.value(),
            "stuck_timeout": self.stuck_timeout_spin.value(),
            "auto_verify_delay": self.verify_delay_spin.value(),
            "auto_verify_polls": self.verify_polls_spin.value(),
            "auto_verify_poll_delay": self.verify_poll_delay_spin.value(),
            "clean_debug_artifacts_on_start": self.clean_debug_artifacts_check.isChecked(),
            "auto_capture_debug_snapshots": self.auto_debug_snapshots_check.isChecked(),
            "debug_snapshot_retention_count": self.debug_snapshot_retention_spin.value(),
            "ui": {
                "compact_tables": self.compact_tables_check.isChecked(),
                "show_session_timer": self.show_timer_check.isChecked(),
            },
        }

    def load_settings(self, settings: dict):
        cfg = DEFAULT_CONFIG
        self.tesseract_edit.setText(str(settings.get("tesseract_cmd", cfg["TESSERACT_CMD"])))
        self.popup_region_edit.setText(str(settings.get("popup_region", format_region(cfg["POPUP_REGION"]))))
        self.protected_region_edit.setText(str(settings.get("protected_region", format_region(cfg["PROTECTED_REGION"]))))
        self.passive_shard_region_edit.setText(
            str(settings.get("passive_shard_region", format_region(cfg["PASSIVE_SHARD_REGION"])))
        )
        self.power_shard_region_edit.setText(
            str(settings.get("power_shard_region", format_region(cfg["POWER_SHARD_REGION"])))
        )
        self.stop_on_empty_shards_check.setChecked(
            bool(settings.get("stop_on_empty_passive_shards", cfg["STOP_ON_EMPTY_PASSIVE_SHARDS"]))
        )
        self.stop_on_empty_power_shards_check.setChecked(
            bool(settings.get("stop_on_empty_power_shards", cfg["STOP_ON_EMPTY_POWER_SHARDS"]))
        )
        self.webhook_edit.setText(str(settings.get("webhook_url", "")))
        self.player_ping_edit.setText(str(settings.get("player_ping", "")))
        self.passive_alerts_check.setChecked(bool(settings.get("passive_shard_alerts", cfg["PASSIVE_SHARD_ALERTS"])))
        self.passive_interval_spin.setValue(
            max(1, int(settings.get("passive_shard_report_interval", cfg["PASSIVE_SHARD_REPORT_INTERVAL"])) // 60)
        )
        self.power_alerts_check.setChecked(bool(settings.get("power_shard_alerts", cfg["POWER_SHARD_ALERTS"])))
        self.power_interval_spin.setValue(
            max(1, int(settings.get("power_shard_report_interval", cfg["POWER_SHARD_REPORT_INTERVAL"])) // 60)
        )
        self.power_low_threshold_spin.setValue(
            int(settings.get("power_shard_low_threshold", cfg["POWER_SHARD_LOW_THRESHOLD"]))
        )
        self.power_very_low_threshold_spin.setValue(
            int(settings.get("power_shard_very_low_threshold", cfg["POWER_SHARD_VERY_LOW_THRESHOLD"]))
        )
        self.power_critical_threshold_spin.setValue(
            int(settings.get("power_shard_critical_threshold", cfg["POWER_SHARD_CRITICAL_THRESHOLD"]))
        )
        self.power_empty_threshold_spin.setValue(
            int(settings.get("power_shard_empty_threshold", cfg["POWER_SHARD_EMPTY_THRESHOLD"]))
        )
        self.power_alert_cooldown_spin.setValue(
            max(1, int(settings.get("power_shard_alert_cooldown", cfg["POWER_SHARD_ALERT_COOLDOWN"])) // 60)
        )
        self.live_status_check.setChecked(
            bool(settings.get("webhook_live_status_enabled", cfg["WEBHOOK_LIVE_STATUS_ENABLED"]))
        )
        self.status_interval_spin.setValue(
            max(1, int(settings.get("webhook_status_update_interval", cfg["WEBHOOK_STATUS_UPDATE_INTERVAL"])) // 60)
        )
        self.failure_screenshots_check.setChecked(
            bool(settings.get("webhook_failure_screenshots", cfg["WEBHOOK_FAILURE_SCREENSHOTS"]))
        )
        self.popup_screenshot_check.setChecked(
            bool(settings.get("webhook_screenshot_on_popup_stuck", cfg["WEBHOOK_SCREENSHOT_ON_POPUP_STUCK"]))
        )
        self.macro_stop_screenshot_check.setChecked(
            bool(settings.get("webhook_screenshot_on_macro_stop", cfg["WEBHOOK_SCREENSHOT_ON_MACRO_STOP"]))
        )
        self.loop_delay_spin.setValue(float(settings.get("loop_delay", cfg["LOOP_DELAY"])))
        self.stuck_timeout_spin.setValue(float(settings.get("stuck_timeout", cfg["STUCK_TIMEOUT"])))
        self.verify_delay_spin.setValue(self.LOCKED_AUTO_VERIFY_DELAY)
        self.verify_polls_spin.setValue(self.LOCKED_AUTO_VERIFY_POLLS)
        self.verify_poll_delay_spin.setValue(self.LOCKED_AUTO_VERIFY_POLL_DELAY)

        ui = settings.get("ui") or {}
        self.compact_tables_check.setChecked(bool(ui.get("compact_tables", True)))
        self.show_timer_check.setChecked(bool(ui.get("show_session_timer", True)))
        self.clean_debug_artifacts_check.setChecked(
            bool(settings.get("clean_debug_artifacts_on_start", cfg["CLEAN_DEBUG_ARTIFACTS_ON_START"]))
        )
        self.auto_debug_snapshots_check.setChecked(
            bool(settings.get("auto_capture_debug_snapshots", cfg["AUTO_CAPTURE_DEBUG_SNAPSHOTS"]))
        )
        self.debug_snapshot_retention_spin.setValue(
            int(settings.get("debug_snapshot_retention_count", cfg["DEBUG_SNAPSHOT_RETENTION_COUNT"]))
        )

    def set_running(self, running: bool):
        for widget in (
            self.tesseract_edit,
            self.popup_region_edit,
            self.protected_region_edit,
            self.passive_shard_region_edit,
            self.power_shard_region_edit,
            self.stop_on_empty_shards_check,
            self.stop_on_empty_power_shards_check,
            self.pick_shard_region_button,
            self.preview_shard_button,
            self.pick_power_shard_region_button,
            self.preview_power_shard_button,
            self.loop_delay_spin,
            self.stuck_timeout_spin,
            self.verify_delay_spin,
            self.verify_polls_spin,
            self.verify_poll_delay_spin,
            self.webhook_edit,
            self.test_webhook_button,
            self.player_ping_edit,
            self.passive_alerts_check,
            self.passive_interval_spin,
            self.power_alerts_check,
            self.power_interval_spin,
            self.power_low_threshold_spin,
            self.power_very_low_threshold_spin,
            self.power_critical_threshold_spin,
            self.power_empty_threshold_spin,
            self.power_alert_cooldown_spin,
            self.live_status_check,
            self.status_interval_spin,
            self.failure_screenshots_check,
            self.popup_screenshot_check,
            self.macro_stop_screenshot_check,
            self.compact_tables_check,
            self.show_timer_check,
            self.clean_debug_artifacts_check,
            self.auto_debug_snapshots_check,
            self.debug_snapshot_retention_spin,
            self.reset_button,
            self.apply_button,
        ):
            widget.setEnabled(not running)
