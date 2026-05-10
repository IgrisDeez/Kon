from __future__ import annotations

import csv
import json
import re
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from PySide6.QtCore import QObject, Signal
except ModuleNotFoundError:
    class QObject:
        def __init__(self, *args, **kwargs):
            super().__init__()

    class _BoundSignal:
        def __init__(self, slots):
            self._slots = slots

        def connect(self, slot):
            self._slots.append(slot)

        def emit(self, *args):
            for slot in list(self._slots):
                slot(*args)

    class Signal:
        def __init__(self, *types):
            self._name = ""

        def __set_name__(self, owner, name):
            self._name = f"__signal_{name}"

        def __get__(self, instance, owner):
            if instance is None:
                return self
            return _BoundSignal(instance.__dict__.setdefault(self._name, []))

from .. import APP_DISPLAY_NAME, APP_VERSION, SETTINGS_SCHEMA_VERSION
from . import bot as bot_module
from .bot import (
    AelrithForgeBot,
    CAPTURE_DIR,
    DEFAULT_CONFIG,
    DEFAULT_REAL_RULES,
    HISTORY_FILE,
    NEAR_MISS_FILE,
    PRESET_RULES,
    SETTINGS_FILE,
    deep_copy_rules,
    detect_trait,
    display_trait,
    format_shard_count,
    parse_passive_shard_count,
    parse_power_shard_count,
    sanitize_rules,
)
from .powers import POWER_DEFAULT_RULES, SUPPORTED_POWER_DEFINITIONS, default_power_settings, sanitize_power_rules, summarize_power_values
from .log_schema import normalize_log_entry
from .paths import (
    CONFIG_BACKUP_DIR,
    DIAGNOSTIC_DIR,
    LEGACY_HISTORY_FILE,
    LEGACY_NEAR_MISS_FILE,
    LEGACY_RUNTIME_LOG_FILE,
    LEGACY_SETTINGS_FILE,
    RUNTIME_LOG_FILE,
    ensure_app_dirs,
)

LOG_FILE = RUNTIME_LOG_FILE
LIVE_PROOF_DIR = DIAGNOSTIC_DIR / "live_proof"
CURRENT_SETTINGS_VERSION = SETTINGS_SCHEMA_VERSION
REMOVED_SETTINGS_KEYS = {
    "easyocr_enabled",
    "easyocr_fallback",
    "easyocr_gpu",
    "easyocr_languages",
    "use_easyocr",
}
SAFE_LEGACY_MIGRATION_KEYS = {
    "coords",
    "clean_debug_artifacts_on_start",
    "auto_capture_debug_snapshots",
    "debug_snapshot_on_macro_stop",
    "debug_snapshot_on_popup_stuck",
    "debug_snapshot_on_recovery_failure",
    "debug_snapshot_retention_count",
    "delete_screenshots_after_webhook",
    "passive_shard_alerts",
    "passive_shard_alert_cooldown",
    "passive_shard_critical_threshold",
    "passive_shard_empty_threshold",
    "passive_shard_low_threshold",
    "passive_shard_report_interval",
    "passive_shard_very_low_threshold",
    "power_shard_alerts",
    "power_shard_alert_cooldown",
    "power_shard_critical_threshold",
    "power_shard_empty_threshold",
    "power_shard_low_threshold",
    "power_shard_region",
    "power_shard_report_interval",
    "power_shard_very_low_threshold",
    "player_ping",
    "stop_on_empty_power_shards",
    "stop_on_empty_passive_shards",
    "tesseract_cmd",
    "ui",
    "webhook_failure_screenshots",
    "webhook_live_status_enabled",
    "webhook_screenshot_on_macro_stop",
    "webhook_screenshot_on_popup_stuck",
    "webhook_status_update_interval",
    "webhook_url",
}


@dataclass
class GodRollEntry:
    time: str
    spec: str
    rolled: str
    screenshot_path: str = ""
    webhook_sent: bool = False


@dataclass
class NearMissEntry:
    time: str
    spec: str
    stats: str
    failed_condition: str = ""
    miss_distance: str = ""
    screenshot_path: str = ""

    @property
    def screenshot_saved(self) -> str:
        return self.screenshot_path if self.screenshot_path else "No"


def format_region(region) -> str:
    return ",".join(str(int(x)) for x in region)


def parse_region(text: str) -> tuple[int, int, int, int]:
    parts = [int(x.strip()) for x in text.split(",")]
    if len(parts) != 4:
        raise ValueError("Region must contain x,y,w,h")
    if parts[2] <= 0 or parts[3] <= 0:
        raise ValueError("Region width and height must be positive")
    return tuple(parts)


def parse_optional_region(text: str) -> tuple[int, int, int, int]:
    parts = [int(x.strip()) for x in text.split(",")]
    if len(parts) != 4:
        raise ValueError("Region must contain x,y,w,h")
    if parts == [0, 0, 0, 0]:
        return (0, 0, 0, 0)
    if parts[2] <= 0 or parts[3] <= 0:
        raise ValueError("Region width and height must be positive")
    return tuple(parts)


def parse_point(text: str) -> tuple[int, int]:
    parts = [int(x.strip()) for x in text.split(",")]
    if len(parts) != 2:
        raise ValueError("Point must contain x,y")
    return tuple(parts)


def format_point(point) -> str:
    return ",".join(str(int(x)) for x in point)


def default_settings() -> dict:
    cfg = DEFAULT_CONFIG
    return {
        "settings_version": CURRENT_SETTINGS_VERSION,
        "mode": "real",
        "roll_domain": "specs",
        "preset": "Default",
        "nudge": int(cfg["AUTO_LEFT_NUDGE"]),
        "start_delay": float(cfg["STARTUP_DELAY"]),
        "stats_region": format_region(cfg["STATS_REGION"]),
        "webhook_url": "",
        "player_ping": "",
        "delete_screenshots_after_webhook": bool(cfg["DELETE_SCREENSHOTS_AFTER_WEBHOOK"]),
        "clean_debug_artifacts_on_start": bool(cfg["CLEAN_DEBUG_ARTIFACTS_ON_START"]),
        "auto_capture_debug_snapshots": bool(cfg["AUTO_CAPTURE_DEBUG_SNAPSHOTS"]),
        "debug_snapshot_on_macro_stop": bool(cfg["DEBUG_SNAPSHOT_ON_MACRO_STOP"]),
        "debug_snapshot_on_popup_stuck": bool(cfg["DEBUG_SNAPSHOT_ON_POPUP_STUCK"]),
        "debug_snapshot_on_recovery_failure": bool(cfg["DEBUG_SNAPSHOT_ON_RECOVERY_FAILURE"]),
        "debug_snapshot_retention_count": int(cfg["DEBUG_SNAPSHOT_RETENTION_COUNT"]),
        "webhook_live_status_enabled": bool(cfg["WEBHOOK_LIVE_STATUS_ENABLED"]),
        "webhook_status_update_interval": int(cfg["WEBHOOK_STATUS_UPDATE_INTERVAL"]),
        "webhook_failure_screenshots": bool(cfg["WEBHOOK_FAILURE_SCREENSHOTS"]),
        "webhook_screenshot_on_popup_stuck": bool(cfg["WEBHOOK_SCREENSHOT_ON_POPUP_STUCK"]),
        "webhook_screenshot_on_macro_stop": bool(cfg["WEBHOOK_SCREENSHOT_ON_MACRO_STOP"]),
        "require_current_spec": True,
        "tesseract_cmd": cfg["TESSERACT_CMD"],
        "popup_region": format_region(cfg["POPUP_REGION"]),
        "protected_region": format_region(cfg["PROTECTED_REGION"]),
        "passive_shard_region": format_region(cfg["PASSIVE_SHARD_REGION"]),
        "passive_shard_alerts": bool(cfg["PASSIVE_SHARD_ALERTS"]),
        "passive_shard_report_interval": int(cfg["PASSIVE_SHARD_REPORT_INTERVAL"]),
        "passive_shard_low_threshold": int(cfg["PASSIVE_SHARD_LOW_THRESHOLD"]),
        "passive_shard_very_low_threshold": int(cfg["PASSIVE_SHARD_VERY_LOW_THRESHOLD"]),
        "passive_shard_critical_threshold": int(cfg["PASSIVE_SHARD_CRITICAL_THRESHOLD"]),
        "passive_shard_empty_threshold": int(cfg["PASSIVE_SHARD_EMPTY_THRESHOLD"]),
        "passive_shard_alert_cooldown": int(cfg["PASSIVE_SHARD_ALERT_COOLDOWN"]),
        "stop_on_empty_passive_shards": bool(cfg["STOP_ON_EMPTY_PASSIVE_SHARDS"]),
        "power_shard_region": format_region(cfg["POWER_SHARD_REGION"]),
        "power_shard_alerts": bool(cfg["POWER_SHARD_ALERTS"]),
        "power_shard_report_interval": int(cfg["POWER_SHARD_REPORT_INTERVAL"]),
        "power_shard_low_threshold": int(cfg["POWER_SHARD_LOW_THRESHOLD"]),
        "power_shard_very_low_threshold": int(cfg["POWER_SHARD_VERY_LOW_THRESHOLD"]),
        "power_shard_critical_threshold": int(cfg["POWER_SHARD_CRITICAL_THRESHOLD"]),
        "power_shard_empty_threshold": int(cfg["POWER_SHARD_EMPTY_THRESHOLD"]),
        "power_shard_alert_cooldown": int(cfg["POWER_SHARD_ALERT_COOLDOWN"]),
        "stop_on_empty_power_shards": bool(cfg["STOP_ON_EMPTY_POWER_SHARDS"]),
        "loop_delay": float(cfg["LOOP_DELAY"]),
        "stuck_timeout": float(cfg["STUCK_TIMEOUT"]),
        "auto_verify_delay": float(cfg["AUTO_VERIFY_DELAY"]),
        "auto_verify_polls": int(cfg["AUTO_VERIFY_POLLS"]),
        "auto_verify_poll_delay": float(cfg["AUTO_VERIFY_POLL_DELAY"]),
        "max_recovery_attempts": int(cfg["MAX_RECOVERY_ATTEMPTS"]),
        "coords": {
            "auto": format_point(cfg["AUTO_CHECKBOX"]),
            "roll": format_point(cfg["ROLL_BUTTON"]),
            "yes": format_point(cfg["YES_BUTTON"]),
        },
        "enabled_specs": {
            "fortune_chosen": True,
            "executioner": True,
            "rampage": True,
        },
        "real_rules": deep_copy_rules(DEFAULT_REAL_RULES),
        **default_power_settings(),
        "ui": {
            "compact_tables": True,
            "show_session_timer": True,
        },
    }


class BotController(QObject):
    status_changed = Signal(str)
    log_received = Signal(str, str)
    log_entry_added = Signal(object)
    god_roll_added = Signal(object)
    near_miss_added = Signal(object)
    history_loaded = Signal(list, list)
    settings_changed = Signal(dict)
    runtime_changed = Signal(bool)
    passive_shards_changed = Signal(str)
    power_shards_changed = Signal(str)
    decision_chain_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        ensure_app_dirs()
        self.settings = self.normalize_settings(default_settings())
        self.god_rolls: list[GodRollEntry] = []
        self.near_misses: list[NearMissEntry] = []
        self.logs: list[dict] = []
        self._last_log_save = 0.0
        self.bot = AelrithForgeBot(
            self._bot_log,
            self._bot_status,
            self._bot_god_roll,
            self._bot_near_miss,
        )
        self.load_logs()
        self.load_settings()
        self.load_history()
        self.apply_settings(self.settings, save=False, announce=False)
        self.cleanup_old_runtime_log_backups()

    def _bot_log(self, text: str):
        lowered = text.lower()
        level = "info"
        if "keep" in lowered or "sent successfully" in lowered:
            level = "ok"
        elif "near miss" in lowered or "skip" in lowered or "ignored" in lowered:
            level = "warn"
        elif "error" in lowered or "failed" in lowered or "fatal" in lowered:
            level = "error"
        shard_match = re.search(r"passive shards:\s*(.+)", text, re.IGNORECASE)
        if shard_match:
            value, _normalized = parse_passive_shard_count(shard_match.group(1))
            self.passive_shards_changed.emit(format_shard_count(value) if value is not None else shard_match.group(1).strip())
        power_shard_match = re.search(r"power shards:\s*(.+)", text, re.IGNORECASE)
        if power_shard_match:
            value, _normalized = parse_power_shard_count(power_shard_match.group(1))
            self.power_shards_changed.emit(
                format_shard_count(value) if value is not None else power_shard_match.group(1).strip()
            )
        entry = self._record_log(text, level)
        self.log_received.emit(text, level)
        self.log_entry_added.emit(dict(entry))
        self.decision_chain_changed.emit(self.format_decision_chain())

    def add_log(self, text: str):
        self._bot_log(text)

    def _record_log(self, text: str, level: str):
        entry = normalize_log_entry({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": str(text),
        }) or {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "message": str(text),
        }
        self.logs.append(entry)
        if len(self.logs) > 1000:
            self.logs = self.logs[-1000:]
        now = time.time()
        if level == "error" or now - self._last_log_save > 2.0:
            self.save_logs()
            self._last_log_save = now
        return entry

    def _bot_status(self, text: str):
        self.status_changed.emit(text)
        lowered = text.lower()
        if "stopped" in lowered:
            self.runtime_changed.emit(False)
        elif "starting" in lowered or "rolling" in lowered or "manual" in lowered:
            self.runtime_changed.emit(True)

    def _bot_god_roll(self, timestamp, trait, summary, screenshot_path, webhook_sent=False):
        entry = GodRollEntry(
            time=str(timestamp),
            spec=display_trait(trait),
            rolled=str(summary),
            screenshot_path=str(screenshot_path or ""),
            webhook_sent=bool(webhook_sent),
        )
        self.god_rolls.insert(0, entry)
        self.save_history()
        self.god_roll_added.emit(entry)

    def _bot_near_miss(
        self,
        timestamp,
        trait,
        summary,
        screenshot_path,
        failed_condition="",
        miss_distance="",
    ):
        entry = NearMissEntry(
            time=str(timestamp),
            spec=display_trait(trait),
            stats=str(summary),
            failed_condition=str(failed_condition or "Target stats not met"),
            miss_distance=str(miss_distance or "Close to target"),
            screenshot_path=str(screenshot_path or ""),
        )
        self.near_misses.insert(0, entry)
        self.save_history()
        self.near_miss_added.emit(entry)

    def normalize_settings(self, raw: dict | None) -> dict:
        data = default_settings()
        raw = raw or {}
        for key, value in raw.items():
            if key in REMOVED_SETTINGS_KEYS:
                continue
            if key in ("coords", "enabled_specs", "real_rules", "ui", "enabled_powers", "powers_rules", "powers_layout") and isinstance(value, dict):
                data[key].update(value)
            elif key in data:
                data[key] = value

        data["settings_version"] = CURRENT_SETTINGS_VERSION
        data["stats_region"] = self._normalize_region_value(data.get("stats_region"), DEFAULT_CONFIG["STATS_REGION"])
        data["popup_region"] = self._normalize_region_value(data.get("popup_region"), DEFAULT_CONFIG["POPUP_REGION"])
        data["protected_region"] = self._normalize_region_value(
            data.get("protected_region"), DEFAULT_CONFIG["PROTECTED_REGION"]
        )
        data["passive_shard_region"] = self._normalize_region_value(
            data.get("passive_shard_region"), DEFAULT_CONFIG["PASSIVE_SHARD_REGION"]
        )
        data["power_shard_region"] = self._normalize_region_value(
            data.get("power_shard_region"), DEFAULT_CONFIG["POWER_SHARD_REGION"]
        )

        coords = data.get("coords") or {}
        for key, default_key in (("auto", "AUTO_CHECKBOX"), ("roll", "ROLL_BUTTON"), ("yes", "YES_BUTTON")):
            coords[key] = self._normalize_point_value(coords.get(key), DEFAULT_CONFIG[default_key])
        data["coords"] = coords
        data["real_rules"] = sanitize_rules(data.get("real_rules") or DEFAULT_REAL_RULES)
        power_defaults = default_power_settings()
        power_layout = dict(power_defaults["powers_layout"])
        incoming_layout = data.get("powers_layout") or {}
        power_layout.update({k: v for k, v in incoming_layout.items() if k != "coords"})
        power_coords = dict(power_layout.get("coords") or {})
        incoming_power_coords = (incoming_layout.get("coords") or {}) if isinstance(incoming_layout, dict) else {}
        power_coords.update(incoming_power_coords)
        preview_region = power_layout.get("preview_region", "0,0,0,0")
        current_power_region = power_layout.get("current_power_region", power_layout.get("stats_region", preview_region))
        if str(current_power_region).strip() in ("", "0,0,0,0") and str(preview_region).strip() not in ("", "0,0,0,0"):
            current_power_region = preview_region
        power_layout["preview_region"] = self._normalize_region_value(preview_region, (0, 0, 0, 0))
        power_layout["current_power_region"] = self._normalize_region_value(current_power_region, (0, 0, 0, 0))
        power_layout["stats_region"] = power_layout["current_power_region"]
        power_layout["auto_check_region"] = self._normalize_region_value(power_layout.get("auto_check_region"), (0, 0, 0, 0))
        power_layout["confirm_check_region"] = self._normalize_region_value(power_layout.get("confirm_check_region"), (0, 0, 0, 0))
        popup_candidate = power_layout.get("popup_region")
        if str(popup_candidate).strip() in ("", "0,0,0,0"):
            popup_candidate = data.get("popup_region")
        change_exclusion_candidate = power_layout.get("change_detection_exclusion_region") or power_layout.get("protected_region")
        if str(change_exclusion_candidate).strip() in ("", "0,0,0,0"):
            change_exclusion_candidate = data.get("protected_region")
        power_layout["popup_region"] = self._normalize_region_value(popup_candidate, DEFAULT_CONFIG["POPUP_REGION"])
        power_layout["change_detection_exclusion_region"] = self._normalize_region_value(change_exclusion_candidate, DEFAULT_CONFIG["PROTECTED_REGION"])
        power_layout["protected_region"] = power_layout["change_detection_exclusion_region"]
        power_coords["auto"] = self._normalize_point_value(power_coords.get("auto"), (0, 0))
        power_coords["roll"] = self._normalize_point_value(power_coords.get("roll"), (0, 0))
        power_coords["yes"] = self._normalize_point_value(power_coords.get("yes"), (0, 0))
        power_layout["coords"] = power_coords
        data["powers_layout"] = power_layout
        data["enabled_powers"] = {
            key: bool((data.get("enabled_powers") or power_defaults["enabled_powers"]).get(key, True))
            for key in power_defaults["enabled_powers"]
        }
        data["powers_rules"] = sanitize_power_rules(data.get("powers_rules") or power_defaults["powers_rules"])
        return data

    def migrate_legacy_settings(self, raw: dict) -> dict:
        migrated = default_settings()
        for key in SAFE_LEGACY_MIGRATION_KEYS:
            value = raw.get(key)
            if value is None or key in REMOVED_SETTINGS_KEYS:
                continue
            if key in ("coords", "ui") and isinstance(value, dict):
                migrated[key].update(value)
            elif key in migrated:
                migrated[key] = value
        return self.normalize_settings(migrated)

    def _normalize_region_value(self, value, fallback) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return format_region(value)
        return format_region(fallback)

    def _normalize_point_value(self, value, fallback) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, (list, tuple)):
            return format_point(value)
        return format_point(fallback)

    def apply_settings(self, settings: dict, save: bool = True, announce: bool = True):
        data = self.normalize_settings(settings)
        real_rules = sanitize_rules(data["real_rules"])
        enabled_specs = set()
        enabled = data.get("enabled_specs") or {}
        if enabled.get("fortune_chosen", True):
            enabled_specs.update({"fortune", "chosen"})
        if enabled.get("executioner", True):
            enabled_specs.add("executioner")
        if enabled.get("rampage", True):
            enabled_specs.add("rampage")

        power_rules = sanitize_power_rules(data.get("powers_rules") or default_power_settings()["powers_rules"])
        enabled_powers = {key for key, enabled in (data.get("enabled_powers") or {}).items() if enabled}
        roll_domain = str(data.get("roll_domain", "specs")).strip().lower() or "specs"

        active_layout = {
            "stats_region": data["stats_region"],
            "popup_region": data["popup_region"],
            "protected_region": data["protected_region"],
            "coords": data["coords"],
        }
        if roll_domain == "powers":
            active_layout = data.get("powers_layout") or active_layout
            required_regions = [
                active_layout.get("stats_region", "0,0,0,0"),
                active_layout.get("popup_region", "0,0,0,0"),
                active_layout.get("protected_region", "0,0,0,0"),
            ]
            if any(parse_optional_region(value) == (0, 0, 0, 0) for value in required_regions):
                raise ValueError("Powers layout is not configured yet. Set Powers OCR/popup/protected regions before switching the live engine to Powers.")
            power_coords = active_layout.get("coords") or {}
            if any(parse_point(str(power_coords.get(key, "0,0"))) == (0, 0) for key in ("auto", "roll", "yes")):
                raise ValueError("Powers layout is not configured yet. Set Powers Auto / Reroll / Confirm points before switching the live engine to Powers.")

        self.bot.set_roll_domain(roll_domain)
        self.bot.set_rules(real_rules)
        self.bot.set_power_rules(power_rules)
        self.bot.set_mode(str(data.get("mode", "real")))
        self.bot.set_enabled_specs(enabled_specs)
        self.bot.set_enabled_powers(enabled_powers)
        self.bot.update(
            AUTO_LEFT_NUDGE=int(data["nudge"]),
            STARTUP_DELAY=float(data["start_delay"]),
            STATS_REGION=parse_region(active_layout["stats_region"]),
            POPUP_REGION=parse_region(active_layout["popup_region"]),
            PROTECTED_REGION=parse_region(active_layout["protected_region"]),
            PASSIVE_SHARD_REGION=parse_optional_region(data["passive_shard_region"]),
            PASSIVE_SHARD_ALERTS=bool(data.get("passive_shard_alerts", True)),
            PASSIVE_SHARD_REPORT_INTERVAL=int(data.get("passive_shard_report_interval", 1200)),
            PASSIVE_SHARD_LOW_THRESHOLD=int(data.get("passive_shard_low_threshold", DEFAULT_CONFIG["PASSIVE_SHARD_LOW_THRESHOLD"])),
            PASSIVE_SHARD_VERY_LOW_THRESHOLD=int(
                data.get("passive_shard_very_low_threshold", DEFAULT_CONFIG["PASSIVE_SHARD_VERY_LOW_THRESHOLD"])
            ),
            PASSIVE_SHARD_CRITICAL_THRESHOLD=int(
                data.get("passive_shard_critical_threshold", DEFAULT_CONFIG["PASSIVE_SHARD_CRITICAL_THRESHOLD"])
            ),
            PASSIVE_SHARD_EMPTY_THRESHOLD=int(
                data.get("passive_shard_empty_threshold", DEFAULT_CONFIG["PASSIVE_SHARD_EMPTY_THRESHOLD"])
            ),
            PASSIVE_SHARD_ALERT_COOLDOWN=int(
                data.get("passive_shard_alert_cooldown", DEFAULT_CONFIG["PASSIVE_SHARD_ALERT_COOLDOWN"])
            ),
            STOP_ON_EMPTY_PASSIVE_SHARDS=bool(data.get("stop_on_empty_passive_shards", True)),
            POWER_SHARD_REGION=parse_optional_region(data["power_shard_region"]),
            POWER_SHARD_ALERTS=bool(data.get("power_shard_alerts", True)),
            POWER_SHARD_REPORT_INTERVAL=int(data.get("power_shard_report_interval", 1200)),
            POWER_SHARD_LOW_THRESHOLD=int(data.get("power_shard_low_threshold", DEFAULT_CONFIG["POWER_SHARD_LOW_THRESHOLD"])),
            POWER_SHARD_VERY_LOW_THRESHOLD=int(
                data.get("power_shard_very_low_threshold", DEFAULT_CONFIG["POWER_SHARD_VERY_LOW_THRESHOLD"])
            ),
            POWER_SHARD_CRITICAL_THRESHOLD=int(
                data.get("power_shard_critical_threshold", DEFAULT_CONFIG["POWER_SHARD_CRITICAL_THRESHOLD"])
            ),
            POWER_SHARD_EMPTY_THRESHOLD=int(
                data.get("power_shard_empty_threshold", DEFAULT_CONFIG["POWER_SHARD_EMPTY_THRESHOLD"])
            ),
            POWER_SHARD_ALERT_COOLDOWN=int(
                data.get("power_shard_alert_cooldown", DEFAULT_CONFIG["POWER_SHARD_ALERT_COOLDOWN"])
            ),
            STOP_ON_EMPTY_POWER_SHARDS=bool(data.get("stop_on_empty_power_shards", True)),
            AUTO_CAPTURE_DEBUG_SNAPSHOTS=bool(data.get("auto_capture_debug_snapshots", False)),
            DEBUG_SNAPSHOT_ON_MACRO_STOP=bool(data.get("debug_snapshot_on_macro_stop", True)),
            DEBUG_SNAPSHOT_ON_POPUP_STUCK=bool(data.get("debug_snapshot_on_popup_stuck", True)),
            DEBUG_SNAPSHOT_ON_RECOVERY_FAILURE=bool(data.get("debug_snapshot_on_recovery_failure", True)),
            DEBUG_SNAPSHOT_RETENTION_COUNT=int(
                data.get("debug_snapshot_retention_count", DEFAULT_CONFIG["DEBUG_SNAPSHOT_RETENTION_COUNT"])
            ),
            WEBHOOK_URL=str(data.get("webhook_url", "")).strip(),
            PLAYER_PING=str(data.get("player_ping", "")).strip(),
            DELETE_SCREENSHOTS_AFTER_WEBHOOK=bool(data.get("delete_screenshots_after_webhook", True)),
            CLEAN_DEBUG_ARTIFACTS_ON_START=bool(data.get("clean_debug_artifacts_on_start", False)),
            WEBHOOK_LIVE_STATUS_ENABLED=bool(data.get("webhook_live_status_enabled", True)),
            WEBHOOK_STATUS_UPDATE_INTERVAL=int(
                data.get("webhook_status_update_interval", DEFAULT_CONFIG["WEBHOOK_STATUS_UPDATE_INTERVAL"])
            ),
            WEBHOOK_FAILURE_SCREENSHOTS=bool(data.get("webhook_failure_screenshots", True)),
            WEBHOOK_SCREENSHOT_ON_POPUP_STUCK=bool(data.get("webhook_screenshot_on_popup_stuck", True)),
            WEBHOOK_SCREENSHOT_ON_MACRO_STOP=bool(data.get("webhook_screenshot_on_macro_stop", True)),
            REQUIRE_CURRENT_SPEC=bool(data.get("require_current_spec", True)),
            TESSERACT_CMD=str(data.get("tesseract_cmd", DEFAULT_CONFIG["TESSERACT_CMD"])),
            LOOP_DELAY=float(data.get("loop_delay", DEFAULT_CONFIG["LOOP_DELAY"])),
            STUCK_TIMEOUT=float(data.get("stuck_timeout", DEFAULT_CONFIG["STUCK_TIMEOUT"])),
            AUTO_VERIFY_DELAY=float(data.get("auto_verify_delay", DEFAULT_CONFIG["AUTO_VERIFY_DELAY"])),
            AUTO_VERIFY_POLLS=int(data.get("auto_verify_polls", DEFAULT_CONFIG["AUTO_VERIFY_POLLS"])),
            AUTO_VERIFY_POLL_DELAY=float(
                data.get("auto_verify_poll_delay", DEFAULT_CONFIG["AUTO_VERIFY_POLL_DELAY"])
            ),
            MAX_RECOVERY_ATTEMPTS=int(data.get("max_recovery_attempts", DEFAULT_CONFIG["MAX_RECOVERY_ATTEMPTS"])),
        )
        active_coords = active_layout.get("coords") or data["coords"]
        self.bot.cfg["AUTO_CHECKBOX"] = parse_point(active_coords["auto"])
        self.bot.cfg["ROLL_BUTTON"] = parse_point(active_coords["roll"])
        self.bot.cfg["YES_BUTTON"] = parse_point(active_coords["yes"])

        self.settings = data
        if save:
            self.save_settings()
        self.settings_changed.emit(dict(self.settings))
        if announce:
            self._bot_log("Settings applied.")

    def safe_power_settings_snapshot(self, settings: dict | None = None) -> dict:
        data = self.normalize_settings(settings or self.settings)
        return {
            "roll_domain": data.get("roll_domain"),
            "powers_layout": data.get("powers_layout"),
            "enabled_powers": data.get("enabled_powers"),
            "powers_rules": data.get("powers_rules"),
            "power_shard_region": data.get("power_shard_region"),
        }

    def save_power_settings_backup(self, path: Path | None = None) -> Path:
        backup_path = Path(path) if path is not None else SETTINGS_FILE.parent / f"powers_settings_backup_{time.strftime('%Y%m%d_%H%M%S')}.json"
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_text(json.dumps(self.safe_power_settings_snapshot(), indent=2), encoding="utf-8")
        return backup_path

    def start(self, settings: dict):
        if self.bot.running:
            self._bot_log("The bot is already running.")
            return
        self.apply_settings(settings)
        if self.bot.cfg.get("CLEAN_DEBUG_ARTIFACTS_ON_START", False):
            self.clean_debug_artifacts()
        self.bot.start()
        self.runtime_changed.emit(True)

    def stop(self):
        was_running = bool(self.bot.running)
        self.bot.stop()
        self.runtime_changed.emit(False)
        if was_running:
            try:
                self.export_live_proof_pack("session_stop")
            except Exception as e:
                self._bot_log(f"Live proof pack export failed after stop: {e}")

    def test_webhook(self, settings: dict) -> bool:
        self.apply_settings(settings)
        self._bot_log("Testing Discord webhook...")
        return self.bot.test_webhook()

    def capture_debug_report(self, settings: dict | None = None) -> str:
        if settings is not None:
            self.apply_settings(settings, save=False, announce=False)
        recent_logs = self.logs[-80:]
        path = self.bot.capture_diagnostic_snapshot("manual", extra={"recent_logs": recent_logs})
        self._bot_log(f"Manual debug report saved: {path}")
        self.decision_chain_changed.emit(self.format_decision_chain())
        return path

    def capture_current_screenshot(self) -> str:
        path = self.bot.capture_screen("debug_capture")
        self._bot_log(f"Debug screenshot saved: {path}")
        return path

    def _safe_artifact_label(self, text: str, fallback: str = "manual") -> str:
        value = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(text or "").strip()).strip("_").lower()
        return value or fallback

    def _unique_folder(self, root: Path, base_name: str) -> Path:
        folder = root / base_name
        suffix = 2
        while folder.exists():
            folder = root / f"{base_name}_{suffix}"
            suffix += 1
        return folder

    def _format_live_proof_duration(self, seconds: float) -> str:
        seconds = max(0, int(seconds))
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _live_proof_target_summary(self) -> list[str]:
        settings = self.settings or {}
        if str(settings.get("roll_domain", "specs")).strip().lower() == "powers":
            enabled = settings.get("enabled_powers") or {}
            rules = settings.get("powers_rules") or {}
            lines = []
            for key, definition in SUPPORTED_POWER_DEFINITIONS.items():
                if not enabled.get(key, True):
                    lines.append(f"{definition.name}: disabled")
                    continue
                configured = rules.get(key, POWER_DEFAULT_RULES[key])
                parts = []
                for target, range_pair in zip(definition.rule_targets, configured):
                    low, high = range_pair
                    optional = " (optional)" if not target.required else ""
                    if high >= target.max_value:
                        parts.append(f"{target.label}{optional} >= {low:g}%")
                    else:
                        parts.append(f"{target.label}{optional} {low:g}-{high:g}%")
                lines.append(f"{definition.name}: {', '.join(parts) if parts else 'no targets'}")
            return lines

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
            for label, cap, range_pair in zip(
                bot_module.STAT_LABELS[rule_key],
                bot_module.STAT_CAPS[rule_key],
                rules.get(rule_key, []),
            ):
                low, high = range_pair
                if high >= cap:
                    parts.append(f"{label} >= {low:g}%")
                else:
                    parts.append(f"{label} {low:g}-{high:g}%")
            lines.append(f"{title}: {', '.join(parts) if parts else 'no targets'}")
        if settings.get("require_current_spec", True):
            lines.append("CURRENT SPEC required")
        return lines

    def _live_proof_shard_summary(self) -> dict:
        passive_current = self.bot.session_latest_passive_shards
        power_current = self.bot.session_latest_power_shards
        return {
            "passive": {
                "current": passive_current,
                "current_formatted": format_shard_count(passive_current) if passive_current is not None else "unknown",
                "session": self.bot.passive_shard_usage_summary(),
                "state": dict(self.bot.last_shard_ocr_state or {}),
            },
            "power": {
                "current": power_current,
                "current_formatted": format_shard_count(power_current) if power_current is not None else "unknown",
                "session": self.bot.power_shard_usage_summary(),
                "state": dict(self.bot.last_power_shard_ocr_state or {}),
            },
        }

    def _live_proof_payload(self, trigger: str) -> dict:
        now = time.time()
        started = float(self.bot.session_started_at or 0.0)
        duration_seconds = max(0.0, now - started) if started else 0.0
        recent_logs = self.recent_log_entries(80)
        operator_events = [entry for entry in recent_logs if entry.get("operator_visible")][-40:]
        return {
            "app": APP_DISPLAY_NAME,
            "version": APP_VERSION,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "trigger": trigger,
            "active_domain": str(self.settings.get("roll_domain", "specs")).strip().lower() or "specs",
            "running": bool(self.bot.running),
            "session": {
                "started_at_epoch": started,
                "duration_seconds": round(duration_seconds, 2),
                "duration": self._format_live_proof_duration(duration_seconds),
                "recoveries": self.bot.session_recovery_count,
                "recovery_failures": self.bot.recovery_failures,
                "god_rolls": self.bot.session_god_rolls,
                "near_misses": self.bot.session_near_misses,
                "last_event": self.bot.last_important_event,
            },
            "targets": self._live_proof_target_summary(),
            "decision_chain": dict(self.bot.last_decision_chain or {}),
            "decision_chain_text": self.format_decision_chain(),
            "shards": self._live_proof_shard_summary(),
            "timings": list(getattr(self.bot, "recent_timing_events", [])[-40:]),
            "auto_checkbox": self.bot.auto_checkbox_session_summary(),
            "verification_cache": dict(getattr(self.bot, "last_verification_cache_stats", {}) or {}),
            "route_budget_timings": list(getattr(self.bot, "recent_route_budget_events", [])[-20:]),
            "route_snapshots": {
                "startup": dict(getattr(self.bot, "last_startup_route_snapshot", {}) or {}),
                "recovery": dict(getattr(self.bot, "last_recovery_route_snapshot", {}) or {}),
            },
            "recent_operator_events": operator_events,
            "recent_logs": recent_logs,
            "recent_history": {
                "god_rolls": [asdict(row) for row in self.god_rolls[-10:]],
                "near_misses": [asdict(row) for row in self.near_misses[-10:]],
            },
            "settings": {
                "roll_domain": self.settings.get("roll_domain"),
                "preset": self.settings.get("preset"),
                "webhook_configured": bool(str(self.settings.get("webhook_url", "")).strip()),
                "stats_region": self.settings.get("stats_region"),
                "powers_preview_region": (self.settings.get("powers_layout") or {}).get("preview_region"),
                "passive_shard_region": self.settings.get("passive_shard_region"),
                "power_shard_region": self.settings.get("power_shard_region"),
            },
        }

    def macro_health_summary(self) -> dict:
        startup = dict(getattr(self.bot, "last_startup_route_snapshot", {}) or {})
        recovery = dict(getattr(self.bot, "last_recovery_route_snapshot", {}) or {})
        auto_checkbox = self.bot.auto_checkbox_session_summary()
        latest_checkbox = dict(auto_checkbox.get("latest_classifier") or {})
        cache = dict(getattr(self.bot, "last_verification_cache_stats", {}) or {})
        budgets = list(getattr(self.bot, "recent_route_budget_events", [])[-20:])
        timings = list(getattr(self.bot, "recent_timing_events", [])[-40:])
        latest_verify = budgets[-1] if budgets else (timings[-1] if timings else {})
        startup_route = startup.get("route_reason") or startup.get("route") or "none"
        recovery_route = recovery.get("route_reason") or recovery.get("result") or "none"
        checkbox_state = latest_checkbox.get("effective_state") or latest_checkbox.get("state") or "unknown"
        checkbox_confidence = latest_checkbox.get("confidence") or "unknown"
        return {
            "startup_route": startup_route,
            "recovery_route": recovery_route,
            "auto_checkbox": {
                "state": checkbox_state,
                "confidence": checkbox_confidence,
                "ambiguous_reads": auto_checkbox.get("ambiguous_reads", 0),
                "reads": auto_checkbox.get("reads", 0),
            },
            "latest_verify": latest_verify,
            "verification_cache": cache,
            "route_budget_timings": budgets,
            "route_snapshots": {"startup": startup, "recovery": recovery},
        }

    @staticmethod
    def _proof_text(value) -> str:
        text = str(value or "")
        replacements = {
            "\u00e2\u20ac\u00a6": "\u2026",
            "\u00e2\u20ac\u201d": "-",
            "\u00e2\u20ac\u201c": "-",
            "\u00e2\u20ac\u02dc": "'",
            "\u00e2\u20ac\u2122": "'",
            "\u00e2\u20ac\u0153": '"',
            "\u00e2\u20ac\ufffd": '"',
        }
        for broken, fixed in replacements.items():
            text = text.replace(broken, fixed)
        return text

    def _render_live_proof_markdown(self, payload: dict) -> str:
        session = payload["session"]
        shards = payload["shards"]
        auto_checkbox = payload.get("auto_checkbox") or {}
        latest_checkbox = auto_checkbox.get("latest_classifier") or {}
        lines = [
            f"# {APP_DISPLAY_NAME} Live Proof Pack",
            "",
            f"- Trigger: {payload['trigger']}",
            f"- Generated: {payload['generated_at']}",
            f"- Active domain: {payload['active_domain']}",
            f"- Running at export: {payload['running']}",
            f"- Session duration: {session['duration']}",
            f"- Recoveries: {session['recoveries']} ({session['recovery_failures']} failures)",
            f"- Kept rolls: {session['god_rolls']}",
            f"- Near misses: {session['near_misses']}",
            f"- Last event: {self._proof_text(session['last_event']) or 'unknown'}",
            "",
            "## Targets",
        ]
        targets = [self._proof_text(item) for item in (payload.get("targets") or [])]
        lines.extend(f"- {item}" for item in targets)
        if not targets:
            lines.append("- No active target summary available")

        lines.extend(
            [
                "",
                "## Shards",
                f"- Passive: {shards['passive']['current_formatted']} | {shards['passive']['session']}",
                f"- Power: {shards['power']['current_formatted']} | {shards['power']['session']}",
                "",
                "## Last Decision Chain",
                "```text",
                self._proof_text(payload.get("decision_chain_text")) or "No decisions recorded yet.",
                "```",
                "",
                "## Recent Timings",
            ]
        )
        timings = payload.get("timings") or []
        if timings:
            for event in timings[-12:]:
                name = event.get("name", "timing")
                elapsed = event.get("elapsed_ms", 0)
                result = event.get("result", "")
                context = event.get("context") or event.get("tasks") or event.get("domain") or ""
                suffix = f" | {result}" if result else ""
                context_text = f" | {context}" if context else ""
                lines.append(f"- {name}: {elapsed}ms{suffix}{context_text}")
        else:
            lines.append("- No timing events recorded.")

        lines.extend(
            [
                "",
                "## Auto Checkbox",
                (
                    f"- Reads: {auto_checkbox.get('reads', 0)} | "
                    f"Ambiguous: {auto_checkbox.get('ambiguous_reads', 0)} | "
                    f"Manual reroll direct recovery clicks: "
                    f"{auto_checkbox.get('manual_reroll_direct_recovery_clicks', 0)}"
                ),
            ]
        )
        if latest_checkbox:
            lines.append(
                "- Latest classifier: "
                f"{latest_checkbox.get('state', 'unknown')} "
                f"({latest_checkbox.get('confidence', 'unknown')}) | "
                f"{self._proof_text(latest_checkbox.get('context', 'unknown'))}"
            )
        else:
            lines.append("- Latest classifier: none recorded.")

        route_snapshots = payload.get("route_snapshots") or {}
        verification_cache = payload.get("verification_cache") or {}
        route_budget_timings = payload.get("route_budget_timings") or []
        lines.extend(
            [
                "",
                "## Recovery Visibility",
                (
                    "- Startup route: "
                    f"{self._proof_text((route_snapshots.get('startup') or {}).get('route_reason') or (route_snapshots.get('startup') or {}).get('route') or 'none')}"
                ),
                (
                    "- Recovery route: "
                    f"{self._proof_text((route_snapshots.get('recovery') or {}).get('route_reason') or (route_snapshots.get('recovery') or {}).get('result') or 'none')}"
                ),
                (
                    "- Verification cache: "
                    f"hits={verification_cache.get('cache_hits', 0)} | "
                    f"misses={verification_cache.get('cache_misses', 0)} | "
                    f"polls={verification_cache.get('polls_seen', 0)}/{verification_cache.get('polls_planned', 0)}"
                ),
            ]
        )
        if route_budget_timings:
            event = route_budget_timings[-1]
            lines.append(
                "- Latest verify budget: "
                f"{event.get('name', 'verify')} | {event.get('elapsed_ms', 0)}ms | "
                f"{event.get('result', 'unknown')} | {self._proof_text(event.get('reason', 'none'))}"
            )
        else:
            lines.append("- Latest verify budget: none recorded.")

        lines.extend(
            [
                "",
                "## Recent Operator Events",
            ]
        )
        operator_events = payload.get("recent_operator_events") or []
        if operator_events:
            for entry in operator_events[-20:]:
                event_text = self._proof_text(entry.get("summary") or entry.get("message") or "")
                lines.append(f"- {entry.get('time', '')} [{entry.get('category', 'RUNTIME')}] {event_text}")
        else:
            lines.append("- No operator-visible events recorded.")

        lines.extend(["", "## Recent History"])
        history = payload.get("recent_history") or {}
        god_rolls = history.get("god_rolls") or []
        near_misses = history.get("near_misses") or []
        lines.append(f"- Recent kept rolls: {len(god_rolls)}")
        lines.append(f"- Recent near misses: {len(near_misses)}")
        return "\n".join(lines) + "\n"

    def export_live_proof_pack(self, trigger: str = "manual") -> str:
        safe_trigger = self._safe_artifact_label(trigger, "manual")
        domain = self._safe_artifact_label(self.settings.get("roll_domain", "specs"), "specs")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        version_prefix = self._safe_artifact_label(APP_VERSION, "vunknown")
        LIVE_PROOF_DIR.mkdir(parents=True, exist_ok=True)
        folder = self._unique_folder(LIVE_PROOF_DIR, f"{version_prefix}_{stamp}_{safe_trigger}_{domain}")
        folder.mkdir(parents=True, exist_ok=False)

        payload = self._live_proof_payload(safe_trigger)
        payload["folder"] = str(folder)
        (folder / "proof.json").write_text(json.dumps(payload, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
        (folder / "proof.md").write_text(self._render_live_proof_markdown(payload), encoding="utf-8")
        self._bot_log(f"Live proof pack exported: {folder}")
        return str(folder)

    def test_popup_detection(self, settings: dict | None = None) -> bool:
        if settings is not None:
            self.apply_settings(settings, save=False, announce=False)
        active = self.bot.popup_active(log=True, context="manual popup test")
        self._bot_log(f"Manual popup detection result: {'active' if active else 'not detected'}")
        self.decision_chain_changed.emit(self.format_decision_chain())
        return active

    def test_current_roll_classification(self, settings: dict | None = None) -> tuple:
        if settings is not None:
            self.apply_settings(settings, save=False, announce=False)
        state, trait, summary, _ocr_text, missing, near = self.bot.check_roll()
        self._bot_log(
            "Manual current roll classification | "
            f"state={state} trait={display_trait(trait) if trait else 'unknown'} "
            f"near={near} summary={summary or '<empty>'} "
            f"missing={' ; '.join(missing) if missing else 'none'}"
        )
        self.decision_chain_changed.emit(self.format_decision_chain())
        return state, trait, summary, missing, near

    def load_preset_rules(self, name: str) -> dict:
        return sanitize_rules(PRESET_RULES.get(name, DEFAULT_REAL_RULES))

    def preview_ocr(self, region_text: str) -> dict:
        region = parse_region(region_text)
        if bot_module.pyautogui is None:
            raise RuntimeError("pyautogui is not installed. Install dependencies and try again.")
        img = bot_module.pyautogui.screenshot(region=region)
        candidates = self.bot.get_stats_ocr_candidates(image=img, region=region)
        attempts = []

        if self.bot.roll_domain == "powers":
            fallback_candidates = self.bot.get_stats_ocr_candidates(image=img, region=region, fallback_only=True)
            combined_candidates = candidates + (fallback_candidates or [])
            parsed, fallback_text = self.bot._parse_power_candidates(combined_candidates)
            for engine, text, raw_text in [self.bot._unpack_ocr_candidate(candidate) for candidate in combined_candidates[:6]]:
                attempts.append(f"{engine}\n{text}\nRaw: {raw_text}")
            trait = parsed["power"] if parsed else ("non_target_power" if fallback_text else "")
            merged_text = (
                summarize_power_values(trait, parsed["values"], parsed.get("passive"))
                if parsed
                else ("Unsupported or filler power observed" if fallback_text else "")
            )
            return {
                "image": img,
                "attempts": "\n\n".join(attempts),
                "trait": display_trait(trait) if trait else "",
                "merged": merged_text,
            }

        parsed = self.bot._parse_stat_ocr_candidates(candidates, bad_panel_words=[])
        if self.bot._parsed_needs_fallback(parsed):
            fallback_candidates = self.bot.get_stats_ocr_candidates(image=img, region=region, fallback_only=True)
            if fallback_candidates:
                parsed = self.bot._parse_stat_ocr_candidates(candidates + fallback_candidates, bad_panel_words=[])
        trait = parsed["trait"]
        merged = parsed["merged_values"] if trait else []
        merged_text = self.bot.build_summary_from_labeled(trait, merged) if trait and merged else ""
        for item in parsed.get("parsed", [])[:6]:
            attempts.append(
                f"{item['engine']} | quality {item['quality']}\n"
                f"{item['text']}\n"
                f"Values: {dict(zip(bot_module.STAT_LABELS.get(trait, []), item['values']))}"
            )
        return {
            "image": img,
            "attempts": "\n\n".join(attempts),
            "trait": display_trait(trait) if trait else "",
            "merged": merged_text,
        }

    def preview_passive_shards(self, region_text: str) -> dict:
        region = parse_optional_region(region_text)
        if region == (0, 0, 0, 0):
            raise ValueError("Passive shard region is not set.")
        if bot_module.pyautogui is None:
            raise RuntimeError("pyautogui is not installed. Install dependencies and try again.")

        result = self.bot.passive_shard_ocr_attempts(region=region)
        attempts = result["attempts"]
        raw_text = "\n".join(
            attempt["raw"]
            for attempt in attempts
            if attempt["raw"] and not str(attempt["raw"]).startswith("<error:")
        )
        parsed, cleaned = parse_passive_shard_count(
            raw_text,
            self.bot.last_passive_shards,
            infer_missing_suffix=True,
        )
        return {
            "raw_image": result["image"],
            "processed_image": result["processed_image"],
            "attempts": [(attempt["mode"], attempt["psm"], attempt["raw"]) for attempt in attempts],
            "raw_text": raw_text,
            "cleaned": cleaned,
            "parsed": parsed,
            "formatted": format_shard_count(parsed) if parsed is not None else "not found",
        }

    def preview_power_shards(self, region_text: str) -> dict:
        region = parse_optional_region(region_text)
        if region == (0, 0, 0, 0):
            raise ValueError("Power shard region is not set.")
        if bot_module.pyautogui is None:
            raise RuntimeError("pyautogui is not installed. Install dependencies and try again.")

        result = self.bot.power_shard_ocr_attempts(region=region)
        attempts = result["attempts"]
        raw_text = "\n".join(
            attempt["raw"]
            for attempt in attempts
            if attempt["raw"] and not str(attempt["raw"]).startswith("<error:")
        )
        parsed, cleaned = parse_power_shard_count(
            raw_text,
            self.bot.last_power_shards,
            infer_missing_suffix=True,
        )
        return {
            "raw_image": result["image"],
            "processed_image": result["processed_image"],
            "attempts": [(attempt["mode"], attempt["psm"], attempt["raw"]) for attempt in attempts],
            "raw_text": raw_text,
            "cleaned": cleaned,
            "parsed": parsed,
            "formatted": format_shard_count(parsed) if parsed is not None else "not found",
        }

    def capture_mouse_position(self) -> tuple[int, int]:
        if bot_module.pyautogui is None:
            raise RuntimeError("pyautogui is not installed. Install dependencies and try again.")
        pos = bot_module.pyautogui.position()
        return int(pos.x), int(pos.y)

    def update_coord(self, name: str, point: tuple[int, int]):
        data = self.normalize_settings(self.settings)
        data["coords"][name] = format_point(point)
        self.apply_settings(data)

    def update_stats_region(self, region: tuple[int, int, int, int]):
        data = self.normalize_settings(self.settings)
        data["stats_region"] = format_region(region)
        self.apply_settings(data)

    def save_settings(self):
        try:
            self.settings = self.normalize_settings(self.settings)
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self.settings, indent=2), encoding="utf-8")
        except Exception as e:
            self._bot_log(f"Could not save settings: {e}")

    def load_settings(self):
        settings_source = SETTINGS_FILE
        if not settings_source.exists() and LEGACY_SETTINGS_FILE.exists():
            settings_source = LEGACY_SETTINGS_FILE
        if not settings_source.exists():
            self.settings = self.normalize_settings(default_settings())
            self.save_settings()
            self._bot_log("Settings file missing. Fresh default settings created.")
            return
        try:
            raw = json.loads(settings_source.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("Settings file must contain a JSON object.")

            old_version = str(raw.get("settings_version", "")).strip()
            if old_version != CURRENT_SETTINGS_VERSION:
                backup = self._backup_settings_file("legacy", source_path=settings_source)
                self.settings = self.migrate_legacy_settings(raw)
                self.save_settings()
                source = old_version or "missing"
                self._bot_log(f"Settings migrated from version {source} to {CURRENT_SETTINGS_VERSION}.")
                self._bot_log("Settings reset to clean defaults; safe compatible fields were migrated.")
                if backup:
                    self._bot_log(f"Backup file created: {backup}")
                return

            had_removed_keys = any(key in raw for key in REMOVED_SETTINGS_KEYS)
            self.settings = self.normalize_settings(raw)
            if had_removed_keys:
                self.save_settings()
                self._bot_log("Removed obsolete settings keys from current settings.")
            self._bot_log(f"Settings loaded successfully. Source: {settings_source}")
            if settings_source != SETTINGS_FILE:
                self.save_settings()
                self._bot_log(f"Settings migrated to preferred config path: {SETTINGS_FILE}")
        except Exception as e:
            backup = self._backup_settings_file("invalid", source_path=settings_source)
            self.settings = self.normalize_settings(default_settings())
            self.save_settings()
            self._bot_log(f"Settings reset to defaults after load failure: {e}")
            if backup:
                self._bot_log(f"Backup file created: {backup}")

    def reset_settings(self) -> Path | None:
        backup = self._backup_settings_file("manual")
        self.settings = self.normalize_settings(default_settings())
        self.apply_settings(self.settings, save=True, announce=False)
        if backup:
            self._bot_log(f"Manual settings reset complete. Backup file created: {backup}")
        else:
            self._bot_log("Manual settings reset complete. Fresh default settings created.")
        return backup

    def _backup_settings_file(self, reason: str, source_path: Path | None = None) -> Path | None:
        source = Path(source_path) if source_path is not None else SETTINGS_FILE
        if not source.exists():
            return None
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup = CONFIG_BACKUP_DIR / f"{SETTINGS_FILE.stem}.{reason}_backup_{timestamp}{SETTINGS_FILE.suffix}"
        try:
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup)
            return backup
        except Exception as e:
            self._bot_log(f"Could not back up settings file: {e}")
            return None

    def save_history(self):
        try:
            HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            NEAR_MISS_FILE.parent.mkdir(parents=True, exist_ok=True)
            HISTORY_FILE.write_text(
                json.dumps([asdict(entry) for entry in self.god_rolls], indent=2),
                encoding="utf-8",
            )
            NEAR_MISS_FILE.write_text(
                json.dumps([asdict(entry) for entry in self.near_misses], indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            self._bot_log(f"Could not save history: {e}")

    def load_history(self):
        history_path = HISTORY_FILE if HISTORY_FILE.exists() or not LEGACY_HISTORY_FILE.exists() else LEGACY_HISTORY_FILE
        near_miss_path = NEAR_MISS_FILE if NEAR_MISS_FILE.exists() or not LEGACY_NEAR_MISS_FILE.exists() else LEGACY_NEAR_MISS_FILE
        self.god_rolls = self._load_god_rolls(history_path)
        self.near_misses = self._load_near_misses(near_miss_path)
        if history_path != HISTORY_FILE or near_miss_path != NEAR_MISS_FILE:
            self.save_history()
            self._bot_log("History migrated to preferred output/json paths.")
        self.history_loaded.emit(list(self.god_rolls), list(self.near_misses))

    def save_logs(self):
        try:
            LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            LOG_FILE.write_text(json.dumps(self.logs, indent=2), encoding="utf-8")
        except Exception:
            pass

    def load_logs(self):
        log_source = LOG_FILE if LOG_FILE.exists() or not LEGACY_RUNTIME_LOG_FILE.exists() else LEGACY_RUNTIME_LOG_FILE
        if not log_source.exists():
            return
        try:
            data = json.loads(log_source.read_text(encoding="utf-8"))
            if isinstance(data, list):
                normalized = []
                for item in data[-1000:]:
                    entry = normalize_log_entry(item)
                    if entry is not None:
                        normalized.append(entry)
                self.logs = normalized[-1000:]
                if log_source != LOG_FILE or any("category" not in item for item in data if isinstance(item, dict)):
                    self.save_logs()
        except Exception:
            self.logs = []

    def cleanup_old_runtime_log_backups(self):
        cleaned = 0
        failed = 0
        try:
            candidates = list(LOG_FILE.parent.glob(f"{LOG_FILE.stem}.*.bak{LOG_FILE.suffix}"))
        except Exception:
            candidates = []
        for path in candidates:
            try:
                if path == LOG_FILE or not path.is_file():
                    continue
                path.unlink()
                cleaned += 1
            except Exception:
                failed += 1
        if cleaned:
            message = f"Cleaned {cleaned} old runtime backup log{'s' if cleaned != 1 else ''}"
            if failed:
                message += f"; {failed} could not be removed"
            self._bot_log(message)
        elif failed:
            self._bot_log(f"Runtime backup log cleanup skipped {failed} file{'s' if failed != 1 else ''} due to deletion errors")
        else:
            self._bot_log("No old runtime backup logs found")
        return {"cleaned": cleaned, "failed": failed}

    def clean_debug_artifacts(self):
        runtime_logs = 0
        try:
            if LOG_FILE.exists():
                backup = LOG_FILE.with_name(f"{LOG_FILE.stem}.{time.strftime('%Y%m%d_%H%M%S')}.bak{LOG_FILE.suffix}")
                LOG_FILE.replace(backup)
                runtime_logs = 1
                self.logs = []
                self._last_log_save = 0.0
        except Exception:
            runtime_logs = 0
        cleared = self.bot.clean_debug_artifacts()
        self._bot_log(
            "Startup cleanup cleared "
            f"{cleared.get('ocr_debug_files', 0)} OCR debug files, "
            f"{cleared.get('ocr_debug_logs', 0)} OCR debug logs, "
            f"{cleared.get('debug_screenshots', 0)} debug screenshots, "
            f"and rotated {runtime_logs} runtime log"
        )

    def recent_log_entries(self, limit: int = 120, *, operator_only: bool = False) -> list[dict]:
        entries = list(self.logs[-max(0, int(limit)):])
        if operator_only:
            entries = [entry for entry in entries if entry.get("operator_visible")]
        return [dict(entry) for entry in entries]

    def format_decision_chain(self) -> str:
        data = dict(self.bot.last_decision_chain or {})
        if not data:
            return "No decisions recorded yet."

        def value(key, default="-"):
            item = data.get(key, default)
            if isinstance(item, dict):
                return json.dumps(item, ensure_ascii=True, default=str)
            if isinstance(item, list):
                return json.dumps(item, ensure_ascii=True, default=str)
            return str(item)

        lines = [
            f"Time: {value('time')}",
            f"Subsystem: {value('subsystem')}",
            f"Classification: {value('classification')} | Reason: {value('classification_reason')}",
            f"Trait: {value('current_trait', value('ocr_trait', value('last_trait')))}",
            f"Values: {value('parsed_values', value('merged_values'))}",
            f"OCR: {value('ocr_source')} | {value('ocr_selection_reason')} | candidates={value('ocr_candidate_count')}",
            f"Recovery: {value('recovery_state')} | {value('recovery_reason', value('last_recovery_reason'))}",
            f"Popup: {value('popup_active')} | context={value('popup_context')}",
            f"Shards: {value('shard_result')} | {value('shard_reason')}",
            f"Last action/event: {value('last_event')}",
        ]
        return "\n".join(lines)

    def _load_json_list(self, path: Path) -> list:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _load_god_rolls(self, path: Path) -> list[GodRollEntry]:
        entries = []
        for item in self._load_json_list(path):
            if isinstance(item, dict):
                entries.append(
                    GodRollEntry(
                        time=str(item.get("time", "")),
                        spec=str(item.get("spec", "")),
                        rolled=str(item.get("rolled", "")),
                        screenshot_path=str(item.get("screenshot_path", "")),
                        webhook_sent=bool(item.get("webhook_sent", False)),
                    )
                )
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                entries.append(GodRollEntry(str(item[0]), str(item[1]), str(item[2])))
        return entries

    def _load_near_misses(self, path: Path) -> list[NearMissEntry]:
        entries = []
        for item in self._load_json_list(path):
            if isinstance(item, dict):
                values = {k: item.get(k, "") for k in NearMissEntry.__dataclass_fields__}
                entries.append(NearMissEntry(**values))
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                entries.append(NearMissEntry(str(item[0]), str(item[1]), str(item[2])))
        return entries

    def clear_history(self, kind: str):
        if kind == "god":
            self.god_rolls.clear()
        elif kind == "near":
            self.near_misses.clear()
        else:
            self.god_rolls.clear()
            self.near_misses.clear()
        self.save_history()
        self.history_loaded.emit(list(self.god_rolls), list(self.near_misses))

    def export_history(self, path: str, kind: str):
        target = Path(path)
        rows = self.god_rolls if kind == "god" else self.near_misses
        payload = [asdict(row) for row in rows]
        if target.suffix.lower() == ".json":
            target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            return

        if not payload:
            target.write_text("", encoding="utf-8")
            return

        with target.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(payload[0].keys()))
            writer.writeheader()
            writer.writerows(payload)

    @property
    def capture_dir(self) -> Path:
        CAPTURE_DIR.mkdir(exist_ok=True)
        return CAPTURE_DIR
