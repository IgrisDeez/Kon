from __future__ import annotations

import re
from pathlib import Path

APP_DATA_DIR = Path.cwd()
CONFIG_DIR = APP_DATA_DIR / "config"
CONFIG_BACKUP_DIR = CONFIG_DIR / "backups"
OUTPUT_DIR = APP_DATA_DIR / "output"
LOG_DIR = OUTPUT_DIR / "logs"
JSON_DIR = OUTPUT_DIR / "json"
CAPTURE_DIR = OUTPUT_DIR / "captures"
OCR_DEBUG_DIR = OUTPUT_DIR / "ocr"
DIAGNOSTIC_DIR = OUTPUT_DIR / "diagnostics"

LEGACY_LOG_DIR = APP_DATA_DIR / "logs"
LEGACY_JSON_DIR = APP_DATA_DIR / "json"
LEGACY_CAPTURE_DIR = APP_DATA_DIR / "godroll_captures"
LEGACY_OCR_DEBUG_DIR = APP_DATA_DIR / "ocr_debug_crops"
LEGACY_DIAGNOSTIC_DIR = APP_DATA_DIR / "diagnostic_snapshots"

SETTINGS_FILE = CONFIG_DIR / "aelrith_forge_settings.json"
HISTORY_FILE = JSON_DIR / "aelrith_forge_history.json"
NEAR_MISS_FILE = JSON_DIR / "aelrith_forge_near_misses.json"
RUNTIME_LOG_FILE = LOG_DIR / "aelrith_forge_logs.json"

LEGACY_SETTINGS_FILE = LEGACY_JSON_DIR / "aelrith_forge_settings.json"
LEGACY_HISTORY_FILE = LEGACY_JSON_DIR / "aelrith_forge_history.json"
LEGACY_NEAR_MISS_FILE = LEGACY_JSON_DIR / "aelrith_forge_near_misses.json"
LEGACY_RUNTIME_LOG_FILE = LEGACY_LOG_DIR / "aelrith_forge_logs.json"


def ensure_app_dirs() -> None:
    for directory in (
        CONFIG_DIR,
        CONFIG_BACKUP_DIR,
        OUTPUT_DIR,
        LOG_DIR,
        JSON_DIR,
        CAPTURE_DIR,
        OCR_DEBUG_DIR,
        DIAGNOSTIC_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def build_ocr_debug_log_file(version_text: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(version_text or "vunknown"))
    return OCR_DEBUG_DIR / f"aelrith_forge_{safe}_ocr_debug.jsonl"
