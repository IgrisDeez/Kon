from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import APP_BRAND_NAME, APP_CONSOLE_LABEL, APP_DISPLAY_NAME, APP_VERSION
from ..backend.bot import STAT_CAPS, STAT_LABELS
from ..backend.powers import POWER_DEFAULT_RULES, SUPPORTED_POWER_DEFINITIONS
from ..backend.controller import BotController, format_point, format_region
from .pages.logs_page import LogsPage
from .pages.main_page import MainPage
from .pages.powers_page import PowersPage
from .pages.settings_page import SettingsPage
from .pages.targets_page import TargetsPage
from .pages.tools_page import ToolsPage
from .widgets.cards import StatusStrip, label


class MainWindow(QMainWindow):
    def __init__(self, controller: BotController):
        super().__init__()
        self.controller = controller
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(940, 640)
        self.setMinimumSize(780, 540)
        self._session_started_at: float | None = None

        self._build_shell()
        self._connect_signals()
        self._load_settings(self.controller.settings)
        self._set_history(self.controller.god_rolls, self.controller.near_misses)
        self._load_existing_logs_into_ui()

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick_timer)

    def _build_shell(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        main_area = QWidget()
        main_layout = QVBoxLayout(main_area)
        main_layout.setContentsMargins(14, 12, 14, 14)
        main_layout.setSpacing(10)

        chrome = QFrame()
        chrome.setObjectName("TopChrome")
        chrome_layout = QHBoxLayout(chrome)
        chrome_layout.setContentsMargins(18, 11, 18, 11)
        chrome_layout.setSpacing(14)
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(2)
        app_title = label(APP_BRAND_NAME, "heroTitle")
        app_console = label(APP_CONSOLE_LABEL, "subtitle")
        app_version = label(APP_VERSION, "tiny")
        title_box.addWidget(app_title)
        title_box.addWidget(app_console)
        title_box.addWidget(app_version)
        chrome_layout.addLayout(title_box)
        chrome_layout.addStretch(1)
        self.preview_capture_notice = QLabel("Preview restored")
        self.preview_capture_notice.setProperty("previewNotice", True)
        self.preview_capture_notice.setVisible(False)
        chrome_layout.addWidget(self.preview_capture_notice)
        self.top_status_badge = QLabel("Idle")
        self.top_status_badge.setProperty("badge", True)
        self.top_status_badge.setProperty("statusTone", "header")
        self.top_status_badge.setProperty("stateTone", "idle")
        chrome_layout.addWidget(self.top_status_badge)
        main_layout.addWidget(chrome)

        self.status_strip = StatusStrip()
        self.status_value = self.status_strip.add_metric("Status", "Idle")
        self.preset_value = self.status_strip.add_metric("Preset", "Default")
        self.ocr_value = self.status_strip.add_metric("OCR Region", "Set")
        self.webhook_value = self.status_strip.add_metric("Webhook", "Missing")
        self.passive_shards_value = self.status_strip.add_metric("Passive Shards", "-")
        self.power_shards_value = self.status_strip.add_metric("Power Shards", "-")
        self.timer_value = self.status_strip.add_metric("Session", "00:00")
        main_layout.addWidget(self.status_strip)

        self.stack = QStackedWidget()
        self.main_page = MainPage()
        self.logs_page = LogsPage()
        self.settings_page = SettingsPage()
        self.target_page = TargetsPage()
        self.powers_page = PowersPage()
        self.tools_page = ToolsPage()
        for page in (self.main_page, self.target_page, self.powers_page, self.settings_page, self.logs_page, self.tools_page):
            self.stack.addWidget(page)
        main_layout.addWidget(self.stack, 1)
        root_layout.addWidget(main_area, 1)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(130)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 16, 12, 15)
        layout.setSpacing(9)

        logo_shell = QFrame()
        logo_shell.setObjectName("SidebarLogoShell")
        logo_layout = QVBoxLayout(logo_shell)
        logo_layout.setContentsMargins(0, 3, 0, 7)
        logo_layout.setSpacing(0)

        self.sidebar_logo = QLabel()
        self.sidebar_logo.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.sidebar_logo.setProperty("role", "logo")
        self.sidebar_logo.setMinimumHeight(68)
        logo_path = Path(__file__).resolve().parent / "assets" / "af_logo.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path)).scaled(62, 62, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.sidebar_logo.setPixmap(pixmap)
        else:
            self.sidebar_logo.setText("K.")
            self.sidebar_logo.setProperty("role", "title")
        logo_layout.addWidget(self.sidebar_logo)
        layout.addWidget(logo_shell)
        layout.addSpacing(6)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons = []
        for index, name in enumerate(["Main", "Specs", "Powers", "Settings", "Debug", "Tools"]):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setProperty("nav", True)
            button.clicked.connect(lambda checked=False, i=index: self.stack.setCurrentIndex(i))
            self.nav_group.addButton(button)
            self.nav_buttons.append(button)
            layout.addWidget(button)
        self.nav_buttons[0].setChecked(True)
        layout.addStretch(1)

        footer = QLabel(f"Copyright © 2026 Igers. All rights reserved.\n{APP_CONSOLE_LABEL} · {APP_VERSION}")
        footer.setProperty("container", True)
        footer.setProperty("role", "tiny")
        footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        layout.addWidget(footer)
        return sidebar

    def _connect_signals(self):
        self.controller.status_changed.connect(self._set_status)
        self.controller.log_entry_added.connect(self.logs_page.append_log_entry)
        self.controller.log_entry_added.connect(self.main_page.append_log_entry)
        self.controller.log_entry_added.connect(lambda _entry: self._refresh_macro_health())
        self.controller.god_roll_added.connect(self._add_god_roll)
        self.controller.near_miss_added.connect(self._add_near_miss)
        self.controller.history_loaded.connect(self._set_history)
        self.controller.settings_changed.connect(self._load_settings)
        self.controller.runtime_changed.connect(self._set_running)
        self.controller.passive_shards_changed.connect(self._set_passive_shards)
        self.controller.power_shards_changed.connect(self._set_power_shards)
        self.controller.decision_chain_changed.connect(self.logs_page.update_decision_chain)
        self.controller.decision_chain_changed.connect(self.main_page.update_decision_chain)
        self.controller.decision_chain_changed.connect(lambda _text: self._refresh_macro_health())

        self.main_page.startSpecsRequested.connect(lambda: self.start_bot("specs"))
        self.main_page.startPowersRequested.connect(lambda: self.start_bot("powers"))
        self.main_page.stopRequested.connect(self.controller.stop)
        self.main_page.debugRequested.connect(lambda: self.stack.setCurrentWidget(self.logs_page))
        self.target_page.applyRequested.connect(self.apply_settings)
        self.target_page.loadPresetRequested.connect(self.load_preset)
        self.target_page.previewRequested.connect(self.preview_ocr)
        self.target_page.pickRegionRequested.connect(self.pick_region)
        self.target_page.pickPointRequested.connect(self.pick_specs_point)
        self.powers_page.applyRequested.connect(self.apply_settings)
        self.powers_page.previewRequested.connect(lambda: self.preview_ocr("powers"))
        self.powers_page.pickRegionRequested.connect(self.pick_region)
        self.powers_page.pickPointRequested.connect(self.pick_runtime_point)

        self.settings_page.applyRequested.connect(self.apply_settings)
        self.settings_page.resetRequested.connect(self.reset_settings)
        self.settings_page.testWebhookRequested.connect(self.test_webhook)
        self.settings_page.pickShardRegionRequested.connect(self.pick_passive_shard_region)
        self.settings_page.previewShardRequested.connect(self.preview_passive_shards)
        self.settings_page.pickPowerShardRegionRequested.connect(self.pick_power_shard_region)
        self.settings_page.previewPowerShardRequested.connect(self.preview_power_shards)

        self.tools_page.captureDebugRequested.connect(self.capture_debug_report)
        self.tools_page.captureScreenshotRequested.connect(self.capture_debug_screenshot)
        self.tools_page.exportLiveProofRequested.connect(self.export_live_proof_pack)
        self.tools_page.testPopupRequested.connect(self.test_popup_detection)
        self.tools_page.testClassificationRequested.connect(self.test_current_roll_classification)
        self.tools_page.previewRequested.connect(self.preview_ocr)
        self.tools_page.previewShardRequested.connect(self.preview_passive_shards)
        self.tools_page.previewPowerShardRequested.connect(self.preview_power_shards)
        self.tools_page.testWebhookRequested.connect(self.test_webhook)

    def _load_existing_logs_into_ui(self):
        existing = self.controller.recent_log_entries(260)
        self.logs_page.load_log_entries(existing)
        self.main_page.load_event_entries(existing)

    def _sync_line_edits(self, left, right):
        def push_to_right(text):
            if right.text() != text:
                right.setText(text)

        def push_to_left(text):
            if left.text() != text:
                left.setText(text)

        left.textChanged.connect(push_to_right)
        right.textChanged.connect(push_to_left)

    def compose_settings(self) -> dict:
        data = self.controller.normalize_settings(self.controller.settings)
        advanced = self.settings_page.collect_settings()
        targets = self.target_page.collect_target_settings()
        powers = self.powers_page.collect_power_settings()
        for key, value in advanced.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key].update(value)
            else:
                data[key] = value
        for key, value in targets.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key].update(value)
            else:
                data[key] = value
        for key, value in powers.items():
            if isinstance(value, dict) and isinstance(data.get(key), dict):
                data[key].update(value)
            else:
                data[key] = value
        return data

    def apply_settings(self, confirm: bool = True):
        if not self._ensure_idle("change settings"):
            return
        try:
            settings = self.compose_settings()
            summary_mode = self._apply_summary_mode(settings)
            if confirm and not self._confirm_apply(settings, summary_mode):
                return
            self.controller.apply_settings(settings)
            self._refresh_status_strip(settings)
            self.controller.add_log(f"Desired targets applied | {self._compact_target_summary(settings, summary_mode)}")
        except Exception as e:
            QMessageBox.warning(self, "Settings Error", str(e))

    def reset_settings(self):
        if not self._ensure_idle("reset settings"):
            return
        answer = QMessageBox.question(
            self,
            "Reset Settings",
            "Reset settings to clean defaults? A backup of the current settings file will be created first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            backup = self.controller.reset_settings()
            message = "Settings reset to clean defaults."
            if backup:
                message += f"\n\nBackup created:\n{backup}"
            QMessageBox.information(self, "Reset Settings", message)
        except Exception as e:
            QMessageBox.warning(self, "Reset Settings", str(e))

    def _minimize_after_start(self):
        if self.isMinimized():
            return
        self.showMinimized()
        QApplication.processEvents()

    def _settings_for_domain(self, roll_domain: str) -> dict:
        settings = self.compose_settings()
        settings["roll_domain"] = "powers" if str(roll_domain).strip().lower() == "powers" else "specs"
        return settings

    def start_bot(self, roll_domain: str = "specs"):
        try:
            self.controller.start(self._settings_for_domain(roll_domain))
        except Exception as e:
            QMessageBox.warning(self, "Start Error", str(e))
            return
        QTimer.singleShot(0, self._minimize_after_start)

    def test_webhook(self):
        if not self._ensure_idle("test the webhook"):
            return
        try:
            ok = self.controller.test_webhook(self.compose_settings())
        except Exception as e:
            QMessageBox.warning(self, "Webhook", str(e))
            return
        if ok:
            QMessageBox.information(self, "Webhook", "Webhook test sent successfully.")
        else:
            QMessageBox.warning(self, "Webhook", "Webhook test failed. Check the log.")

    def capture_debug_report(self):
        try:
            settings = None if self.controller.bot.running else self.compose_settings()
            path = self.controller.capture_debug_report(settings)
            QMessageBox.information(self, "Debug Report", f"Diagnostic snapshot saved:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Debug Report", str(e))

    def capture_debug_screenshot(self):
        try:
            path = self.controller.capture_current_screenshot()
            QMessageBox.information(self, "Debug Screenshot", f"Screenshot saved:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Debug Screenshot", str(e))

    def export_live_proof_pack(self):
        try:
            path = self.controller.export_live_proof_pack("manual")
            QMessageBox.information(self, "Live Proof Pack", f"Live proof pack exported:\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Live Proof Pack", str(e))

    def test_popup_detection(self, roll_domain: str | None = None):
        try:
            settings = None if self.controller.bot.running else self._settings_for_domain(roll_domain or self._current_preview_domain())
            active = self.controller.test_popup_detection(settings)
            QMessageBox.information(
                self,
                "Popup Detection",
                "Popup detected." if active else "Popup not detected. Details were written to the log.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Popup Detection", str(e))

    def test_current_roll_classification(self, roll_domain: str | None = None):
        try:
            settings = None if self.controller.bot.running else self._settings_for_domain(roll_domain or self._current_preview_domain())
            state, trait, summary, missing, near = self.controller.test_current_roll_classification(settings)
            message = (
                f"State: {state}\n"
                f"Trait: {trait or 'unknown'}\n"
                f"Near miss: {near}\n"
                f"Summary: {summary or '<empty>'}\n"
                f"Missing: {'; '.join(missing) if missing else 'none'}"
            )
            QMessageBox.information(self, "Current Roll Classification", message)
        except Exception as e:
            QMessageBox.warning(self, "Current Roll Classification", str(e))

    def load_preset(self, name: str):
        if not self._ensure_idle("load a preset"):
            return
        rules = self.controller.load_preset_rules(name)
        self.target_page.apply_preset_rules(rules)
        self.controller.add_log(f"Loaded preset: {name}")

    def _current_preview_domain(self) -> str:
        current = self.stack.currentWidget()
        if current is self.powers_page:
            return "powers"
        if current is self.target_page:
            return "specs"
        return str(self.controller.settings.get("roll_domain", "specs")).strip().lower() or "specs"

    def preview_ocr(self, roll_domain: str | None = None):
        if not self._ensure_idle("preview OCR"):
            return
        try:
            domain = "powers" if str(roll_domain or self._current_preview_domain()).strip().lower() == "powers" else "specs"
            settings = self._settings_for_domain(domain)
            self.controller.apply_settings(settings, save=False, announce=False)
            region_text = self.target_page.region_edit.text().strip()
            if domain == "powers":
                region_text = self.powers_page.preview_region_edit.text().strip()
            data = self._run_with_window_hidden_for_ocr_preview(
                lambda: self.controller.preview_ocr(region_text)
            )
        except Exception as e:
            QMessageBox.warning(self, "Preview Error", str(e))
            return
        self._show_preview_dialog(data)

    def preview_passive_shards(self):
        if not self._ensure_idle("preview passive shards"):
            return
        try:
            self.controller.apply_settings(self.compose_settings(), save=False, announce=False)
            data = self._run_with_window_hidden_for_ocr_preview(
                lambda: self.controller.preview_passive_shards(self.settings_page.passive_shard_region_edit.text().strip())
            )
        except Exception as e:
            QMessageBox.warning(self, "Passive Shard Preview", str(e))
            return
        self._show_shard_preview_dialog(data, "Passive Shard Preview")

    def preview_power_shards(self):
        if not self._ensure_idle("preview power shards"):
            return
        try:
            self.controller.apply_settings(self.compose_settings(), save=False, announce=False)
            data = self._run_with_window_hidden_for_ocr_preview(
                lambda: self.controller.preview_power_shards(self.settings_page.power_shard_region_edit.text().strip())
            )
        except Exception as e:
            QMessageBox.warning(self, "Power Shard Preview", str(e))
            return
        self._show_shard_preview_dialog(data, "Power Shard Preview")

    def _run_with_window_hidden_for_ocr_preview(self, capture):
        started = time.perf_counter()
        was_visible = self.isVisible()
        was_maximized = self.isMaximized()
        was_fullscreen = self.isFullScreen()
        self._set_preview_capture_notice(True, "Preparing preview")
        QApplication.processEvents()
        if was_visible:
            self._set_preview_capture_notice(True, "Window hidden")
            self._set_status("Preview capture")
            self.controller.add_log("OCR preview capture: hiding main window temporarily.")
            self.hide()
            QApplication.processEvents()
            time.sleep(0.18)
            QApplication.processEvents()
        try:
            return capture()
        finally:
            elapsed = time.perf_counter() - started
            try:
                self.controller.bot._record_timing_event(
                    "ocr_preview_capture",
                    elapsed,
                    result="completed",
                    ui_hidden=was_visible,
                )
            except Exception:
                pass
            self._set_preview_capture_notice(True, "Capture complete")
            if was_visible:
                if was_fullscreen:
                    self.showFullScreen()
                elif was_maximized:
                    self.showMaximized()
                else:
                    self.show()
                self.raise_()
                self.activateWindow()
                QApplication.processEvents()
                self._set_status("Preview ready")
                self._set_preview_capture_notice(True, "Preview restored")
                QTimer.singleShot(2400, lambda: self._set_preview_capture_notice(False))
                self.controller.add_log(f"OCR preview capture complete | elapsed={int(elapsed * 1000)}ms")

    def _preview_image_label(self, image, width=400, height=220):
        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        try:
            from PIL.ImageQt import ImageQt

            qimage = ImageQt(image.convert("RGBA"))
            pixmap = QPixmap.fromImage(qimage).scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            image_label.setPixmap(pixmap)
        except Exception:
            image_label.setText("Preview image could not be rendered.")
        return image_label

    def _show_preview_dialog(self, data: dict):
        dialog = QDialog(self)
        dialog.setWindowTitle("OCR Region Preview")
        dialog.resize(880, 650)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        layout.addWidget(self._preview_image_label(data["image"], 840, 320))

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(
            f"Trait: {data.get('trait') or 'Not detected'}\n"
            f"Merged: {data.get('merged') or 'No merged stats'}\n\n"
            f"Tesseract Attempts:\n{data.get('attempts') or 'No OCR text detected'}"
        )
        layout.addWidget(details, 1)
        dialog.exec()

    def _show_shard_preview_dialog(self, data: dict, title: str):
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(880, 620)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        image_row = QHBoxLayout()
        image_row.addWidget(self._preview_image_label(data["raw_image"], 400, 220))
        image_row.addWidget(self._preview_image_label(data["processed_image"], 400, 220))
        layout.addLayout(image_row)

        attempts = []
        for name, psm, text in data.get("attempts", []):
            attempts.append(f"{name} psm{psm}: {text.strip() or '<empty>'}")

        details = QPlainTextEdit()
        details.setReadOnly(True)
        details.setPlainText(
            f"Parsed: {data.get('formatted') or 'not found'}\n"
            f"Cleaned: {data.get('cleaned') or '<empty>'}\n\n"
            f"Raw OCR:\n{data.get('raw_text') or '<empty>'}\n\n"
            f"Attempts:\n{chr(10).join(attempts) if attempts else 'No OCR attempts'}"
        )
        layout.addWidget(details, 1)
        dialog.exec()

    def pick_specs_point(self, name: str):
        if not self._ensure_idle("pick positions"):
            return
        prompts = {
            "auto": "Hover over the Specs Auto checkbox.",
            "roll": "Hover over the Specs reroll button.",
            "yes": "Hover over the Specs confirm button.",
        }
        try:
            point = self._capture_mouse_position(prompts.get(name, "Hover over the target point."))
            self.target_page.set_point(name, format_point(point))
            self.apply_settings(confirm=False)
            self.controller.add_log(f"Picked specs {name} at {point[0]},{point[1]}")
        except Exception as e:
            QMessageBox.warning(self, "Pick Position", str(e))

    def pick_region(self, field_key: str | None = None):
        if not self._ensure_idle("pick the OCR region"):
            return
        prompt_map = {
            "stats_region": ("Hover over the top-left of the current spec box.", "Hover over the bottom-right of the current spec box."),
            "current_power_region": ("Hover over the top-left of the current power box.", "Hover over the bottom-right of the current power box."),
            "preview_region": ("Hover over the top-left of the OCR preview region.", "Hover over the bottom-right of the OCR preview region."),
            "auto_check_region": ("Hover over the top-left of the Powers Auto check region.", "Hover over the bottom-right of the Powers Auto check region."),
            "confirm_check_region": ("Hover over the top-left of the Powers confirm check region.", "Hover over the bottom-right of the Powers confirm check region."),
            "popup_region": ("Hover over the top-left of the popup detection region.", "Hover over the bottom-right of the popup detection region."),
            "change_detection_exclusion_region": ("Hover over the top-left of the change-detection exclusion region.", "Hover over the bottom-right of the change-detection exclusion region."),
        }
        key = field_key or "stats_region"
        try:
            prompt_a, prompt_b = prompt_map.get(key, prompt_map["stats_region"])
            p1 = self._capture_mouse_position(prompt_a)
            p2 = self._capture_mouse_position(prompt_b)
            x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1])
            x2, y2 = max(p1[0], p2[0]), max(p1[1], p2[1])
            region_text = format_region((x1, y1, x2 - x1, y2 - y1))
            if key == "stats_region":
                self.target_page.set_stats_region(region_text)
            else:
                mapping = {
                    "current_power_region": self.powers_page.current_power_region_edit,
                    "preview_region": self.powers_page.preview_region_edit,
                    "auto_check_region": self.powers_page.auto_check_region_edit,
                    "confirm_check_region": self.powers_page.confirm_check_region_edit,
                    "popup_region": self.powers_page.popup_region_edit,
                    "change_detection_exclusion_region": self.powers_page.change_exclusion_region_edit,
                }
                if key in mapping:
                    mapping[key].setText(region_text)
            self.apply_settings(confirm=False)
            self.controller.add_log(f"Picked {key}: {region_text}")
        except Exception as e:
            QMessageBox.warning(self, "Pick Region", str(e))

    def pick_runtime_point(self, name: str):
        if not self._ensure_idle("pick positions"):
            return
        prompts = {
            "auto": "Hover over the Powers Auto checkbox.",
            "roll": "Hover over the Powers reroll button.",
            "yes": "Hover over the Powers confirm button.",
        }
        try:
            point = self._capture_mouse_position(prompts.get(name, "Hover over the target point."))
            text = format_point(point)
            mapping = {
                "auto": self.powers_page.auto_point_edit,
                "roll": self.powers_page.roll_point_edit,
                "yes": self.powers_page.yes_point_edit,
            }
            if name in mapping:
                mapping[name].setText(text)
            self.apply_settings(confirm=False)
            self.controller.add_log(f"Picked powers {name} at {point[0]},{point[1]}")
        except Exception as e:
            QMessageBox.warning(self, "Pick Position", str(e))

    def pick_passive_shard_region(self):
        if not self._ensure_idle("pick the passive shard region"):
            return
        try:
            p1 = self._capture_mouse_position("Hover over the top-left of the passive shard count.")
            p2 = self._capture_mouse_position("Hover over the bottom-right of the passive shard count.")
            x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1])
            x2, y2 = max(p1[0], p2[0]), max(p1[1], p2[1])
            region_text = format_region((x1, y1, x2 - x1, y2 - y1))
            self.settings_page.passive_shard_region_edit.setText(region_text)
            self.apply_settings(confirm=False)
            self.controller.add_log(f"Picked passive shard region: {region_text}")
        except Exception as e:
            QMessageBox.warning(self, "Pick Passive Shards", str(e))

    def pick_power_shard_region(self):
        if not self._ensure_idle("pick the power shard region"):
            return
        try:
            p1 = self._capture_mouse_position("Hover over the top-left of the Power shard count.")
            p2 = self._capture_mouse_position("Hover over the bottom-right of the Power shard count.")
            x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1])
            x2, y2 = max(p1[0], p2[0]), max(p1[1], p2[1])
            region_text = format_region((x1, y1, x2 - x1, y2 - y1))
            self.settings_page.power_shard_region_edit.setText(region_text)
            self.apply_settings(confirm=False)
            self.controller.add_log(f"Picked power shard region: {region_text}")
        except Exception as e:
            QMessageBox.warning(self, "Pick Power Shards", str(e))

    def _capture_mouse_position(self, prompt: str) -> tuple[int, int]:
        QMessageBox.information(self, "Capture Position", f"{prompt}\n\nCapture starts in 2.5 seconds.")
        self.hide()
        QApplication.processEvents()
        time.sleep(2.5)
        point = self.controller.capture_mouse_position()
        self.show()
        self.raise_()
        self.activateWindow()
        return point

    def copy_selected_history(self):
        text = self.history_page.selected_text()
        if not text:
            QMessageBox.information(self, "Copy selected", "Select a row first.")
            return
        QApplication.clipboard().setText(text)
        self.controller.add_log("Copied selected history row.")

    def export_history(self, kind: str):
        default_name = "god_rolls.csv" if kind == "god" else "near_misses.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export History",
            default_name,
            "CSV Files (*.csv);;JSON Files (*.json)",
        )
        if not path:
            return
        try:
            self.controller.export_history(path, kind)
            self.controller.add_log(f"Exported history to {path}")
        except Exception as e:
            QMessageBox.warning(self, "Export", str(e))

    def open_capture_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.controller.capture_dir)))

    def clear_history(self, kind: str):
        label_text = "God Rolls" if kind == "god" else "Near-Misses"
        answer = QMessageBox.question(
            self,
            "Clear history",
            f"Clear {label_text} history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.controller.clear_history(kind)
            self.controller.add_log(f"Cleared {label_text} history.")

    def _set_status(self, text: str):
        self.status_value.setText(text)
        self.top_status_badge.setText(text or "Idle")
        self._apply_status_tone(text)
        self.main_page.set_status(text)
        self._refresh_macro_health()

    def _set_preview_capture_notice(self, visible: bool, text: str | None = None):
        if text is not None:
            self.preview_capture_notice.setText(text)
        self.preview_capture_notice.setVisible(visible)
        self.preview_capture_notice.style().unpolish(self.preview_capture_notice)
        self.preview_capture_notice.style().polish(self.preview_capture_notice)

    def _apply_status_tone(self, text: str):
        lowered = (text or "idle").lower()
        tone = "idle"
        if any(token in lowered for token in ("error", "failed", "stop", "popup")):
            tone = "error"
        elif any(token in lowered for token in ("recovery", "manual", "warn")):
            tone = "warn"
        elif any(token in lowered for token in ("running", "rolling", "active")):
            tone = "good"
        widget = self.top_status_badge
        widget.setProperty("stateTone", tone)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _refresh_macro_health(self):
        try:
            health = self.controller.macro_health_summary()
        except Exception:
            return
        self.main_page.set_macro_health(health)
        self.tools_page.set_diagnostics_readout(health)

    def _set_running(self, running: bool):
        self.main_page.set_active_mode(self.controller.bot.roll_domain if running else "idle")
        self.main_page.set_running(running)
        self.target_page.set_running(running)
        self.powers_page.set_running(running)
        self.settings_page.set_running(running)
        self.tools_page.set_running(running)
        if running and self._session_started_at is None:
            self._session_started_at = time.time()
            self.timer.start()
        elif not running:
            self.timer.stop()
            self._session_started_at = None
            self.timer_value.setText("00:00")
            self.main_page.set_session_time("00:00")

    def _tick_timer(self):
        if self._session_started_at is None:
            return
        elapsed = int(time.time() - self._session_started_at)
        minutes, seconds = divmod(elapsed, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            value = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            value = f"{minutes:02d}:{seconds:02d}"
        self.timer_value.setText(value)
        self.main_page.set_session_time(value)

    def _add_god_roll(self, entry):
        self.main_page.add_god_roll(entry)
        domain = "powers" if str(self.controller.settings.get("roll_domain", "specs")).strip().lower() == "powers" else "specs"
        passive = ""
        parsed_values = dict((self.controller.bot.last_decision_chain or {}).get("parsed_values") or {})
        if domain == "powers":
            passive_name = str(parsed_values.get("Passive") or "").strip()
            passive_value = str(parsed_values.get("Passive Value") or "").strip()
            passive_duration = str(parsed_values.get("Passive Duration") or "").strip()
            if passive_name:
                passive = passive_name
                if passive_value:
                    passive += f" {passive_value}"
                if passive_duration:
                    passive += f" / {passive_duration}"
        self.logs_page.update_preview(
            self.settings_page.player_ping_edit.text(),
            entry.spec,
            entry.rolled,
            domain=domain,
            passive=passive,
        )

    def _add_near_miss(self, entry):
        self.main_page.add_near_miss(entry)

    def _set_history(self, god_rolls: list, near_misses: list):
        self.main_page.set_history(god_rolls, near_misses)

    def _load_settings(self, settings: dict):
        self.target_page.load_settings(settings)
        self.powers_page.load_settings(settings)
        self.settings_page.load_settings(settings)
        self.main_page.set_display_mode(settings.get("roll_domain", "specs"))
        self._refresh_status_strip(settings)
        preview_name = "Fortune Chosen"
        preview_roll = "Drop 30 | Luck 10"
        preview_domain = "specs"
        preview_passive = ""
        if str(settings.get("roll_domain", "specs")).strip().lower() == "powers":
            preview_name = "Cursebrand"
            preview_roll = "Damage 30 | HP (optional) ? | Crit Chance 4 | Crit Damage 12"
            preview_domain = "powers"
            preview_passive = "NPC increased damage 15"
        self.logs_page.update_preview(
            settings.get("player_ping", ""),
            preview_name,
            preview_roll,
            domain=preview_domain,
            passive=preview_passive,
        )

    def _refresh_status_strip(self, settings: dict):
        roll_domain = str(settings.get("roll_domain", "specs")).strip().lower() or "specs"
        profile = str(settings.get("preset", "Default")) if roll_domain != "powers" else "Powers"
        self.preset_value.setText(profile)
        if roll_domain != "powers":
            region = str(settings.get("stats_region", "")).strip()
        else:
            region = str((settings.get("powers_layout") or {}).get("preview_region", "")).strip()
        self.ocr_value.setText("Set" if region and region != "0,0,0,0" else "Missing")
        webhook = str(settings.get("webhook_url", "")).strip()
        self.webhook_value.setText("Configured" if webhook else "Missing")
        self.main_page.set_active_targets_summary(self._target_summary_text(settings, roll_domain))
        profile = str(settings.get("preset", "Default")) if settings.get("roll_domain", "specs") != "powers" else "Powers"
        self.main_page.set_target_profile(profile)
        self.target_page.set_active_targets_summary(self._compact_target_summary(settings, "specs"))
        self.powers_page.set_active_targets_summary(self._compact_target_summary(settings, "powers"))

    def _set_passive_shards(self, text: str):
        self.passive_shards_value.setText(text)
        self.main_page.set_passive_shards(text)

    def _set_power_shards(self, text: str):
        self.power_shards_value.setText(text)
        self.main_page.set_power_shards(text)

    def _specs_summary_lines(self, settings: dict) -> list[str]:
        enabled = settings.get("enabled_specs") or {}
        rules = settings.get("real_rules") or {}
        specs = (
            ("fortune_chosen", "fortune", "Fortune Chosen"),
            ("executioner", "executioner", "Executioner"),
            ("rampage", "rampage", "Rampage"),
        )
        lines = []
        for enabled_key, rule_key, title in specs:
            if not enabled.get(enabled_key, True):
                lines.append(f"{title}: disabled")
                continue
            parts = []
            for label_text, cap, range_pair in zip(
                STAT_LABELS[rule_key],
                STAT_CAPS[rule_key],
                rules.get(rule_key, []),
            ):
                low, high = range_pair
                if high >= cap:
                    parts.append(f"{label_text} >= {low:g}%")
                else:
                    parts.append(f"{label_text} {low:g}-{high:g}%")
            lines.append(f"{title}: {', '.join(parts) if parts else 'no targets'}")
        if settings.get("require_current_spec", True):
            lines.append("CURRENT SPEC required")
        return lines

    def _powers_summary_lines(self, settings: dict) -> list[str]:
        enabled = settings.get("enabled_powers") or {}
        rules = settings.get("powers_rules") or {}
        lines = []
        for key, definition in SUPPORTED_POWER_DEFINITIONS.items():
            if not enabled.get(key, True):
                lines.append(f"{definition.name}: disabled")
                continue
            parts = []
            configured = rules.get(key, POWER_DEFAULT_RULES[key])
            for target, range_pair in zip(definition.rule_targets, configured):
                low, high = range_pair
                optional = " (optional)" if not target.required else ""
                if high >= target.max_value:
                    parts.append(f"{target.label}{optional} >= {low:g}%")
                else:
                    parts.append(f"{target.label}{optional} {low:g}-{high:g}%")
            lines.append(f"{definition.name}: {', '.join(parts) if parts else 'no targets'}")
        return lines

    def _target_summary_lines(self, settings: dict, summary_mode: str | None = None) -> list[str]:
        mode = str(summary_mode or self._apply_summary_mode(settings)).strip().lower() or "specs"
        if mode == "powers":
            return self._powers_summary_lines(settings)
        return self._specs_summary_lines(settings)

    def _target_summary_text(self, settings: dict, summary_mode: str | None = None) -> str:
        return "\n".join(self._target_summary_lines(settings, summary_mode))

    def _compact_target_summary(self, settings: dict, summary_mode: str | None = None) -> str:
        summary = "; ".join(self._target_summary_lines(settings, summary_mode))
        return summary if len(summary) <= 180 else summary[:177].rstrip() + "..."

    def _apply_summary_mode(self, settings: dict | None = None) -> str:
        sender = self.sender()
        if isinstance(sender, PowersPage):
            return "powers"
        if isinstance(sender, TargetsPage):
            return "specs"
        if isinstance(sender, SettingsPage):
            return str((settings or self.controller.settings).get("roll_domain", "specs")).strip().lower() or "specs"

        current = self.stack.currentWidget()
        if current is self.powers_page:
            return "powers"
        if current is self.target_page:
            return "specs"
        return str((settings or self.controller.settings).get("roll_domain", "specs")).strip().lower() or "specs"

    def _ensure_idle(self, action: str) -> bool:
        if not self.controller.bot.running:
            return True
        QMessageBox.information(self, "Bot Running", f"Stop the bot before you {action}.")
        return False

    def _confirm_apply(self, settings: dict, summary_mode: str | None = None) -> bool:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Confirm Active Mode Targets")
        box.setText(f"Confirm and apply these targets to {APP_DISPLAY_NAME}?")
        box.setInformativeText("\n".join(self._target_summary_lines(settings, summary_mode)))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        yes_button = box.button(QMessageBox.StandardButton.Yes)
        if yes_button is not None:
            yes_button.setText("Confirm and Apply")
        cancel_button = box.button(QMessageBox.StandardButton.Cancel)
        if cancel_button is not None:
            cancel_button.setText("Cancel / Edit")
        box.setDefaultButton(QMessageBox.StandardButton.Yes)
        return box.exec() == QMessageBox.StandardButton.Yes

    def closeEvent(self, event):
        try:
            if self.controller.bot.running:
                self.controller.stop()
            else:
                self.controller.apply_settings(self.compose_settings(), save=True, announce=False)
            self.controller.save_logs()
        except Exception:
            pass
        super().closeEvent(event)
