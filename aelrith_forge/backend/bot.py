from __future__ import annotations

import difflib
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from .. import APP_DISPLAY_NAME, APP_VERSION, STARTUP_LOGIC_VERSION
from .paths import (
    APP_DATA_DIR,
    CAPTURE_DIR,
    DIAGNOSTIC_DIR,
    HISTORY_FILE,
    JSON_DIR,
    LOG_DIR,
    NEAR_MISS_FILE,
    OCR_DEBUG_DIR,
    SETTINGS_FILE,
    build_ocr_debug_log_file,
    ensure_app_dirs,
)
from .normalization import canonical_stat_key, normalize_ocr_text, normalize_stat_tokens
from .powers import (
    POWER_DISPLAY_NAMES,
    SUPPORTED_POWER_DEFINITIONS,
    default_power_settings,
    evaluate_power,
    parse_power_roll_text,
    power_display_name,
    power_near_miss,
    power_score,
    sanitize_power_rules,
    summarize_power_values,
)

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    import pydirectinput
except Exception:
    pydirectinput = None

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import requests
except Exception:
    requests = None

try:
    import numpy as np
except Exception:
    np = None

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except Exception:
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None

try:
    import cv2
except Exception:
    cv2 = None

if pytesseract is not None:
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if pyautogui is not None:
    pyautogui.FAILSAFE = True

ensure_app_dirs()
ARTIFACT_VERSION_PREFIX = re.sub(r"[^a-zA-Z0-9._-]+", "_", APP_VERSION)
OCR_DEBUG_LOG_FILE = build_ocr_debug_log_file(ARTIFACT_VERSION_PREFIX)

SUPPORTED_SPEC_TRAITS = ("fortune", "executioner", "rampage")
LEGACY_SPEC_TRAIT_ALIASES = {
    "chosen": "fortune",
    "fortune_chosen": "fortune",
    "fortune chosen": "fortune",
}

TRAIT_ALIASES = {
    "fortune": ["fortune chosen", "fortunechosen", "fortune", "fortu", "urtune", "furtune", "borturne", "chosen", "chosem", "lhosen", "lhoser"],
    "executioner": ["executioner", "executione", "xecutioner", "execut", "lxecut", "edee"],
    "rampage": ["rampage", "ranpage", "fanpage", "ra mpage", "rarnpage", "rgxaga", "rxaga", "ragaga", "aterany"],
}

ROLLABLE_NON_TARGET_TRAIT_ALIASES = {
    "vigor": ["vigor", "vigour"],
    "range": ["range"],
    "swift": ["swift"],
    "scholar": ["scholar"],
    "marksman": ["marksman", "markman"],
    "deadeye": ["deadeye", "dead eye"],
    "ethereal": ["ethereal", "etheral"],
    "solar": ["solar"],
    "monarch": ["monarch"],
    "blitz": ["blitz"],
}

TYPO_MAP = {
    "borturne": "fortune",
    "fortu": "fortune",
    "urtune": "fortune",
    "furtune": "fortune",
    "lhosen": "fortune",
    "lhoser": "fortune",
    "chosem": "fortune",
    "edee": "executioner",
    "lxecut": "executioner",
    "execut": "executioner",
    "executione": "executioner",
    "xecutioner": "executioner",
    "executionar": "executioner",
    "exccutioner": "executioner",
    "below50": "below 50",
    "ranpage": "rampage",
    "fanpage": "rampage",
    "ra mpage": "rampage",
    "rarnpage": "rampage",
    "rgxaga": "rampage",
    "rxaga": "rampage",
    "ragaga": "rampage",
    "aterany": "rampage",
    "danage": "damage",
    "erit": "crit",
    "erit rate": "crit rate",
    "erit chance": "crit chance",
    "ait ance": "crit chance",
    "ait chance": "crit chance",
    "ait cance": "crit chance",
    "ait oance": "crit chance",
    "ait onance": "crit chance",
    "uit ance": "crit chance",
    "uit chance": "crit chance",
    "uit cance": "crit chance",
    "uit oance": "crit chance",
    "uit onance": "crit chance",
    "fortunene": "fortune",
    "fortunene chosen": "fortune chosen",
    "orop": "drop",
    "oror": "drop",
    "drap": "drop",
    "crop": "drop",
    "luek": "luck",
    "iuck": "luck",
    "lack": "luck",
    "git chance": "crit chance",
    "git clance": "crit chance",
    "cit chance": "crit chance",
    "cit clance": "crit chance",
    "ccrit chance": "crit chance",
    "crit oance": "crit chance",
    "crit cance": "crit chance",
    "ert chanice": "crit chance",
    "bmcaitchance": "crit chance",
    "qit chance": "crit chance",
    "dit chance": "crit chance",
    "git damage": "crit damage",
    "qit damage": "crit damage",
    "crit darmaee": "crit damage",
    "crit darmage": "crit damage",
    "crit danmage": "crit damage",
    "eit dantige": "crit damage",
    "gtdakige": "crit damage",
    "darmaee": "damage",
    "coibo": "combo",
    "ratupage": "rampage",
    "ruzaga": "rampage",
    "cobo": "combo",
}


def canonical_spec_trait(trait: str | None) -> str | None:
    if not trait:
        return None
    key = normalize_ocr_text(str(trait)).replace(" ", "_")
    if key in SUPPORTED_SPEC_TRAITS:
        return key
    return LEGACY_SPEC_TRAIT_ALIASES.get(key)


def is_supported_spec_trait(trait: str | None) -> bool:
    return canonical_spec_trait(trait) in SUPPORTED_SPEC_TRAITS

DEFAULT_REAL_RULES = {
    "fortune": [(29.0, 30.0), (9.0, 10.0)],
    "chosen": [(29.0, 30.0), (9.0, 10.0)],
    "executioner": [(44.0, 45.0), (3.0, 4.0), (14.0, 15.0)],
    "rampage": [(15.0, 30.0), (29.0, 30.0), (3.0, 4.0), (9.0, 10.0)],
}

DEFAULT_TEST_RULES = {
    "fortune": [(20.0, 30.0), (5.0, 10.0)],
    "chosen": [(20.0, 30.0), (5.0, 10.0)],
    "executioner": [(30.0, 45.0), (1.0, 4.0), (8.0, 15.0)],
    "rampage": [(10.0, 30.0), (20.0, 30.0), (1.0, 4.0), (5.0, 10.0)],
}

PRESET_RULES = {
    "Default": DEFAULT_REAL_RULES,
    "Strict": {
        "fortune": [(29.5, 30.0), (9.0, 10.0)],
        "chosen": [(29.5, 30.0), (9.0, 10.0)],
        "executioner": [(43.9, 45.0), (3.0, 4.0), (14.0, 15.0)],
        "rampage": [(15.0, 30.0), (29.0, 30.0), (3.0, 4.0), (9.0, 10.0)],
    },
    "Test Easy": DEFAULT_TEST_RULES,
}

STAT_LABELS = {
    "fortune": ["Drop", "Luck"],
    "chosen": ["Drop", "Luck"],
    "executioner": ["NPC DMG", "Crit Chance", "Crit Damage"],
    "rampage": ["Combo Ramp", "Damage", "Crit Rate", "Crit Damage"],
}

STAT_CAPS = {
    "fortune": [30.0, 10.0],
    "chosen": [30.0, 10.0],
    "executioner": [45.0, 4.0, 15.0],
    "rampage": [30.0, 30.0, 4.0, 10.0],
}

STARTUP_CONFIRMED_ROLLING = "confirmed_rolling"
STARTUP_POPUP_CLEARED_AND_RESUMED = "popup_cleared_and_resumed"
STARTUP_CURRENT_SPEC_BAD_REROLLED_THEN_ROLLING = "current_spec_bad_rerolled_then_rolling"
STARTUP_FAILED_UNCERTAIN_AUTO_STATE = "failed_uncertain_auto_state"
STARTUP_FAILED_NO_ROLL_DETECTED = "failed_no_roll_detected"
STARTUP_FAILED_UNREADABLE_UI = "failed_unreadable_ui"
STARTUP_FAILED_TIMEOUT = "failed_timeout"
STARTUP_STOPPED_ON_CURRENT_SPEC = "stopped_on_current_spec"

AUTO_UNCERTAIN_CLICK_RESULTS = (
    "clicked_uncertain",
    "clicked_uncertain_validated",
    "clicked_uncertain_restored",
    "clicked_uncertain_rolled_back",
)
AUTO_ENABLE_CLICK_RESULTS = (
    "clicked",
    "startup_fallback_clicked",
    "clicked_uncertain",
    "clicked_uncertain_validated",
    "clicked_uncertain_restored",
)
AUTO_UNSAFE_RESUME_RESULTS = (
    "uncertain",
    "clicked_uncertain",
    "clicked_uncertain_restored",
    "clicked_uncertain_rolled_back",
)

SPEC_DISPLAY_NAMES = {
    "fortune": "Fortune Chosen",
    "chosen": "Fortune Chosen",
    "executioner": "Executioner",
    "rampage": "Rampage",
    "vigor": "Vigor",
    "range": "Range",
    "swift": "Swift",
    "scholar": "Scholar",
    "marksman": "Marksman",
    "deadeye": "Deadeye",
    "ethereal": "Ethereal",
    "solar": "Solar",
    "monarch": "Monarch",
    "blitz": "Blitz",
    "non_target": "Non-target Roll",
}

DEFAULT_CONFIG = {
    "AUTO_CHECKBOX": (1210, 629),
    "ROLL_BUTTON": (1112, 676),
    "YES_BUTTON": (894, 554),
    "STATS_REGION": (920, 520, 320, 85),
    "POPUP_REGION": (760, 485, 400, 70),
    "PROTECTED_REGION": (300, 300, 1300, 150),
    "PASSIVE_SHARD_REGION": (0, 0, 0, 0),
    "PASSIVE_SHARD_ALERTS": True,
    "PASSIVE_SHARD_REPORT_INTERVAL": 600,
    "PASSIVE_SHARD_LOW_THRESHOLD": 10_000,
    "PASSIVE_SHARD_VERY_LOW_THRESHOLD": 5_000,
    "PASSIVE_SHARD_CRITICAL_THRESHOLD": 1_000,
    "PASSIVE_SHARD_EMPTY_THRESHOLD": 0,
    "PASSIVE_SHARD_ALERT_COOLDOWN": 1800,
    "STOP_ON_EMPTY_PASSIVE_SHARDS": True,
    "POWER_SHARD_REGION": (0, 0, 0, 0),
    "POWER_SHARD_ALERTS": True,
    "POWER_SHARD_REPORT_INTERVAL": 600,
    "POWER_SHARD_LOW_THRESHOLD": 10_000,
    "POWER_SHARD_VERY_LOW_THRESHOLD": 5_000,
    "POWER_SHARD_CRITICAL_THRESHOLD": 1_000,
    "POWER_SHARD_EMPTY_THRESHOLD": 0,
    "POWER_SHARD_ALERT_COOLDOWN": 1800,
    "STOP_ON_EMPTY_POWER_SHARDS": True,
    "OCR_UPSCALE": 3,
    "TESSERACT_STAT_WHITELIST": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.%:,+->",
    "OCR_CACHE_TTL": 1.25,
    "OCR_UNCHANGED_BACKOFF": 0.35,
    "OCR_DEBUG_VERBOSE": False,
    "OCR_DEBUG_FILE": True,
    "OCR_DEBUG_CAPTURE_ON_FAIL": True,
    "OCR_DEBUG_MAX_FILES": 80,
    "CLEAN_DEBUG_ARTIFACTS_ON_START": False,
    "AUTO_CAPTURE_DEBUG_SNAPSHOTS": False,
    "DEBUG_SNAPSHOT_ON_MACRO_STOP": True,
    "DEBUG_SNAPSHOT_ON_POPUP_STUCK": True,
    "DEBUG_SNAPSHOT_ON_RECOVERY_FAILURE": True,
    "DEBUG_SNAPSHOT_RETENTION_COUNT": 12,
    "HIGH_VALUE_STOP_SCORE": 99.5,
    "AUTO_LEFT_NUDGE": 10,
    "STARTUP_DELAY": 2.0,
    "LOOP_DELAY": 0.08,
    "STUCK_TIMEOUT": 6.0,
    "UNEXPECTED_NO_ROLL_WATCHDOG_ENABLED": True,
    "UNEXPECTED_NO_ROLL_TIMEOUT": 0.0,
    "UNEXPECTED_NO_ROLL_COOLDOWN": 0.0,
    "PARTIAL_TARGET_CONFIRM_ATTEMPTS": 2,
    "PARTIAL_TARGET_CONFIRM_DELAY": 0.08,
    "AUTO_VERIFY_DELAY": 0.20,
    "AUTO_VERIFY_POLLS": 7,
    "AUTO_VERIFY_POLL_DELAY": 0.14,
    "POPUP_RETRY_DELAY": 0.06,
    "MANUAL_POPUP_TIMEOUT": 1.1,
    "MANUAL_POPUP_POLL_DELAY": 0.10,
    "MAX_RECOVERY_ATTEMPTS": 3,
    "WEBHOOK_URL": "",
    "PLAYER_PING": "",
    "DELETE_SCREENSHOTS_AFTER_WEBHOOK": True,
    "WEBHOOK_LIVE_STATUS_ENABLED": True,
    "WEBHOOK_STATUS_UPDATE_INTERVAL": 120,
    "WEBHOOK_FAILURE_SCREENSHOTS": True,
    "WEBHOOK_SCREENSHOT_ON_POPUP_STUCK": True,
    "WEBHOOK_SCREENSHOT_ON_MACRO_STOP": True,
    "WEBHOOK_DEDUP_WINDOW": 90,
    "CURRENT_SPEC_MARKER_OCR": True,
    "CURRENT_SPEC_FALLBACK_MIN_QUALITY": 70,
    "REQUIRE_CURRENT_SPEC": True,
    "TESSERACT_CMD": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
}


@dataclass
class RecoveryVerifyOutcome:
    confirmed: bool
    classification: str
    reason: str = ""
    rejection_reason: str = ""
    signal_sources: tuple[str, ...] = ()
    image_changed_samples: int = 0
    max_change_score: float = 0.0
    unreadable: bool = False
    sample_text: str = ""
    samples: int = 0
    ui_signals: tuple[str, ...] = ()
    weak_samples: int = 0
    exit_reason: str = ""
    context: str = ""


def _require_module(name: str, module):
    if module is None:
        raise RuntimeError(f"{name} is not installed. Install project dependencies and try again.")
    return module


def normalize_text(text: str) -> str:
    text = normalize_numeric_ocr_text(text)
    t = normalize_ocr_text(text)
    t = re.sub(r"\s+", " ", t).strip()
    for wrong, correct in TYPO_MAP.items():
        t = t.replace(wrong, correct)
    t = normalize_numeric_ocr_text(t)
    return t


def normalize_numeric_ocr_text(text: str) -> str:
    text = str(text or "")
    text = re.sub(r"(?<=\d)\s*[-–—]\s*(?=\d)", ".", text)
    text = re.sub(r"(?<=\d)[fF](?=[.\-]\d)", "4", text)
    text = re.sub(r"(?<=\d)[oO](?=\.\d)", "0", text)
    return text


def preprocess_ocr_image(img, scale=3, threshold=True):
    _require_module("Pillow", ImageOps)
    img = img.convert("L")
    scale = max(2, int(scale or 3))
    img = img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)

    if cv2 is not None and np is not None:
        arr = np.array(img)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        arr = clahe.apply(arr)
        if threshold:
            arr = cv2.adaptiveThreshold(
                arr,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                31,
                5,
            )
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        arr = cv2.filter2D(arr, -1, kernel)
        return Image.fromarray(arr)

    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    img = ImageEnhance.Contrast(img).enhance(2.2)
    img = img.filter(ImageFilter.SHARPEN)
    if threshold:
        img = img.point(lambda x: 255 if x > 145 else 0)
    return img


def preprocess(img):
    return preprocess_ocr_image(img, scale=3, threshold=True)


def extract_numbers(text: str):
    nums = []
    text = normalize_numeric_ocr_text(text)
    for m in re.findall(r"(?<![a-zA-Z0-9])\d+(?:\.\d+)?(?![a-zA-Z0-9])", text):
        try:
            nums.append(float(m))
        except ValueError:
            pass
    return nums


def parse_match_number(text: str, match, group=1):
    start, end = match.span(group)
    if start > 0 and text[start - 1].isalnum():
        return None
    if end < len(text) and text[end].isalnum():
        return None
    try:
        return float(match.group(group))
    except Exception:
        return None


def _ocr_word_is_stat_fragment(word: str) -> bool:
    compact = re.sub(r"[^a-z0-9]+", "", str(word or "").lower())
    compact = re.sub(r"(?:viii|vii|vi|iv|ix|iii|ii|i|v|x)$", "", compact)
    if compact in {
        "damage",
        "dmg",
        "crit",
        "critrate",
        "critchance",
        "critdamage",
        "critdmg",
        "hp",
        "range",
        "luck",
        "drop",
        "npcdmg",
        "npcdamage",
        "comboramp",
        "combo",
    }:
        return True
    normalized = normalize_stat_tokens(compact)
    stat_keys = {"combo_ramp", "damage", "crit_rate", "crit_damage", "drop", "luck", "npc_damage"}
    return bool(normalized in stat_keys or any(token in stat_keys for token in normalized.split()))


def detect_trait(text: str):
    normalized = normalize_text(text)
    for trait, aliases in TRAIT_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return canonical_spec_trait(trait)
    words = re.findall(r"[a-z]{4,}", normalized)
    aliases = {
        alias: trait
        for trait, trait_aliases in TRAIT_ALIASES.items()
        for alias in trait_aliases
        if len(alias) >= 4 and " " not in alias
    }
    for word in words:
        if _ocr_word_is_stat_fragment(word):
            continue
        match = difflib.get_close_matches(word, aliases.keys(), n=1, cutoff=0.72)
        if match:
            return canonical_spec_trait(aliases[match[0]])
    return None


def _detect_alias_trait(text: str, alias_map: dict[str, list[str]], cutoff=0.72):
    normalized = normalize_text(text)
    for trait, aliases in alias_map.items():
        if any(alias and alias in normalized for alias in aliases):
            return trait
    words = re.findall(r"[a-z]{4,}", normalized)
    aliases = {
        alias: trait
        for trait, trait_aliases in alias_map.items()
        for alias in trait_aliases
        if len(alias) >= 4 and " " not in alias
    }
    for word in words:
        match = difflib.get_close_matches(word, aliases.keys(), n=1, cutoff=cutoff)
        if match:
            return aliases[match[0]]
    return None


def _current_spec_title_text(text: str):
    normalized = normalize_text(text)
    marker = re.search(r"(?:current\s*spec|curent\s*spec|curren\s*spec|cument\s*spec|current\s*spee)", normalized)
    if not marker:
        return normalized
    after = normalized[marker.end() :]
    after = re.split(r"\d|[>%|,:;]", after, maxsplit=1)[0]
    return after.strip() or normalized


def detect_rollable_non_target_trait(text: str):
    return "non_target" if _detect_alias_trait(_current_spec_title_text(text), ROLLABLE_NON_TARGET_TRAIT_ALIASES) else None


def detect_rollable_trait(text: str):
    return detect_trait(text) or detect_rollable_non_target_trait(text)


def in_range(values, low, high, tol=0.08):
    return any((low - tol) <= v <= (high + tol) for v in values)


def nearest_value(values, low, high):
    if not values:
        return None
    return min(values, key=lambda v: min(abs(v - low), abs(v - high)))


def normalize_shard_ocr_text(text: str) -> str:
    normalized = normalize_numeric_ocr_text(str(text or "").lower())
    normalized = re.sub(r"\bs(?=\d)", "5", normalized)
    normalized = re.sub(r"\b(\d{1,2}),(\d{1,2})(?=\s*[kmb]\b)", r"\1.\2", normalized)
    normalized = normalized.replace(",", "")
    normalized = re.sub(r"\b([0-9]{1,3})(?:l|i)k\b", r"\1.1k", normalized)
    normalized = re.sub(r"\b([0-9]+(?:\.[0-9]+)?)(?:x|n)\b", r"\1k", normalized)
    normalized = re.sub(r"[^0-9.kmb ]+", " ", normalized)
    normalized = re.sub(r"\b(\d{1,3})\s+(\d)(?=\s*[kmb]\b)", r"\1.\2", normalized)
    normalized = re.sub(r"(?<=\d)\s+(?=[kmb]\b)", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def format_shard_count(count: int | None) -> str:
    if count is None:
        return "unknown"
    if count >= 1_000_000:
        compact = count / 1_000_000
        return f"{count:,} ({compact:g}m)"
    if count >= 1_000:
        compact = count / 1_000
        return f"{count:,} ({compact:g}k)"
    return f"{count:,}"


def compact_shard_count(count: int | None) -> str:
    if count is None:
        return "unknown"
    if count >= 1_000_000:
        return f"{count / 1_000_000:g}M"
    if count >= 1_000:
        return f"{count / 1_000:g}K"
    return str(int(count))


def _has_malformed_plain_shard_grouping(text: str, normalized: str) -> bool:
    if re.search(r"\b[0-9]+(?:\.[0-9]+)?\s*[kmb]\b", normalized):
        return False
    raw = normalize_numeric_ocr_text(str(text or "").lower())
    return bool(re.search(r"\b\d{1,3}(?:,\d{3})+\d+\b", raw))


def _parse_shard_count_detail(
    text: str,
    previous_value: int | None = None,
    infer_missing_suffix: bool = False,
):
    normalized = normalize_shard_ocr_text(text)
    if not normalized:
        return None, normalized, "none"
    if _has_malformed_plain_shard_grouping(text, normalized):
        return None, normalized, "malformed_plain_count"

    candidates = []
    suffix_spans = []
    for match in re.finditer(r"\b([0-9]+(?:\.[0-9]+)?)([kmb])\b", normalized):
        value = float(match.group(1))
        suffix = match.group(2)
        multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[suffix]
        parsed = int(round(value * multiplier))
        had_decimal = "." in match.group(1)
        candidates.append((parsed, value, multiplier, had_decimal, "suffix"))
        suffix_spans.append(match.span(1))

    for match in re.finditer(r"\b([0-9]+(?:\.[0-9]+)?)\b", normalized):
        if any(start <= match.start(1) and match.end(1) <= end for start, end in suffix_spans):
            continue
        parsed = int(round(float(match.group(1))))
        value = float(match.group(1))
        had_decimal = "." in match.group(1)
        candidates.append((parsed, value, 1, had_decimal, "plain"))
        if infer_missing_suffix and 10 <= value < 100:
            candidates.append((int(round(value * 1_000)), value, 1_000, had_decimal, "inferred_k"))

    if not candidates:
        return None, normalized, "none"

    adjusted = []
    for parsed, value, multiplier, had_decimal, source in candidates:
        candidate = parsed
        adjusted.append((candidate, source))

    if previous_value:
        best, source = min(adjusted, key=lambda item: abs(item[0] - previous_value))
        if best > 0 and previous_value >= 10_000 and best < previous_value / 8 and re.search(r"\b\d+(?:\.\d+)?\s*[km]\b", normalized):
            return previous_value, normalized, "previous_value_guard"
        return best, normalized, source

    if infer_missing_suffix:
        priority = {
            "suffix": 0,
            "inferred_k": 1,
            "plain": 2,
        }
        best, source = min(adjusted, key=lambda item: (priority.get(item[1], 9), -item[0]))
        return best, normalized, source

    best, source = max(adjusted, key=lambda item: item[0])
    return best, normalized, source


def parse_passive_shard_count(
    text: str,
    previous_value: int | None = None,
    infer_missing_suffix: bool = False,
):
    parsed, normalized, _source = _parse_shard_count_detail(text, previous_value, infer_missing_suffix)
    return parsed, normalized


def parse_power_shard_count(
    text: str,
    previous_value: int | None = None,
    infer_missing_suffix: bool = False,
):
    parsed, normalized, _source = _parse_shard_count_detail(text, previous_value, infer_missing_suffix)
    return parsed, normalized


def _parse_passive_shard_count_detail(
    text: str,
    previous_value: int | None = None,
    infer_missing_suffix: bool = False,
):
    return _parse_shard_count_detail(text, previous_value, infer_missing_suffix)


def _parse_power_shard_count_detail(
    text: str,
    previous_value: int | None = None,
    infer_missing_suffix: bool = False,
):
    return _parse_shard_count_detail(text, previous_value, infer_missing_suffix)


def parse_range_string(raw: str):
    low_s, high_s = [x.strip() for x in raw.split(",", 1)]
    return float(low_s), float(high_s)


def deep_copy_rules(rules):
    return {k: [tuple(x) for x in v] for k, v in rules.items()}


def migrate_rampage_ranges(trait_ranges):
    ranges = list(trait_ranges or [])
    defaults = DEFAULT_REAL_RULES["rampage"]

    if len(ranges) == 3:
        return [defaults[0]] + ranges

    if len(ranges) >= 4:
        fixed = ranges[:4]
        try:
            second_high = float(fixed[1][1])
            third_high = float(fixed[2][1])
        except Exception:
            return fixed

        crit_rate_cap = STAT_CAPS["rampage"][2]
        if second_high <= crit_rate_cap + 0.2:
            crit_rate_range = fixed[2] if third_high <= crit_rate_cap + 0.2 else fixed[1]
            return [fixed[0], defaults[1], crit_rate_range, fixed[3]]

        return fixed

    return ranges


def sanitize_rules(rules):
    clean = {}
    rules = dict(rules or {})
    if "chosen" in rules and "fortune" not in rules:
        rules["fortune"] = rules["chosen"]
    for trait, defaults in DEFAULT_REAL_RULES.items():
        trait_ranges = list(rules.get(trait, defaults) or defaults)
        if trait == "rampage":
            trait_ranges = migrate_rampage_ranges(trait_ranges)
        clean[trait] = []
        for index, cap in enumerate(STAT_CAPS[trait]):
            fallback = defaults[index]
            try:
                low, high = trait_ranges[index]
                low = float(low)
                high = float(high)
            except Exception:
                low, high = fallback

            low = max(0.0, min(low, cap))
            high = max(0.0, min(high, cap))
            if low > high:
                high = low
            clean[trait].append((round(low, 1), round(high, 1)))
    return clean


def display_trait(trait: str | None) -> str:
    if not trait:
        return "Unknown"
    if trait in POWER_DISPLAY_NAMES:
        return power_display_name(trait)
    return SPEC_DISPLAY_NAMES.get(trait, trait.replace("_", " ").title())


class AelrithForgeBot:
    def __init__(self, log_fn, status_fn, godroll_fn=None, nearmiss_fn=None):
        self.log = log_fn
        self.set_status = status_fn
        self.on_god_roll = godroll_fn or (lambda *args, **kwargs: None)
        self.on_near_miss = nearmiss_fn or (lambda *args, **kwargs: None)

        self.running = False
        self.stop_event = threading.Event()
        self.thread = None

        self.real_rules = sanitize_rules(DEFAULT_REAL_RULES)
        self.test_rules = sanitize_rules(DEFAULT_TEST_RULES)
        self.rules = deep_copy_rules(self.real_rules)
        self.cfg = dict(DEFAULT_CONFIG)

        self.last_text = ""
        self.last_change = time.time()
        self.roll_domain = "specs"
        self.enabled_specs = set(SUPPORTED_SPEC_TRAITS)
        power_defaults = default_power_settings()
        self.enabled_powers = {key for key, enabled in power_defaults["enabled_powers"].items() if enabled}
        self.power_rules = sanitize_power_rules(power_defaults["powers_rules"])

        self.last_passive_shard_report = 0.0
        self.last_passive_shards = None
        self.last_passive_shards_sent = None
        self.session_start_passive_shards = None
        self.session_latest_passive_shards = None
        self.last_passive_shard_bucket = "normal"
        self.last_passive_shard_bucket_alert = {}
        self._passive_shard_region_warned = False
        self._passive_shard_backoff_until = 0.0
        self._passive_shard_backoff_reason = ""
        self.last_power_shard_report = 0.0
        self.last_power_shards = None
        self.last_power_shards_sent = None
        self.session_start_power_shards = None
        self.session_latest_power_shards = None
        self.last_power_shard_bucket = "normal"
        self.last_power_shard_bucket_alert = {}
        self._power_shard_region_warned = False
        self._startup_shard_prime_pending = set()
        self._ocr_cache = {}
        self._last_debug_capture = 0.0
        self.recovery_failures = 0
        self.session_started_at = 0.0
        self.session_recovery_count = 0
        self.session_god_rolls = 0
        self.session_near_misses = 0
        self.session_start_passive_shards = None
        self.session_latest_passive_shards = None
        self.last_passive_shard_bucket = "normal"
        self.last_passive_shard_bucket_alert = {}
        self.last_trait_seen = ""
        self.last_important_event = "Idle"
        self.terminal_stop_reason = ""
        self.live_status_message_id = None
        self.live_status_can_edit = False
        self.last_status_update = 0.0
        self._webhook_dedup = {}
        self.last_decision_chain = {}
        self.last_ocr_candidate_debug = {}
        self.last_popup_state = {"active": None, "samples": [], "context": "unknown"}
        self.last_auto_checkbox_state = {}
        self.last_auto_checkbox_classifier_summary = {}
        self.auto_checkbox_read_count = 0
        self.auto_checkbox_ambiguous_read_count = 0
        self.manual_reroll_direct_recovery_clicks = 0
        self.last_recovery_reason = ""
        self.last_shard_ocr_state = {}
        self.recovery_duration_total = 0.0
        self.recovery_duration_count = 0
        self.popup_clear_duration_total = 0.0
        self.popup_clear_duration_count = 0
        self.last_recovery_verify_unreadable = False
        self.last_recovery_verify_state = "not_rolling"
        self.last_recovery_verify_details = {}
        self.last_recovery_fallback_unclassified = False
        self.last_power_shard_ocr_state = {}
        self.watchdog_in_progress = False
        self.recovery_in_progress = False
        self.manual_reroll_active = False
        self.last_watchdog_attempt_at = 0.0
        self.last_watchdog_signature = ""
        self._last_empty_check_skip_log = 0.0
        self._empty_check_active = False
        self._last_power_empty_check_skip_log = 0.0
        self._power_empty_check_active = False
        self._fragment_rejection_dedup = {}
        self._startup_context = None
        self.last_startup_result = ""
        self.last_startup_route_snapshot = {}
        self.last_recovery_route_snapshot = {}
        self.last_manual_reroll_confirmed_at = 0.0
        self.last_manual_reroll_confirm_reason = ""
        self.recent_timing_events = []
        self.recent_route_budget_events = []
        self.last_verification_cache_stats = {}
        self._last_non_target_decision_cache = {}
        self._runtime_log_dedup = {}
        self._last_loop_perf_log = 0.0

    def update(self, **kwargs):
        self.cfg.update(kwargs)
        self._enforce_recovery_safety_defaults()
        cmd = self.cfg.get("TESSERACT_CMD")
        if pytesseract is not None and cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd

    def _stop_requested(self, context="operation"):
        if not self.stop_event.is_set():
            return False
        self.log(f"Stop requested during {context}")
        return True

    def _record_timing_event(self, name, elapsed_seconds, **fields):
        try:
            elapsed_ms = int(max(0.0, float(elapsed_seconds)) * 1000)
        except Exception:
            elapsed_ms = 0
        event = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "name": str(name or "timing"),
            "elapsed_ms": elapsed_ms,
        }
        for key, value in fields.items():
            event[str(key)] = value
        self.recent_timing_events.append(event)
        self.recent_timing_events = self.recent_timing_events[-60:]
        return event

    def _record_verify_budget_event(self, context, elapsed_seconds, polls_seen, polls_planned, result, reason=""):
        try:
            elapsed_ms = int(max(0.0, float(elapsed_seconds or 0.0)) * 1000)
        except Exception:
            elapsed_ms = 0
        startup = "Initial Auto Start" in str(context or "")
        name = "startup_verify_budget" if startup else "recovery_verify_budget"
        seen = max(0, int(polls_seen or 0))
        planned = max(0, int(polls_planned or 0))
        event = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "name": name,
            "context": str(context or ""),
            "path": str(context or ""),
            "polls": seen,
            "polls_planned": planned,
            "elapsed_ms": elapsed_ms,
            "result": str(result or "unknown"),
            "reason": str(reason or ""),
        }
        self.recent_route_budget_events.append(event)
        self.recent_route_budget_events = self.recent_route_budget_events[-40:]
        self._record_timing_event(
            name,
            elapsed_seconds,
            context=str(context or ""),
            path=str(context or ""),
            polls=seen,
            polls_planned=planned,
            result=str(result or "unknown"),
            reason=str(reason or ""),
        )
        self.log(
            f"{name} | path={context} | polls={seen}/{planned} | elapsed={elapsed_ms}ms | "
            f"result={result or 'unknown'} | reason={reason or 'none'}"
        )
        return event

    def _log_with_cooldown(self, key, message, cooldown=60.0):
        now = time.time()
        try:
            cooldown = max(0.0, float(cooldown or 0.0))
        except Exception:
            cooldown = 0.0
        state = self._runtime_log_dedup.get(key) or {}
        last_message = str(state.get("message") or "")
        last_time = float(state.get("time") or 0.0)
        if last_message == message and now - last_time < cooldown:
            return False
        self._runtime_log_dedup[key] = {"message": message, "time": now}
        self.log(message)
        return True

    def _session_blocked_ocr_reason(self, text):
        cleaned = normalize_text(text or "")
        if not cleaned:
            return ""
        compact = re.sub(r"[^a-z0-9]+", "", cleaned)
        if "maintenancestarting" in compact or ("maintenance" in cleaned and "starting" in cleaned):
            return "maintenance_screen"
        if (
            "initiateddisconnect" in compact
            or "clientinitiateddisconnect" in compact
            or "errorcode285" in compact
            or (("disconnect" in cleaned or "disconnect" in compact) and "285" in compact)
        ):
            return "disconnect_screen"
        return ""

    def _session_blocked_support_signals(self, reason):
        if not reason:
            return []
        return ["session_blocked", str(reason)]

    def _stats_region_control_text_reason(self, text):
        cleaned = normalize_text(text or "")
        if not cleaned:
            return ""
        compact = re.sub(r"[^a-z0-9]+", "", cleaned)
        if not compact:
            return ""
        if self._has_activity_stat_signal(cleaned) or self.has_current_spec_marker(cleaned):
            return ""
        if self.detect_rollable_trait(cleaned):
            return ""
        control_markers = (
            "ocrpass",
            "startpowers",
            "startspecs",
            "startspec",
            "startpower",
            "fartpowers",
            "rcode",
            "orcode",
        )
        if any(marker in compact for marker in control_markers):
            return "stats_region_off_target_ui_text"
        if re.search(r"\b(?:or)?code\s*:?\s*\d+\b", cleaned):
            return "stats_region_off_target_ui_text"
        return ""

    def _watchdog_roll_panel_support(self, text, trait=None, effective_checkbox_state="unknown"):
        cleaned = normalize_text(text or "")
        signals = []
        if self.has_current_spec_marker(cleaned):
            signals.append("current_spec_marker")
        detected_trait = trait or self.detect_rollable_trait(cleaned) or self._generic_rollable_non_target_from_text(cleaned)
        if detected_trait:
            signals.append("trait")
        if self._has_activity_stat_signal(cleaned):
            signals.append("stat_signal")
        if str(effective_checkbox_state or "") == "disabled":
            signals.append("checkbox_disabled_frame")
        return signals

    def _begin_startup_context(self, reason="startup"):
        ctx = {
            "reason": reason,
            "started_perf": time.perf_counter(),
            "started_wall": time.strftime("%Y-%m-%d %H:%M:%S"),
            "result": "pending",
            "auto_state": "not_checked",
            "auto_state_known": False,
            "auto_state_attempts": 0,
            "startup_fallback_click": False,
            "cautious_uncertain_click": False,
            "uncertain_click_restored": False,
            "manual_reroll_used": False,
            "manual_reroll_fallback_used": False,
            "popup_confirmed": False,
            "rolling_confirmed": False,
            "current_spec_class": "unknown",
            "fallback_route": "none",
            "route_reason": "",
            "decision_confidence": "unknown",
            "supports": "none",
            "failure_type": "",
            "startup_logic_version": STARTUP_LOGIC_VERSION,
            "preflight_bypassed": False,
            "preflight_fallback_reason": "none",
            "summary_logged": False,
            "fast_non_target_trust": False,
        }
        self._startup_context = ctx
        self.last_startup_result = "pending"
        self.last_startup_route_snapshot = {
            "result": "pending",
            "route": "none",
            "route_reason": "none",
            "auto_state": "not_checked",
            "rolling_confirmed": False,
            "failure_type": "none",
            "support_signals": [],
        }
        self.log(f"[Startup] started | timestamp={ctx['started_wall']} | reason={reason}")
        return ctx

    def _startup_context_active(self):
        ctx = getattr(self, "_startup_context", None)
        return isinstance(ctx, dict) and not ctx.get("summary_logged")

    def _record_startup_auto_state(self, state, attempt):
        if not self._startup_context_active():
            return
        ctx = self._startup_context
        ctx["auto_state_attempts"] = max(int(ctx.get("auto_state_attempts", 0)), int(attempt))
        ctx["auto_state"] = state or "unknown"
        if state in ("enabled", "disabled"):
            ctx["auto_state_known"] = True
        self.log(f"[Startup Auto] state read | attempt={attempt} state={ctx['auto_state']}")

    def _record_startup_auto_result(self, result):
        if not self._startup_context_active():
            return
        ctx = self._startup_context
        if result in AUTO_UNCERTAIN_CLICK_RESULTS:
            ctx["cautious_uncertain_click"] = True
        if result in ("clicked_uncertain_restored", "clicked_uncertain_rolled_back"):
            ctx["uncertain_click_restored"] = True
        if result in (
            "already_enabled",
            "clicked",
            "clicked_uncertain_validated",
            "compact_enabled_no_click",
            "compact_disabled_clicked",
        ):
            ctx["auto_state_known"] = True
        if result == "compact_enabled_no_click":
            ctx["auto_state"] = "enabled_no_click"
        elif result == "compact_disabled_clicked":
            ctx["auto_state"] = "disabled_clicked"
        elif result == "compact_unknown_guarded_path":
            ctx["auto_state"] = "unknown_guarded_path"
        elif result == "already_enabled":
            ctx["auto_state"] = "enabled"
        elif result == "clicked":
            ctx["auto_state"] = "disabled_then_clicked"
        elif result == "startup_fallback_clicked":
            ctx["auto_state"] = "unknown_then_startup_fallback_clicked"
            ctx["startup_fallback_click"] = True
        elif result == "clicked_uncertain_validated":
            ctx["auto_state"] = "unknown_then_validated"
        elif result == "clicked_uncertain_restored":
            ctx["auto_state"] = "unknown_then_restored"
        elif result == "clicked_uncertain_rolled_back":
            ctx["auto_state"] = "unknown_then_rolled_back"
        elif result == "clicked_uncertain":
            ctx["auto_state"] = "unknown_after_cautious_click"
        elif result == "uncertain":
            ctx["auto_state"] = "unknown"

    def _set_startup_result(self, result, rolling_confirmed=False):
        self.last_startup_result = result
        if self._startup_context_active():
            self._startup_context["result"] = result
            if rolling_confirmed:
                self._startup_context["rolling_confirmed"] = True

    def _mark_startup_manual_reroll(self, fallback=False):
        if self._startup_context_active():
            self._startup_context["manual_reroll_used"] = True
            if fallback:
                self._startup_context["manual_reroll_fallback_used"] = True

    def _mark_startup_popup_confirmed(self):
        if self._startup_context_active():
            self._startup_context["popup_confirmed"] = True

    def _record_startup_spec_class(self, spec_class):
        if not self._startup_context_active():
            return
        self._startup_context["current_spec_class"] = spec_class or "unknown"

    def _record_startup_route(self, route, reason="", confidence="unknown", supports=None, failure_type=""):
        if not self._startup_context_active():
            return
        ctx = self._startup_context
        ctx["fallback_route"] = route or "none"
        ctx["route_reason"] = reason or ""
        ctx["decision_confidence"] = confidence or "unknown"
        if supports is None:
            supports_text = "none"
        elif isinstance(supports, (list, tuple, set)):
            supports_text = "+".join([str(item) for item in supports if str(item).strip()]) or "none"
        else:
            supports_text = str(supports).strip() or "none"
        ctx["supports"] = supports_text
        if failure_type:
            ctx["failure_type"] = failure_type

    def _support_signals_list(self, supports):
        if supports is None:
            return []
        if isinstance(supports, (list, tuple, set)):
            return [str(item) for item in supports if str(item).strip()]
        text = str(supports).strip()
        if not text or text == "none":
            return []
        return [part for part in text.split("+") if part]

    def _refresh_startup_route_snapshot(self):
        if not self._startup_context:
            return
        ctx = self._startup_context
        self.last_startup_route_snapshot = {
            "result": ctx.get("result", self.last_startup_result or "pending") or "pending",
            "route": ctx.get("fallback_route", "none") or "none",
            "route_reason": ctx.get("route_reason", "") or "none",
            "auto_state": ctx.get("auto_state", "unknown") or "unknown",
            "rolling_confirmed": bool(ctx.get("rolling_confirmed")),
            "failure_type": ctx.get("failure_type", "") or "none",
            "support_signals": self._support_signals_list(ctx.get("supports")),
        }

    def _set_recovery_route_snapshot(
        self,
        *,
        result,
        route_reason,
        auto_state="unknown",
        rolling_confirmed=False,
        failure_type="none",
        support_signals=None,
        context="",
    ):
        self.last_recovery_route_snapshot = {
            "result": str(result or "unknown"),
            "route_reason": str(route_reason or "none"),
            "auto_state": str(auto_state or "unknown"),
            "rolling_confirmed": bool(rolling_confirmed),
            "failure_type": str(failure_type or "none"),
            "support_signals": self._support_signals_list(support_signals),
            "context": str(context or ""),
        }

    def _finish_startup_summary(self, result=None):
        if not self._startup_context_active():
            return
        ctx = self._startup_context
        final_result = result or ctx.get("result") or STARTUP_FAILED_NO_ROLL_DETECTED
        ctx["result"] = final_result
        self.last_startup_result = final_result
        duration = max(0.0, time.perf_counter() - float(ctx.get("started_perf", time.perf_counter())))
        self.log(
            "[Startup Summary] "
            f"startup_logic_version={STARTUP_LOGIC_VERSION} | "
            f"result={final_result} | "
            f"auto_state={ctx.get('auto_state', 'unknown')} | "
            f"auto_known={bool(ctx.get('auto_state_known'))} | "
            f"auto_reads={int(ctx.get('auto_state_attempts', 0))} | "
            f"startup_fallback_click={bool(ctx.get('startup_fallback_click'))} | "
            f"cautious_uncertain_click={bool(ctx.get('cautious_uncertain_click'))} | "
            f"uncertain_click_restored={bool(ctx.get('uncertain_click_restored'))} | "
            f"manual_reroll={bool(ctx.get('manual_reroll_used'))} | "
            f"manual_fallback={bool(ctx.get('manual_reroll_fallback_used'))} | "
            f"popup_confirmed={bool(ctx.get('popup_confirmed'))} | "
            f"rolling_confirmed={bool(ctx.get('rolling_confirmed'))} | "
            f"current_spec_class={ctx.get('current_spec_class', 'unknown')} | "
            f"fallback_route={ctx.get('fallback_route', 'none')} | "
            f"route_reason={ctx.get('route_reason', '') or 'none'} | "
            f"decision_confidence={ctx.get('decision_confidence', 'unknown')} | "
            f"supports={ctx.get('supports', 'none')} | "
            f"failure_type={ctx.get('failure_type', '') or 'none'} | "
            f"preflight_bypassed={bool(ctx.get('preflight_bypassed'))} | "
            f"preflight_fallback_reason={ctx.get('preflight_fallback_reason', 'none') or 'none'} | "
            f"duration={duration:.2f}s"
        )
        ctx["summary_logged"] = True
        self._refresh_startup_route_snapshot()

    def _interruptible_sleep(self, seconds, context="sleep", step=0.05):
        deadline = time.perf_counter() + max(0.0, float(seconds))
        step = max(0.01, float(step))
        while True:
            if self.stop_event.is_set():
                self.log(f"Stop requested during {context}")
                return False
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                return True
            time.sleep(min(step, remaining))

    def _enforce_recovery_safety_defaults(self):
        minimums = {
            "STUCK_TIMEOUT": DEFAULT_CONFIG["STUCK_TIMEOUT"],
            "AUTO_VERIFY_DELAY": DEFAULT_CONFIG["AUTO_VERIFY_DELAY"],
            "AUTO_VERIFY_POLLS": DEFAULT_CONFIG["AUTO_VERIFY_POLLS"],
            "AUTO_VERIFY_POLL_DELAY": DEFAULT_CONFIG["AUTO_VERIFY_POLL_DELAY"],
            "MAX_RECOVERY_ATTEMPTS": DEFAULT_CONFIG["MAX_RECOVERY_ATTEMPTS"],
        }
        for key, minimum in minimums.items():
            try:
                current = float(self.cfg.get(key, minimum))
                value = max(current, float(minimum))
                self.cfg[key] = int(value) if isinstance(minimum, int) else value
            except Exception:
                self.cfg[key] = minimum

    def set_rules(self, real_rules):
        self.real_rules = sanitize_rules(real_rules)
        self.rules = deep_copy_rules(self.real_rules)

    def set_mode(self, mode: str):
        if mode == "test":
            self.rules = deep_copy_rules(self.test_rules)
        else:
            self.rules = deep_copy_rules(self.real_rules)
        self.log(f"Mode set to {mode.upper()}")

    def set_enabled_specs(self, enabled_specs):
        self.enabled_specs = {
            canonical
            for canonical in (canonical_spec_trait(trait) for trait in (enabled_specs or []))
            if canonical in SUPPORTED_SPEC_TRAITS
        }

    def set_roll_domain(self, roll_domain: str):
        domain = str(roll_domain or "specs").strip().lower()
        self.roll_domain = "powers" if domain == "powers" else "specs"
        self.log(f"Roll domain set to {self.roll_domain.upper()}")

    def set_power_rules(self, power_rules):
        self.power_rules = sanitize_power_rules(power_rules)

    def set_enabled_powers(self, enabled_powers):
        self.enabled_powers = set(enabled_powers or [])

    def _region_signature(self, img):
        small = img.convert("L").resize((24, 12))
        return hash(small.tobytes())

    def _region_change_score(self, first, second):
        if first is None or second is None or np is None:
            return 0.0
        try:
            left = np.asarray(first.convert("L").resize((48, 24)), dtype=np.int16)
            right = np.asarray(second.convert("L").resize((48, 24)), dtype=np.int16)
            if left.shape != right.shape:
                return 0.0
            return float(np.mean(np.abs(left - right)))
        except Exception:
            return 0.0

    def _stats_verify_changed_threshold(self):
        try:
            return max(3.5, float(self.cfg.get("STARTUP_VERIFY_CHANGE_THRESHOLD", 7.0)))
        except Exception:
            return 7.0

    def _safe_region_screenshot(self, region):
        try:
            if pyautogui is None:
                return None
            img = pyautogui.screenshot(region=tuple(region))
            if not hasattr(img, "convert"):
                return None
            return img
        except Exception:
            return None

    def _manual_visual_change_threshold(self):
        try:
            return max(2.5, float(self.cfg.get("MANUAL_REROLL_VISUAL_CHANGE_THRESHOLD", 4.0)))
        except Exception:
            return 4.0

    def _verify_state_label(self, changed, unreadable, image_changed=False):
        if changed:
            return "rolling"
        if unreadable and image_changed:
            return "unreadable_but_changed"
        if unreadable:
            return "unreadable_static"
        return "not_rolling"

    def _startup_verify_delay_cap(self, clicked=False, guarded=False):
        base = max(0.0, float(self.cfg.get("AUTO_VERIFY_DELAY", DEFAULT_CONFIG["AUTO_VERIFY_DELAY"])))
        cap = 0.08 if (clicked or guarded) else 0.06
        return min(base, cap)

    def _startup_verify_poll_delay_cap(self, preflight=False, clicked=False, guarded=False):
        base = max(0.0, float(self.cfg.get("AUTO_VERIFY_POLL_DELAY", DEFAULT_CONFIG["AUTO_VERIFY_POLL_DELAY"])))
        if preflight:
            cap = 0.03
        elif clicked or guarded:
            cap = 0.05
        else:
            cap = 0.04
        return min(base, cap)

    def _cached_ocr(self, key, signature):
        cached = self._ocr_cache.get(key)
        if not cached:
            return None
        now = time.time()
        ttl = float(self.cfg.get("OCR_CACHE_TTL", 1.25))
        backoff = float(self.cfg.get("OCR_UNCHANGED_BACKOFF", 0.35))
        if cached["signature"] == signature and now - cached["time"] <= ttl:
            return cached["text"]
        if cached["signature"] == signature and now - cached["time"] <= backoff:
            return cached["text"]
        return None

    def _store_ocr_cache(self, key, signature, text):
        self._ocr_cache[key] = {
            "signature": signature,
            "text": text,
            "time": time.time(),
        }

    def _write_ocr_debug_event(self, event: str, payload: dict):
        if not self.cfg.get("OCR_DEBUG_FILE", True):
            return
        try:
            record = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "event": event,
                **(payload or {}),
            }
            OCR_DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with OCR_DEBUG_LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")
        except Exception:
            pass

    def ocr_region_tesseract_raw(self, region, psm=7):
        _require_module("pyautogui", pyautogui)
        _require_module("pytesseract", pytesseract)
        img = pyautogui.screenshot(region=region)
        signature = self._region_signature(img)
        key = ("tesseract_raw", tuple(region), int(psm))
        cached = self._cached_ocr(key, signature)
        if cached is not None:
            return cached
        img = preprocess(img)
        text = pytesseract.image_to_string(img, config=f"--psm {psm}")
        self._store_ocr_cache(key, signature, text)
        return text

    def ocr_region_tesseract(self, region, psm=7):
        return normalize_text(self.ocr_region_tesseract_raw(region, psm))

    def _tesseract_config(self, psm):
        whitelist = self.cfg.get("TESSERACT_STAT_WHITELIST", DEFAULT_CONFIG["TESSERACT_STAT_WHITELIST"])
        whitelist = "".join(ch for ch in str(whitelist) if ch not in {"'", '"'} and not ch.isspace())
        return f"--psm {int(psm)} -c tessedit_char_whitelist={whitelist}"

    def _tight_stat_crop(self, img):
        width, height = img.size
        if width < 80 or height < 40:
            return img
        left = int(width * 0.035)
        top = int(height * 0.18)
        right = int(width * 0.97)
        bottom = int(height * 0.82)
        if right <= left or bottom <= top:
            return img
        return img.crop((left, top, right, bottom))

    def _upscale_for_tesseract(self, img, scale=2):
        scale = max(1, int(scale or 1))
        if scale == 1:
            return img
        return img.resize((img.width * scale, img.height * scale), Image.Resampling.LANCZOS)

    def _tesseract_stat_variants(self, img):
        _require_module("Pillow", ImageEnhance)
        crops = [("full", img), ("text", self._tight_stat_crop(img))]
        variants = []
        seen_sizes = set()
        for crop_name, crop in crops:
            size_key = (crop_name, crop.size)
            if size_key in seen_sizes:
                continue
            seen_sizes.add(size_key)

            original = self._upscale_for_tesseract(crop.convert("RGB"), 2)
            gray = self._upscale_for_tesseract(crop.convert("L"), 2)
            contrast = ImageEnhance.Contrast(gray).enhance(1.45)
            threshold = contrast.point(lambda px: 255 if px > 135 else 0)

            variants.extend(
                [
                    (f"{crop_name}-original", original),
                    (f"{crop_name}-gray", gray),
                    (f"{crop_name}-contrast", contrast),
                    (f"{crop_name}-threshold", threshold),
                ]
            )
        return variants

    def _tesseract_stat_passes(self, img, fallback_only=False, full=False, startup_fast=False, fast_loop=False):
        primary_modes = {
            "full-original",
            "full-gray",
            "full-threshold",
            "text-original",
            "text-gray",
            "text-threshold",
        }
        startup_fast_modes = {
            "text-original",
            "text-threshold",
            "full-original",
        }
        fast_loop_modes = {"full-original"}
        for mode_name, variant in self._tesseract_stat_variants(img):
            if full:
                psms = (6, 7)
            elif fast_loop:
                if mode_name not in fast_loop_modes:
                    continue
                psms = (6,)
            elif startup_fast:
                if mode_name not in startup_fast_modes:
                    continue
                psms = (6,)
            elif fallback_only:
                psms = (6, 7) if mode_name.endswith("contrast") else (7,)
            elif mode_name in primary_modes:
                psms = (6,)
            else:
                continue

            for psm in psms:
                yield mode_name, variant, psm

    def _ocr_tesseract_image(self, img, psm):
        _require_module("pytesseract", pytesseract)
        text = pytesseract.image_to_string(img, config=self._tesseract_config(psm))
        return text

    def ocr_region(self, region, psm=7):
        return self.ocr_region_tesseract(region, psm)

    def _strong_spec_ocr_candidate(self, engine, text, raw_text):
        combined = f"{text or ''}\n{raw_text or ''}"
        bad_panel_words = (
            "mythical 0.2",
            "fortune chosen > 17.5",
            "executioner > 30",
            "rampage > 15",
            "the more times you do dmg",
            "resets after 5s",
        )
        if any(word in normalize_text(combined) for word in bad_panel_words):
            return False, "bad_panel_text"
        trait = detect_trait(combined)
        if not trait or not self.is_target_trait(trait):
            return False, "target_trait_missing"
        if not self.has_current_spec_marker(combined):
            return False, "current_spec_marker_missing"
        values, debug = self.extract_labeled_values(trait, raw_text or text, return_debug=True)
        found = sum(value is not None for value in values)
        needed = len(STAT_LABELS.get(trait, []))
        if not needed or found < needed:
            return False, f"incomplete_values:{found}/{needed or '?'}"
        if debug.get("parse_errors"):
            return False, "parse_errors_present"
        if trait == "rampage" and not self._rampage_structure_details(values, debug)["usable"]:
            return False, "rampage_structure_weak"
        quality = self._candidate_parse_quality(trait, text, values, debug)
        coherence = self._candidate_parse_coherence(trait, values, debug)
        if quality < 100 or coherence < 90:
            return False, f"quality_too_low:{quality}/{coherence}"
        return True, f"strong_spec:{display_trait(trait)}:{found}/{needed}:{engine}"

    def _strong_power_ocr_candidate(self, engine, text, raw_text):
        combined = f"{text or ''}\n{raw_text or ''}"
        parsed = parse_power_roll_text(combined)
        if not parsed:
            return False, "power_parse_missing"
        power_key = parsed.get("power")
        values = parsed.get("values") or {}
        passive = parsed.get("passive")
        quality = self._power_candidate_quality(power_key, values, combined, passive)
        completeness = self._power_parse_completeness(power_key, values, passive)
        enabled_power = power_key in self.enabled_powers
        if quality < 100:
            return False, f"power_quality_too_low:{quality}"
        if enabled_power and not completeness["coherent"]:
            return False, "enabled_power_incomplete"
        return True, f"strong_power:{power_display_name(power_key)}:{quality}:{engine}"

    def _stats_ocr_early_stop_candidate(self, engine, text, raw_text, fallback_only=False, full=False):
        if fallback_only or full:
            return False, "full_or_fallback_scan"
        if self.roll_domain == "powers":
            return self._strong_power_ocr_candidate(engine, text, raw_text)
        return self._strong_spec_ocr_candidate(engine, text, raw_text)

    def get_stats_ocr_candidates(self, image=None, region=None, fallback_only=False, full=False, startup_fast=False, fast_loop=False):
        region = tuple(region or self.cfg["STATS_REGION"])
        candidates = []
        started = time.perf_counter()
        early_stop_reason = ""

        _require_module("pyautogui", pyautogui)
        _require_module("pytesseract", pytesseract)
        img = image if image is not None else pyautogui.screenshot(region=region)
        signature = self._region_signature(img)
        self._last_stats_ocr_signature = signature

        for mode_name, variant, psm in self._tesseract_stat_passes(
            img,
            fallback_only=fallback_only,
            full=full,
            startup_fast=startup_fast,
            fast_loop=fast_loop,
        ):
            engine = f"tesseract-{mode_name}-psm{psm}"
            key = ("tesseract_stat", tuple(region), mode_name, int(psm))
            raw = self._cached_ocr(key, signature)
            if raw is None:
                raw = self._ocr_tesseract_image(variant, psm)
                self._store_ocr_cache(key, signature, raw)
            if self.cfg.get("OCR_DEBUG_VERBOSE", True) and raw:
                self.log(f"OCR attempt {engine} | raw={self._compact_debug_text(raw)}")
            normalized = normalize_text(raw)
            if normalized:
                candidates.append((engine, normalized, raw))
                early_stop, early_stop_reason = self._stats_ocr_early_stop_candidate(
                    engine,
                    normalized,
                    raw,
                    fallback_only=fallback_only,
                    full=full,
                )
                if early_stop:
                    self.log(
                        "OCR early stop | "
                        f"engine={engine} | reads={len(candidates)} | reason={early_stop_reason}"
                    )
                    break

        unique = []
        seen = set()
        for engine, text, raw_text in candidates:
            key = (engine, text.strip())
            if text.strip() and key not in seen:
                unique.append((engine, text.strip(), raw_text.strip()))
                seen.add(key)
        self._write_ocr_debug_event(
            "ocr_candidates",
            {
                "region": list(region),
                "candidate_count": len(unique),
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "fallback_only": bool(fallback_only),
                "full": bool(full),
                "startup_fast": bool(startup_fast),
                "fast_loop": bool(fast_loop),
                "early_stop_reason": early_stop_reason,
                "candidates": [
                    {
                        "engine": engine,
                        "raw": raw_text,
                        "cleaned": text,
                    }
                    for engine, text, raw_text in unique
                ],
            },
        )
        return unique

    def click(self, coords, label, offset=(0, 0), settle=0.2):
        _require_module("pydirectinput", pydirectinput)
        x = coords[0] + offset[0]
        y = coords[1] + offset[1]

        pydirectinput.moveTo(x + 3, y, duration=0)
        time.sleep(0.01)
        pydirectinput.moveTo(x - 2, y + 1, duration=0)
        time.sleep(0.01)
        pydirectinput.moveTo(x, y, duration=0)
        time.sleep(0.02)
        pydirectinput.click(x, y)
        time.sleep(settle)

    def auto_checkbox_click_point(self):
        return (
            int(self.cfg["AUTO_CHECKBOX"][0] - self.cfg.get("AUTO_LEFT_NUDGE", 0)),
            int(self.cfg["AUTO_CHECKBOX"][1]),
        )

    def auto_checkbox_region(self, padding=22):
        x, y = self.auto_checkbox_click_point()
        padding = max(10, int(padding))
        return (max(0, x - padding), max(0, y - padding), padding * 2, padding * 2)

    def _auto_checkbox_crop_metrics(self, img):
        img = img.convert("RGB")
        raw = img.tobytes()
        total = len(raw) // 3
        metrics = {
            "pixels": total,
            "green_ratio": 0.0,
            "blue_ratio": 0.0,
            "bright_ratio": 0.0,
            "dark_ratio": 0.0,
            "mid_gray_ratio": 0.0,
            "gray_frame_ratio": 0.0,
            "saturated_ratio": 0.0,
        }
        if total <= 0:
            return metrics
        green_pixels = 0
        blue_pixels = 0
        bright_pixels = 0
        dark_pixels = 0
        mid_gray_pixels = 0
        gray_frame_pixels = 0
        saturated_pixels = 0
        for index in range(0, total * 3, 3):
            r, g, b = raw[index], raw[index + 1], raw[index + 2]
            spread = max(r, g, b) - min(r, g, b)
            luma = (r + g + b) / 3.0
            if g >= 105 and g >= r * 1.25 and g >= b * 1.15:
                green_pixels += 1
            if b >= 115 and b >= r * 1.2 and b >= g * 1.05:
                blue_pixels += 1
            if r >= 185 and g >= 185 and b >= 185:
                bright_pixels += 1
            if r <= 70 and g <= 70 and b <= 70:
                dark_pixels += 1
            if 70 <= luma <= 180 and spread <= 60:
                mid_gray_pixels += 1
            if 85 <= luma <= 180 and spread <= 55:
                gray_frame_pixels += 1
            if spread >= 65:
                saturated_pixels += 1
        metrics.update(
            {
                "green_ratio": round(green_pixels / total, 4),
                "blue_ratio": round(blue_pixels / total, 4),
                "bright_ratio": round(bright_pixels / total, 4),
                "dark_ratio": round(dark_pixels / total, 4),
                "mid_gray_ratio": round(mid_gray_pixels / total, 4),
                "gray_frame_ratio": round(gray_frame_pixels / total, 4),
                "saturated_ratio": round(saturated_pixels / total, 4),
            }
        )
        return metrics

    def _center_crop(self, img, fraction=0.62):
        fraction = min(1.0, max(0.2, float(fraction)))
        width, height = img.size
        crop_w = max(1, int(width * fraction))
        crop_h = max(1, int(height * fraction))
        left = max(0, (width - crop_w) // 2)
        top = max(0, (height - crop_h) // 2)
        return img.crop((left, top, left + crop_w, top + crop_h))

    def _auto_checkbox_disabled_frame_signal(self, full, inner):
        full = full or {}
        inner = inner or {}
        full_accent = max(float(full.get("green_ratio", 0.0) or 0.0), float(full.get("blue_ratio", 0.0) or 0.0))
        inner_accent = max(float(inner.get("green_ratio", 0.0) or 0.0), float(inner.get("blue_ratio", 0.0) or 0.0))
        bright_ratio = max(float(full.get("bright_ratio", 0.0) or 0.0), float(inner.get("bright_ratio", 0.0) or 0.0))
        dark_ratio = max(float(full.get("dark_ratio", 0.0) or 0.0), float(inner.get("dark_ratio", 0.0) or 0.0))
        saturated_ratio = max(float(full.get("saturated_ratio", 0.0) or 0.0), float(inner.get("saturated_ratio", 0.0) or 0.0))
        mid_gray_ratio = max(float(full.get("mid_gray_ratio", 0.0) or 0.0), float(inner.get("mid_gray_ratio", 0.0) or 0.0))
        gray_frame_ratio = max(float(full.get("gray_frame_ratio", 0.0) or 0.0), float(inner.get("gray_frame_ratio", 0.0) or 0.0))
        no_accent = full_accent < 0.02 and inner_accent < 0.02
        classic_bright_frame = (
            bright_ratio >= 0.08
            and dark_ratio >= 0.08
            and no_accent
            and saturated_ratio < 0.22
        )
        if classic_bright_frame:
            return True, "frame signal without accent"
        unchecked_grayscale_frame = (
            gray_frame_ratio >= 0.12
            and mid_gray_ratio >= 0.18
            and dark_ratio >= 0.08
            and no_accent
            and saturated_ratio < 0.30
        )
        if unchecked_grayscale_frame:
            return True, "unchecked grayscale frame signal"
        return False, ""

    def _auto_checkbox_sky_like_false_accent(self, full, inner):
        full = full or {}
        inner = inner or {}
        full_blue = float(full.get("blue_ratio", 0.0) or 0.0)
        inner_blue = float(inner.get("blue_ratio", 0.0) or 0.0)
        full_dark = float(full.get("dark_ratio", 0.0) or 0.0)
        inner_dark = float(inner.get("dark_ratio", 0.0) or 0.0)
        full_saturated = float(full.get("saturated_ratio", 0.0) or 0.0)
        inner_saturated = float(inner.get("saturated_ratio", 0.0) or 0.0)
        full_mid_gray = float(full.get("mid_gray_ratio", 0.0) or 0.0)
        inner_mid_gray = float(inner.get("mid_gray_ratio", 0.0) or 0.0)
        return (
            full_blue >= 0.25
            and inner_blue >= 0.25
            and full_dark < 0.05
            and inner_dark < 0.05
            and full_saturated < 0.20
            and inner_saturated < 0.20
            and full_mid_gray >= 0.55
            and inner_mid_gray >= 0.70
        )

    def _classify_auto_checkbox_image(self, img):
        if img is None:
            return "unknown", {"reason": "missing image", "full": {}, "inner": {}}
        img = img.convert("RGB")
        full = self._auto_checkbox_crop_metrics(img)
        inner = self._auto_checkbox_crop_metrics(self._center_crop(img))
        full_accent = max(full["green_ratio"], full["blue_ratio"])
        inner_accent = max(inner["green_ratio"], inner["blue_ratio"])
        if self._auto_checkbox_sky_like_false_accent(full, inner):
            return "unknown", {"reason": "broad blue background rejected", "full": full, "inner": inner}
        if inner["green_ratio"] >= 0.025 or inner["blue_ratio"] >= 0.045:
            return "enabled", {"reason": "inner accent signal", "full": full, "inner": inner}
        if full["green_ratio"] >= 0.035 or full["blue_ratio"] >= 0.06:
            return "enabled", {"reason": "full crop accent signal", "full": full, "inner": inner}
        disabled_signal, disabled_reason = self._auto_checkbox_disabled_frame_signal(full, inner)
        if disabled_signal:
            return "disabled", {"reason": disabled_reason, "full": full, "inner": inner}
        return "unknown", {"reason": "ambiguous checkbox crop", "full": full, "inner": inner}

    def auto_checkbox_state(self):
        raw_point = tuple(self.cfg["AUTO_CHECKBOX"])
        click_point = self.auto_checkbox_click_point()
        base_padding = 22
        read_plan = [
            (base_padding, 0.62, "base"),
            (base_padding + 4, 0.7, "wide"),
            (max(18, base_padding - 4), 0.56, "tight"),
        ]
        region = self.auto_checkbox_region(base_padding)
        self.last_auto_checkbox_state = {
            "state": "unknown",
            "reason": "not read",
            "raw_point": raw_point,
            "left_nudge": int(self.cfg.get("AUTO_LEFT_NUDGE", 0)),
            "click_point": click_point,
            "region": region,
            "metrics": {},
            "samples": [],
        }
        if pyautogui is None or Image is None:
            self.last_auto_checkbox_state.update({"reason": "screenshot unavailable"})
            return "unknown"

        sample_results = []
        for padding, center_fraction, label in read_plan:
            sample_region = self.auto_checkbox_region(padding)
            try:
                img = pyautogui.screenshot(region=sample_region).convert("RGB")
            except Exception as e:
                self.last_auto_checkbox_state.update({"reason": f"screenshot failed: {e}", "region": sample_region})
                return "unknown"
            state, details = self._classify_auto_checkbox_image(img)
            # re-score with the requested center fraction for extra stability
            alt_inner = self._auto_checkbox_crop_metrics(self._center_crop(img, center_fraction))
            full = details.get("full", {}) or {}
            default_inner = details.get("inner", {}) or {}
            full_accent = max(full.get("green_ratio", 0.0), full.get("blue_ratio", 0.0))
            alt_accent = max(alt_inner.get("green_ratio", 0.0), alt_inner.get("blue_ratio", 0.0))
            alt_green = float(alt_inner.get("green_ratio", 0.0) or 0.0)
            alt_blue = float(alt_inner.get("blue_ratio", 0.0) or 0.0)
            inner_green = float(default_inner.get("green_ratio", 0.0) or 0.0)
            inner_blue = float(default_inner.get("blue_ratio", 0.0) or 0.0)
            disabled_signal, disabled_reason = self._auto_checkbox_disabled_frame_signal(full, alt_inner)
            if self._auto_checkbox_sky_like_false_accent(full, alt_inner):
                state = "unknown"
                reason = f"{label} broad blue background rejected"
            elif (
                max(alt_green, alt_blue) >= 0.06
                and max(inner_green, inner_blue) >= 0.02
                and (alt_green >= 0.03 or alt_blue >= 0.05)
            ):
                state = "enabled"
                reason = f"{label} alt-inner accent signal"
            elif disabled_signal:
                state = "disabled"
                reason = f"{label} {disabled_reason}"
            else:
                reason = details.get("reason", "") or f"{label} ambiguous checkbox crop"
            sample_results.append(
                {
                    "label": label,
                    "padding": int(padding),
                    "center_fraction": float(center_fraction),
                    "region": sample_region,
                    "state": state,
                    "reason": reason,
                    "metrics": {"full": full, "inner": default_inner, "alt_inner": alt_inner},
                }
            )

        enabled_samples = [s for s in sample_results if s["state"] == "enabled"]
        disabled_samples = [s for s in sample_results if s["state"] == "disabled"]
        if enabled_samples and not disabled_samples:
            strongest_enabled = max(
                enabled_samples,
                key=lambda s: max(
                    s["metrics"]["inner"].get("green_ratio", 0.0),
                    s["metrics"]["inner"].get("blue_ratio", 0.0),
                    s["metrics"]["alt_inner"].get("green_ratio", 0.0),
                    s["metrics"]["alt_inner"].get("blue_ratio", 0.0),
                ),
            )
            enabled_strength = max(
                strongest_enabled["metrics"]["inner"].get("green_ratio", 0.0),
                strongest_enabled["metrics"]["inner"].get("blue_ratio", 0.0),
                strongest_enabled["metrics"]["alt_inner"].get("green_ratio", 0.0),
                strongest_enabled["metrics"]["alt_inner"].get("blue_ratio", 0.0),
            )
            strong_inner_samples = 0
            tight_enabled = any(str(s.get("label") or "") == "tight" for s in enabled_samples)
            base_enabled = any(str(s.get("label") or "") == "base" for s in enabled_samples)
            tight_unknown = any(str(s.get("label") or "") == "tight" and s.get("state") == "unknown" for s in sample_results)
            for sample in enabled_samples:
                metrics = sample.get("metrics") or {}
                inner = metrics.get("inner") or {}
                alt_inner = metrics.get("alt_inner") or {}
                if max(
                    float(inner.get("green_ratio", 0.0) or 0.0),
                    float(inner.get("blue_ratio", 0.0) or 0.0),
                    float(alt_inner.get("green_ratio", 0.0) or 0.0),
                    float(alt_inner.get("blue_ratio", 0.0) or 0.0),
                ) >= 0.05:
                    strong_inner_samples += 1
            if (
                len(enabled_samples) >= 2
                and strong_inner_samples >= 1
                and not (base_enabled and not tight_enabled and tight_unknown)
            ) or enabled_strength >= 0.10:
                chosen = strongest_enabled
                state = "enabled"
            else:
                state = "unknown"
                chosen = {
                    "reason": "weak or wide-only enabled checkbox samples",
                    "region": region,
                    "metrics": {"samples": sample_results},
                }
        elif disabled_samples and not enabled_samples:
            chosen = max(
                disabled_samples,
                key=lambda s: (
                    max(s["metrics"]["full"].get("bright_ratio", 0.0), s["metrics"]["alt_inner"].get("bright_ratio", 0.0))
                    + max(s["metrics"]["full"].get("gray_frame_ratio", 0.0), s["metrics"]["alt_inner"].get("gray_frame_ratio", 0.0))
                    + max(s["metrics"]["full"].get("mid_gray_ratio", 0.0), s["metrics"]["alt_inner"].get("mid_gray_ratio", 0.0))
                    + max(s["metrics"]["full"].get("dark_ratio", 0.0), s["metrics"]["alt_inner"].get("dark_ratio", 0.0))
                ),
            )
            state = "disabled"
        elif enabled_samples and disabled_samples:
            state = "unknown"
            chosen = {
                "reason": "conflicting checkbox samples",
                "region": region,
                "metrics": {},
            }
        else:
            state = "unknown"
            chosen = {
                "reason": "all checkbox samples ambiguous",
                "region": region,
                "metrics": {},
            }

        self.last_auto_checkbox_state.update(
            {
                "state": state,
                "reason": chosen.get("reason", ""),
                "region": chosen.get("region", region),
                "metrics": chosen.get("metrics", {}),
                "samples": sample_results,
            }
        )
        return state

    def _auto_checkbox_enabled_is_weak(self):
        info = dict(self.last_auto_checkbox_state or {})
        samples = info.get("samples") or []
        enabled_samples = [s for s in samples if s.get("state") == "enabled"]
        disabled_samples = [s for s in samples if s.get("state") == "disabled"]
        if not enabled_samples or disabled_samples:
            return False
        max_inner_accent = 0.0
        strong_inner_samples = 0
        wide_only_enabled = False
        tight_enabled = False
        tight_unknown = False
        base_enabled = False
        for sample in enabled_samples:
            metrics = sample.get("metrics") or {}
            inner = metrics.get("inner") or {}
            alt_inner = metrics.get("alt_inner") or {}
            inner_accent = max(
                float(inner.get("green_ratio", 0.0) or 0.0),
                float(inner.get("blue_ratio", 0.0) or 0.0),
                float(alt_inner.get("green_ratio", 0.0) or 0.0),
                float(alt_inner.get("blue_ratio", 0.0) or 0.0),
            )
            label = str(sample.get("label") or "")
            reason = str(sample.get("reason") or "")
            max_inner_accent = max(max_inner_accent, inner_accent)
            if inner_accent >= 0.05:
                strong_inner_samples += 1
            if label == "tight" and sample.get("state") == "enabled":
                tight_enabled = True
            if label == "base" and sample.get("state") == "enabled":
                base_enabled = True
            if "wide" in reason and "accent signal" in reason:
                wide_only_enabled = True
        for sample in samples:
            if str(sample.get("label") or "") == "tight" and sample.get("state") == "unknown":
                tight_unknown = True
                break
        classifier = str(info.get("reason", ""))
        if len(enabled_samples) < 2:
            return True
        if max_inner_accent < 0.05:
            return True
        if strong_inner_samples == 0:
            return True
        if wide_only_enabled or "full crop accent signal" in classifier or "wide alt-inner accent signal" in classifier:
            return True
        if base_enabled and not tight_enabled and tight_unknown:
            return True
        return False

    def _auto_checkbox_confidence_tier(self):
        info = dict(self.last_auto_checkbox_state or {})
        state = str(info.get("state") or "unknown")
        if state == "enabled":
            return "weak_enabled" if self._auto_checkbox_enabled_is_weak() else "strong_enabled"
        if state == "unknown" and self._auto_checkbox_enabled_is_weak():
            return "weak_enabled"
        if state == "disabled":
            return "strong_disabled"
        return "ambiguous"

    def _effective_auto_checkbox_state(self, state=None, confidence_tier=None):
        raw_state = str(state or (self.last_auto_checkbox_state or {}).get("state") or "unknown")
        tier = str(confidence_tier or self._auto_checkbox_confidence_tier())
        if raw_state == "enabled":
            return "weak_enabled" if tier == "weak_enabled" else "strong_enabled"
        if raw_state == "unknown" and tier == "weak_enabled":
            return "weak_enabled"
        if raw_state == "disabled":
            return "disabled"
        return "ambiguous"

    def _set_terminal_stop_reason(self, reason):
        reason = str(reason or "").strip()
        if not reason:
            return
        self.terminal_stop_reason = reason
        self.last_important_event = reason

    def _resolved_stop_reason(self):
        if self.terminal_stop_reason:
            return self.terminal_stop_reason
        if self.stop_event.is_set():
            return "Manual stop requested"
        return self.last_important_event or "Stopped"

    def auto_checkbox_session_summary(self):
        return {
            "reads": int(self.auto_checkbox_read_count),
            "ambiguous_reads": int(self.auto_checkbox_ambiguous_read_count),
            "manual_reroll_direct_recovery_clicks": int(self.manual_reroll_direct_recovery_clicks),
            "latest_classifier": dict(self.last_auto_checkbox_classifier_summary or {}),
        }

    def _log_auto_checkbox_state_read(self, reason, attempt, state):
        info = dict(self.last_auto_checkbox_state or {})
        if not info:
            info = {
                "raw_point": tuple(self.cfg["AUTO_CHECKBOX"]),
                "left_nudge": int(self.cfg.get("AUTO_LEFT_NUDGE", 0)),
                "click_point": self.auto_checkbox_click_point(),
                "region": self.auto_checkbox_region(),
                "reason": "state supplied externally",
                "metrics": {},
            }
        info["state"] = state
        sample_summary = ""
        samples = info.get("samples") or []
        if samples:
            sample_summary = " | samples=" + ", ".join(
                f"{s.get('label')}:{s.get('state')}" for s in samples
            )
        evidence_source = "mixed"
        classifier_text = str(info.get("reason", "") or "")
        if "wide" in classifier_text or "full crop" in classifier_text:
            evidence_source = "outer_wide_accent"
        elif "inner" in classifier_text:
            evidence_source = "inner_checkbox"
        confidence_tier = self._auto_checkbox_confidence_tier()
        compact_samples = []
        for sample in samples:
            compact_samples.append(
                {
                    "label": sample.get("label"),
                    "state": sample.get("state"),
                    "reason": sample.get("reason"),
                    "metrics": sample.get("metrics", {}),
                }
            )
        self.auto_checkbox_read_count += 1
        effective_state = self._effective_auto_checkbox_state(state, confidence_tier)
        if state == "unknown" or effective_state == "ambiguous":
            self.auto_checkbox_ambiguous_read_count += 1
        self.last_auto_checkbox_classifier_summary = {
            "context": str(reason),
            "attempt": int(attempt),
            "state": state,
            "confidence": confidence_tier,
            "effective_state": effective_state,
            "evidence": evidence_source,
            "classifier": info.get("reason", ""),
            "raw_point": list(info.get("raw_point") or ()),
            "left_nudge": info.get("left_nudge"),
            "click_point": list(info.get("click_point") or ()),
            "region": list(info.get("region") or ()),
            "samples": compact_samples,
        }
        self.log(
            "Auto checkbox state read | "
            f"reason={reason} | attempt={attempt} | raw={info.get('raw_point')} | "
            f"nudge={info.get('left_nudge')} | click={info.get('click_point')} | "
            f"region={info.get('region')} | state={state} | confidence={confidence_tier} | evidence={evidence_source} | classifier={info.get('reason', '')}{sample_summary}"
        )
        should_record = state == "unknown" or "Initial Auto Start" in str(reason) or "Recovery" in str(reason)
        if should_record:
            self._write_ocr_debug_event(
                "auto_checkbox_state",
                {
                    "context": str(reason),
                    "attempt": int(attempt),
                    "state": state,
                    "raw_point": list(info.get("raw_point") or ()),
                    "left_nudge": info.get("left_nudge"),
                    "click_point": list(info.get("click_point") or ()),
                    "region": list(info.get("region") or ()),
                    "classifier": info.get("reason", ""),
                    "metrics": info.get("metrics", {}),
                    "samples": compact_samples,
                },
            )

    def _observe_auto_state(self, reason="Auto"):
        reason_text = str(reason)
        reason_lower = reason_text.lower()
        startup_auto = "Initial Auto Start" in reason_text
        manual_resume_auto = "manual reroll auto resume" in reason_lower
        diagnostic_auto = startup_auto or "recovery" in reason_lower or manual_resume_auto
        state_label = "Startup auto state" if startup_auto else "Auto state"
        state = self.auto_checkbox_state()
        if diagnostic_auto:
            self._log_auto_checkbox_state_read(reason, 1, state)
        if startup_auto:
            self._record_startup_auto_state(state, 1)
        confidence_tier = self._auto_checkbox_confidence_tier()
        if state == "unknown" and manual_resume_auto and confidence_tier == "weak_enabled":
            self.log(
                f"{state_label} uncertain but checkbox samples lean enabled; using compact manual reroll resume validation | {reason}"
            )
            return "weak_enabled"
        if state == "unknown":
            self.log(f"{state_label} uncertain; retrying state detection | {reason}")
            if not self._interruptible_sleep(0.05, f"{reason} auto state retry"):
                return "aborted"
            state = self.auto_checkbox_state()
            if diagnostic_auto:
                self._log_auto_checkbox_state_read(reason, 2, state)
            if startup_auto:
                self._record_startup_auto_state(state, 2)
            if state == "unknown" and diagnostic_auto and not manual_resume_auto:
                self.log(f"{state_label} still uncertain; one final confirmation read | {reason}")
                if not self._interruptible_sleep(0.04, f"{reason} auto state final retry"):
                    return "aborted"
                state = self.auto_checkbox_state()
                self._log_auto_checkbox_state_read(reason, 3, state)
                if startup_auto:
                    self._record_startup_auto_state(state, 3)
        return state

    def ensure_auto_enabled(self, reason="Auto", allow_uncertain_enable=False):
        reason_text = str(reason)
        reason_lower = reason_text.lower()
        startup_auto = "Initial Auto Start" in reason_text
        manual_resume_auto = "manual reroll auto resume" in reason_lower
        diagnostic_auto = startup_auto or "recovery" in reason_lower or manual_resume_auto
        exact_initial_auto_start = reason_text.strip() == "Initial Auto Start"
        state_label = "Startup auto state" if startup_auto else "Auto state"
        state = self._observe_auto_state(reason)
        if state == "aborted":
            return "aborted"
        if state == "enabled":
            confidence_tier = self._auto_checkbox_confidence_tier()
            if confidence_tier == "strong_enabled":
                self.log(f"Auto checkbox appears already enabled; skipping toggle | {reason}")
                if startup_auto:
                    self._record_startup_auto_result("already_enabled")
                return "already_enabled"
            self.log(f"Auto checkbox enabled read is weak/ambiguous; not trusting it as authoritative | {reason}")
            state = "unknown"
        if state == "weak_enabled":
            if manual_resume_auto:
                self.log(f"{state_label} leans enabled from repeated checkbox samples; using compact resume verify path | {reason}")
                return "weak_enabled"
            self.log(f"Auto checkbox weak-enabled lean is not authoritative in this context; treating as unreadable | {reason}")
            state = "unknown"
        if state == "disabled":
            self.log(f"Auto checkbox appears off; clicking to enable | {reason}")
            self.click(
                self.cfg["AUTO_CHECKBOX"],
                reason,
                offset=(-self.cfg["AUTO_LEFT_NUDGE"], 0),
                settle=0.20,
            )
            if startup_auto:
                self._record_startup_auto_result("clicked")
            return "clicked"
        if startup_auto:
            if exact_initial_auto_start:
                self.log(
                    "Startup auto state unreadable after retry; skipping speculative checkbox click and requesting one more validation read | "
                    f"{reason}"
                )
            else:
                self.log(f"{state_label} still unreadable after retry; skipping speculative checkbox click | {reason}")
            self._record_startup_auto_result("uncertain")
            return "uncertain"
        if allow_uncertain_enable:
            if manual_resume_auto:
                self.log(
                    f"{state_label} uncertain after repeated reads; deferring extra validation to bounded recovery path | {reason}"
                )
                return "uncertain"
            self.log(f"{state_label} uncertain; validating one more time before any enable click | {reason}")
            if not self._interruptible_sleep(0.05, f"{reason} auto state validation"):
                return "aborted"
            post_state = self.auto_checkbox_state()
            if diagnostic_auto:
                self._log_auto_checkbox_state_read(reason, 3, post_state)
            if post_state == "enabled":
                self.log(f"{state_label} uncertain; validation says Auto is already enabled | {reason}")
                return "already_enabled"
            if post_state == "disabled":
                self.log(f"{state_label} uncertain; validation confirmed Auto is off, enabling now | {reason}")
                self.click(
                    self.cfg["AUTO_CHECKBOX"],
                    reason,
                    offset=(-self.cfg["AUTO_LEFT_NUDGE"], 0),
                    settle=0.20,
                )
                return "clicked"
            self.log(f"{state_label} uncertain after validation; skipping speculative checkbox click | {reason}")
            return "uncertain"
        self.log(f"{state_label} uncertain; using cautious fallback | {reason}")
        if startup_auto:
            self._record_startup_auto_result("uncertain")
        return "uncertain"

    def _fuzzy_word_seen(self, text, targets, threshold=0.72):
        words = re.findall(r"[a-z0-9]+", normalize_text(text))
        for word in words:
            for target in targets:
                if target in word or difflib.SequenceMatcher(None, word, target).ratio() >= threshold:
                    return True
        return False

    def is_target_trait(self, trait):
        if self.roll_domain == "powers":
            return bool(trait and trait in SUPPORTED_POWER_DEFINITIONS and trait in self.power_rules)
        trait = canonical_spec_trait(trait)
        return bool(trait and trait in SUPPORTED_SPEC_TRAITS and trait in self.rules)

    def is_rollable_non_target_trait(self, trait):
        return bool(trait and not self.is_target_trait(trait))

    def detect_rollable_trait(self, text):
        return detect_rollable_trait(text)

    def _generic_trait_word_is_stat_fragment(self, word):
        return _ocr_word_is_stat_fragment(word)

    def _unsupported_trait_hint_from_text(self, text):
        cleaned = normalize_text(text)
        if not self.has_current_spec_marker(cleaned):
            return ""
        numbers = extract_numbers(cleaned)
        has_roll_signal = bool(numbers or self._has_activity_stat_signal(cleaned))
        if not has_roll_signal:
            return ""
        if detect_trait(cleaned):
            return ""
        compact = re.sub(r"[^a-z0-9]+", " ", cleaned).strip()
        compact = re.sub(
            r"\b(?:current|curent|curren|cument|spee|spec|specs|trait|passive|stats?)\b",
            " ",
            compact,
        )
        compact = re.sub(r"\b(?:damage|dmg|crit|chance|rate|range|speed|cooldown|drop|luck|npc|cap)\b", " ", compact)
        raw_words = [word for word in re.findall(r"[a-z]{4,}", compact) if word not in {"current", "spec"}]
        words = [
            word
            for word in raw_words
            if not self._generic_trait_word_is_stat_fragment(word)
        ]
        if raw_words and not words:
            return ""
        return words[0] if words else "non_target"

    def _generic_rollable_non_target_from_text(self, text):
        hint = self._unsupported_trait_hint_from_text(text)
        if not hint:
            return None
        return "non_target"

    def _reroll_popup_signal(self, text):
        cleaned = normalize_text(text)
        compact = cleaned.replace(" ", "")
        has_reroll = (
            "reroll" in compact
            or "rer0ll" in compact
            or self._fuzzy_word_seen(cleaned, ("reroll", "rerol"), 0.70)
        )
        has_sure = "sure" in compact or self._fuzzy_word_seen(cleaned, ("sure",), 0.74)
        has_want = "want" in compact or self._fuzzy_word_seen(cleaned, ("want",), 0.74)
        has_confirm = any(token in compact for token in ("confirm", "yes", "accept", "continue"))
        has_question_flow = has_sure and (has_want or has_confirm)
        return (has_reroll and (has_sure or has_want or has_confirm)) or (has_question_flow and has_reroll), cleaned

    def _reroll_popup_maybe_signal(self, cleaned):
        compact = str(cleaned or "").replace(" ", "")
        return bool(
            "reroll" in compact
            or "rer0ll" in compact
            or "sure" in compact
            or "want" in compact
            or any(token in compact for token in ("confirm", "yes", "accept", "continue"))
        )

    def popup_active(self, log=False, context="popup", fast=False):
        samples = []
        active = False
        need_fallback_pass = True
        maybe_signal_seen = False
        passes = (7,) if fast else (7, 6)
        for idx, psm in enumerate(passes):
            text = self.ocr_region(self.cfg["POPUP_REGION"], psm=psm)
            detected, cleaned = self._reroll_popup_signal(text)
            samples.append(f"psm{psm}={self._compact_debug_text(cleaned) or '<empty>'}")
            maybe_signal = self._reroll_popup_maybe_signal(cleaned)
            maybe_signal_seen = maybe_signal_seen or maybe_signal
            active = active or detected
            if detected:
                need_fallback_pass = False
                break
            if fast and idx == 0 and not maybe_signal:
                need_fallback_pass = False
                break
        if fast and not active and need_fallback_pass:
            text = self.ocr_region(self.cfg["POPUP_REGION"], psm=6)
            detected, cleaned = self._reroll_popup_signal(text)
            samples.append(f"psm6={self._compact_debug_text(cleaned) or '<empty>'}")
            maybe_signal_seen = maybe_signal_seen or self._reroll_popup_maybe_signal(cleaned)
            active = active or detected
        if log:
            self.log(f"{context} popup OCR | active={active} | {' | '.join(samples)}")
        self.last_popup_state = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "context": context,
            "active": bool(active),
            "samples": samples,
            "fast": bool(fast),
            "maybe_signal": bool(maybe_signal_seen),
        }
        self.record_decision_chain(subsystem="Popup", popup_active=bool(active), popup_context=context)
        return active

    def _popup_active_checked(self, log=False, context="popup", fast=False):
        try:
            return self.popup_active(log=log, context=context, fast=fast)
        except TypeError:
            return self.popup_active(log=log, context=context)

    def _last_popup_probe_clearly_inactive(self, expected_context=None):
        state = self.last_popup_state if isinstance(self.last_popup_state, dict) else {}
        active = state.get("active")
        if active is True:
            return False
        if active is None:
            return True
        if expected_context and state.get("context") not in (None, expected_context):
            return True
        samples = state.get("samples") or []
        if not samples:
            return True
        return not bool(state.get("maybe_signal"))

    def banner_active(self):
        text = self.ocr_region(self.cfg["PROTECTED_REGION"])
        return "protected" in text or "cannot" in text

    def _has_activity_stat_signal(self, text):
        normalized = normalize_stat_tokens(text)
        return any(
            token in normalized
            for token in (
                "combo_ramp",
                "damage",
                "crit_rate",
                "crit_damage",
                "drop",
                "luck",
                "npc_damage",
            )
        )

    def _recovery_text_quality(self, text):
        cleaned = normalize_text(text)
        trait = self.detect_rollable_trait(cleaned) or self._generic_rollable_non_target_from_text(cleaned)
        numbers = extract_numbers(cleaned)
        stat_signal = self._has_activity_stat_signal(cleaned)
        marker = self.has_current_spec_marker(cleaned)
        useful = bool(trait or stat_signal or marker)
        unreliable = not useful or len(cleaned) <= 6
        return cleaned, trait, numbers, stat_signal, marker, useful, unreliable

    def _recovery_numbers_changed(self, baseline_numbers, numbers):
        if not baseline_numbers or not numbers:
            return False
        base = [round(float(value), 2) for value in baseline_numbers]
        current = [round(float(value), 2) for value in numbers]
        return base != current

    def _recovery_text_materially_different(self, baseline_clean, cleaned, baseline_numbers, numbers):
        if self._recovery_numbers_changed(baseline_numbers, numbers):
            return True
        if not baseline_clean or not cleaned:
            return False
        similarity = difflib.SequenceMatcher(None, baseline_clean, cleaned).ratio()
        return cleaned != baseline_clean and similarity < 0.86

    def _recovery_text_signal(self, raw_text, baseline_clean, baseline_numbers):
        cleaned, trait, numbers, stat_signal, marker, _useful, unreliable = self._recovery_text_quality(raw_text)
        if unreliable:
            return cleaned, None

        materially_different = self._recovery_text_materially_different(
            baseline_clean,
            cleaned,
            baseline_numbers,
            numbers,
        )
        baseline_marker = self.has_current_spec_marker(baseline_clean)
        structured_without_marker = bool(trait and stat_signal and len(numbers) >= 3)
        strong_structure = bool(marker or baseline_marker or structured_without_marker)

        if marker and (trait or stat_signal) and materially_different:
            return cleaned, "current_spec_marker_changed"
        if trait:
            baseline_trait = self.detect_rollable_trait(baseline_clean) or self._generic_rollable_non_target_from_text(baseline_clean)
            if strong_structure and trait != baseline_trait and materially_different and (stat_signal or numbers):
                return cleaned, f"trait_changed:{trait}"
        if strong_structure and stat_signal and numbers and self._recovery_numbers_changed(baseline_numbers, numbers):
            return cleaned, "stat_numbers_changed"
        if strong_structure and trait and numbers and self._recovery_numbers_changed(baseline_numbers, numbers):
            return cleaned, "trait_values_changed"
        if strong_structure and materially_different and (trait or stat_signal) and numbers:
            return cleaned, "structured_ocr_text_changed"

        return cleaned, None

    def _watchdog_text_only_marker_change_is_weak(self, reason, image_changed, baseline_numbers, numbers, ui_signals=None):
        if reason not in {
            "current_spec_marker_changed",
            "stat_numbers_changed",
            "trait_values_changed",
            "structured_ocr_text_changed",
        }:
            return False
        if image_changed:
            return False
        if not any("watchdog" in str(signal).lower() for signal in (ui_signals or [])):
            return False
        return True

    def _recovery_failure_outcome(self, samples, baseline_clean, polls, image_changed_samples):
        readable_samples = [sample for sample in samples if not sample.get("unreliable")]
        if readable_samples:
            for sample in readable_samples:
                blocked_reason = self._session_blocked_ocr_reason(sample.get("cleaned") or "")
                if blocked_reason:
                    return "session_blocked", blocked_reason
            if all(sample.get("trait_only") for sample in readable_samples):
                return "not_rolling", "trait_only_sample"

            baseline_matches = [
                sample
                for sample in readable_samples
                if sample.get("cleaned") and sample.get("cleaned") == baseline_clean
            ]
            if baseline_clean and baseline_matches:
                return "not_rolling", "no_material_change"

            if any(sample.get("materially_different") for sample in readable_samples):
                return "not_rolling", "readable_insufficient_change"

            return "not_rolling", "readable_no_activity_signal"

        unreadable = sum(1 for sample in samples if sample.get("unreliable")) >= max(1, polls - 1)
        classification = self._verify_state_label(False, unreadable, image_changed_samples > 0)
        if classification == "unreadable_but_changed":
            return classification, "unreadable_context_with_screen_change"
        if classification == "unreadable_static":
            return classification, "unreadable_context"
        return classification, "no_verified_rolling_signal"

    def _recovery_candidate_signal(self, baseline_clean, baseline_numbers, image=None):
        try:
            candidates = self.get_stats_ocr_candidates(image=image, region=self.cfg["STATS_REGION"], full=True)
        except Exception as e:
            return "", None, f"multi_source_error:{e}"

        useful = []
        for engine, cleaned, raw in candidates:
            text, trait, numbers, stat_signal, marker, has_useful, _unreliable = self._recovery_text_quality(cleaned)
            if has_useful:
                useful.append((engine, text, trait, numbers, stat_signal, marker, raw))

        if len(useful) < 2:
            sample = useful[0][1] if useful else ""
            return sample, None, f"multi_source_useful={len(useful)}"

        for _engine, text, trait, numbers, stat_signal, marker, _raw in useful:
            materially_different = self._recovery_text_materially_different(
                baseline_clean,
                text,
                baseline_numbers,
                numbers,
            )
            baseline_marker = self.has_current_spec_marker(baseline_clean)
            structured_without_marker = bool(trait and stat_signal and len(numbers) >= 3)
            strong_structure = bool(marker or baseline_marker or structured_without_marker)
            if marker and (trait or stat_signal) and materially_different:
                return text, "multi_source_current_spec_marker_changed", None
            baseline_trait = self.detect_rollable_trait(baseline_clean) or self._generic_rollable_non_target_from_text(baseline_clean)
            if strong_structure and trait and trait != baseline_trait and materially_different and (stat_signal or numbers):
                return text, f"multi_source_trait_changed:{trait}", None
            if strong_structure and stat_signal and numbers and self._recovery_numbers_changed(baseline_numbers, numbers):
                return text, "multi_source_stat_numbers_changed", None
            if strong_structure and trait and numbers and self._recovery_numbers_changed(baseline_numbers, numbers):
                return text, "multi_source_trait_values_changed", None

        return useful[0][1], None, f"multi_source_useful={len(useful)}_but_no_activity_change"

    def _make_recovery_outcome(
        self,
        *,
        confirmed,
        classification,
        reason="",
        rejection_reason="",
        signal_sources=None,
        image_changed_samples=0,
        max_change_score=0.0,
        unreadable=None,
        sample_text="",
        samples=0,
        ui_signals=None,
        weak_samples=0,
        exit_reason="",
        context="",
    ):
        classification = str(classification or ("rolling" if confirmed else "not_rolling")).strip() or "not_rolling"
        resolved_reason = str(reason or "").strip()
        resolved_rejection = str(rejection_reason or "").strip()
        resolved_exit_reason = str(exit_reason or "").strip()
        if unreadable is None:
            unreadable = classification.startswith("unreadable")
        return RecoveryVerifyOutcome(
            confirmed=bool(confirmed),
            classification=classification,
            reason=resolved_reason,
            rejection_reason=resolved_rejection,
            signal_sources=tuple(signal_sources or ()),
            image_changed_samples=int(image_changed_samples or 0),
            max_change_score=round(float(max_change_score or 0.0), 2),
            unreadable=bool(unreadable),
            sample_text=str(sample_text or ""),
            samples=int(samples or 0),
            ui_signals=tuple(ui_signals or ()),
            weak_samples=int(weak_samples or 0),
            exit_reason=resolved_exit_reason or (resolved_rejection if not confirmed else resolved_reason),
            context=str(context or ""),
        )

    def _recovery_outcome_reason(self, outcome):
        if outcome is None:
            return ""
        return str(outcome.reason or outcome.rejection_reason or outcome.exit_reason or "").strip()

    def _apply_recovery_outcome(self, outcome):
        if outcome is None:
            self.last_recovery_verify_unreadable = False
            self.last_recovery_verify_state = "not_rolling"
            self.last_recovery_verify_details = {}
            self.last_recovery_reason = ""
            return
        self.last_recovery_verify_unreadable = bool(outcome.unreadable)
        self.last_recovery_verify_state = outcome.classification
        self.last_recovery_reason = self._recovery_outcome_reason(outcome)
        self.last_recovery_verify_details = {
            "confirmed": bool(outcome.confirmed),
            "classification": outcome.classification,
            "reason": outcome.reason,
            "rejection_reason": outcome.rejection_reason,
            "signal_sources": list(outcome.signal_sources),
            "image_changed_samples": int(outcome.image_changed_samples),
            "max_change_score": round(float(outcome.max_change_score or 0.0), 2),
            "unreadable": bool(outcome.unreadable),
            "sample_text": outcome.sample_text,
            "samples": int(outcome.samples),
            "ui_signals": list(outcome.ui_signals),
            "weak_samples": int(outcome.weak_samples),
            "exit_reason": outcome.exit_reason,
            "context": outcome.context,
        }

    def _recovery_outcome_from_inputs(self, verify_state=None, verify_details=None, verify_reason=None):
        if isinstance(verify_details, RecoveryVerifyOutcome):
            return verify_details
        verify_details = dict(verify_details or {})
        classification = str(verify_state or verify_details.get("classification") or "").strip()
        resolved_reason = str(verify_reason or verify_details.get("reason") or "").strip()
        rejection_reason = str(verify_details.get("rejection_reason") or "").strip()
        confirmed = bool(
            verify_details.get("confirmed")
            if "confirmed" in verify_details
            else (classification == "rolling" and not rejection_reason)
        )
        if not classification:
            classification = "rolling" if confirmed else "not_rolling"
        return self._make_recovery_outcome(
            confirmed=confirmed,
            classification=classification,
            reason=resolved_reason,
            rejection_reason=rejection_reason,
            signal_sources=verify_details.get("signal_sources"),
            image_changed_samples=verify_details.get("image_changed_samples", 0),
            max_change_score=verify_details.get("max_change_score", 0.0),
            unreadable=verify_details.get("unreadable"),
            sample_text=verify_details.get("sample_text", ""),
            samples=verify_details.get("samples", verify_details.get("polls", 0)),
            ui_signals=verify_details.get("ui_signals"),
            weak_samples=verify_details.get("weak_samples", 0),
            exit_reason=verify_details.get("exit_reason", ""),
            context=verify_details.get("context", ""),
        )


    def _startup_confirmation_support(self, verify_state, verify_details=None, verify_reason=None, popup_state=False, popup_cleared=False):
        outcome = self._recovery_outcome_from_inputs(verify_state, verify_details, verify_reason)
        verify_reason = self._recovery_outcome_reason(outcome)
        signal_sources = list(outcome.signal_sources)
        image_changed_samples = int(outcome.image_changed_samples or 0)
        max_change_score = float(outcome.max_change_score or 0.0)
        support_signals = []
        if popup_state or popup_cleared or verify_reason.startswith("popup_"):
            support_signals.append("popup")
        if verify_reason.startswith("banner_"):
            support_signals.append("banner")
        if image_changed_samples > 0 or "image_change" in signal_sources:
            if image_changed_samples > 0:
                support_signals.append("image_change")
        if any(token in verify_reason for token in ("current_spec_marker", "multi_source", "trait", "numbers_changed", "stat_signal")):
            support_signals.append("current_spec_refresh")
        if verify_state == "unreadable_but_changed":
            support_signals.append("unreadable_but_changed")
        non_refresh_signals = [sig for sig in support_signals if sig != "current_spec_refresh"]
        refresh_only_support = (
            "current_spec_refresh" in support_signals
            and not non_refresh_signals
            and image_changed_samples <= 0
        )

        strong = False
        if outcome.classification == "rolling":
            strong = bool(support_signals or (verify_reason and not outcome.unreadable))
            if refresh_only_support:
                strong = False
        elif outcome.classification == "unreadable_but_changed":
            strong = bool(image_changed_samples > 0 or popup_cleared or verify_reason.startswith("popup_"))
        return {
            "strong": strong,
            "signals": support_signals,
            "reason": verify_reason or "none",
            "image_changed_samples": image_changed_samples,
            "max_change_score": round(max_change_score, 2),
        }

    def _startup_accepts_changed_confirmation(self, verify_details=None, verify_reason=None, popup_state=False, popup_cleared=False, phase="startup verify"):
        support = self._startup_confirmation_support(
            "rolling",
            verify_details or {},
            verify_reason,
            popup_state=popup_state,
            popup_cleared=popup_cleared,
        )
        if support["strong"]:
            return True, support
        self.log(
            f"[Startup Verify] marker-only or weak rolling evidence rejected | phase={phase} | "
            f"reason={support.get('reason', 'none')} | support={'+'.join(support.get('signals', [])) or 'none'} | "
            f"image_changed_samples={support.get('image_changed_samples', 0)} | change_score={support.get('max_change_score', 0.0)}"
        )
        return False, support

    def stats_changed(
        self,
        baseline,
        context="Rolling activity",
        ui_signals=None,
        polls_override=None,
        poll_delay_override=None,
        unreadable_fast_fail_polls=None,
        psm_sequence_override=None,
        candidate_signal_enabled=True,
        abandon_on_weak_samples=None,
        post_popup_check_enabled=True,
        initial_popup_known_false=False,
        fast_popup_checks=False,
        initial_banner_known_false=False,
        fast_post_popup_check=False,
        mid_popup_check_enabled=True,
        single_useful_sample_ok=False,
    ):
        verify_started = time.perf_counter()
        self.last_recovery_verify_unreadable = False
        self.last_recovery_verify_state = "not_rolling"
        self.last_recovery_verify_details = {}
        if self._stop_requested(f"{context} verification"):
            self.log("Recovery aborted due to manual stop")
            return False, baseline
        ui_signals = list(ui_signals or [])
        baseline_clean = normalize_text(baseline or "")
        baseline_numbers = extract_numbers(baseline_clean)
        polls = max(1, int(polls_override if polls_override is not None else self.cfg["AUTO_VERIFY_POLLS"]))
        poll_delay = max(
            0.0,
            float(poll_delay_override if poll_delay_override is not None else self.cfg["AUTO_VERIFY_POLL_DELAY"]),
        )
        unreadable_fast_fail_polls = (
            max(1, int(unreadable_fast_fail_polls))
            if unreadable_fast_fail_polls is not None
            else None
        )
        psm_sequence = [int(value) for value in (psm_sequence_override or []) if int(value) in (6, 7)]
        abandon_on_weak_samples = (
            max(1, int(abandon_on_weak_samples))
            if abandon_on_weak_samples is not None
            else None
        )
        if single_useful_sample_ok and abandon_on_weak_samples is None:
            abandon_on_weak_samples = 1
        samples = []
        verify_cache_hits = 0
        verify_cache_misses = 0
        verify_poll_timings = []
        last_poll_img = None
        route_budget_recorded = False

        def finish(changed, text, result, reason="", polls_seen=None):
            nonlocal route_budget_recorded
            elapsed = time.perf_counter() - verify_started
            seen = len(samples) if polls_seen is None else int(polls_seen or 0)
            self.last_verification_cache_stats = {
                "context": context,
                "cache_hits": int(verify_cache_hits),
                "cache_misses": int(verify_cache_misses),
                "polls_seen": seen,
                "polls_planned": polls,
                "elapsed_ms": int(elapsed * 1000),
                "poll_timings": list(verify_poll_timings[-8:]),
                "result": str(result or "unknown"),
                "reason": str(reason or ""),
            }
            if not route_budget_recorded:
                self._record_verify_budget_event(context, elapsed, seen, polls, result, reason)
                route_budget_recorded = True
            return changed, text

        unreliable_samples = 0
        off_target_ui_samples = 0
        image_changed_samples = 0
        max_change_score = 0.0
        weak_samples = 0
        initial_popup = False if initial_popup_known_false else self._popup_active_checked(
            log=True,
            context=f"{context} pre-check",
            fast=fast_popup_checks,
        )
        if self._stop_requested(f"{context} pre-check"):
            self.log("Recovery aborted due to manual stop")
            return finish(False, baseline, "aborted", "manual_stop", 0)
        initial_banner = False if initial_banner_known_false else self.banner_active()
        baseline_img = None
        baseline_signature = None
        try:
            if pyautogui is not None:
                baseline_img = pyautogui.screenshot(region=tuple(self.cfg["STATS_REGION"]))
                baseline_signature = self._region_signature(baseline_img)
        except Exception:
            baseline_img = None
            baseline_signature = None

        self.log(f"{context} baseline OCR | {self._compact_debug_text(baseline_clean) or '<empty>'}")
        if ui_signals:
            self.log(f"{context} UI flow signals | {', '.join(ui_signals)}")

        baseline_blocked_reason = self._session_blocked_ocr_reason(baseline_clean)
        if baseline_blocked_reason:
            elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
            outcome = self._make_recovery_outcome(
                confirmed=False,
                classification="session_blocked",
                rejection_reason=baseline_blocked_reason,
                signal_sources=self._session_blocked_support_signals(baseline_blocked_reason),
                unreadable=False,
                sample_text=baseline_clean,
                samples=0,
                exit_reason=baseline_blocked_reason,
                context=context,
            )
            self._apply_recovery_outcome(outcome)
            self.log(
                f"{context} blocked | reason={baseline_blocked_reason} | "
                f"sample={self._compact_debug_text(baseline_clean) or '<empty>'} | elapsed={elapsed_ms}ms"
            )
            self.record_decision_chain(
                subsystem="Recovery",
                recovery_state="blocked",
                recovery_context=context,
                recovery_reason=self.last_recovery_reason,
                recovery_sample=self._compact_debug_text(baseline_clean, 500),
            )
            return finish(False, baseline, "blocked", baseline_blocked_reason, 0)

        if initial_popup and self.clear_reroll_popup(f"{context} pre-check popup", already_detected=True):
            elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
            self.last_change = time.time()
            outcome = self._make_recovery_outcome(
                confirmed=True,
                classification="rolling",
                reason="popup_confirmed_before_polling",
                signal_sources=("popup",),
                sample_text=baseline_clean,
                samples=0,
                context=context,
            )
            self._apply_recovery_outcome(outcome)
            self.log(f"{context} confirmed | reason={outcome.reason} | elapsed={elapsed_ms}ms")
            self.record_decision_chain(
                subsystem="Recovery",
                recovery_state="confirmed",
                recovery_context=context,
                recovery_reason=self.last_recovery_reason,
            )
            return finish(True, baseline, "confirmed", outcome.reason, 0)

        for index in range(polls):
            if self._stop_requested(f"{context} polling"):
                self.log("Recovery aborted due to manual stop")
                return finish(False, baseline, "aborted", "manual_stop", index)

            poll_started = time.perf_counter()
            poll_cache = {"image": None, "loaded": False}

            def poll_image():
                nonlocal verify_cache_hits, verify_cache_misses, last_poll_img
                if poll_cache["loaded"]:
                    verify_cache_hits += 1
                    return poll_cache["image"]
                poll_cache["loaded"] = True
                try:
                    if pyautogui is not None:
                        poll_cache["image"] = pyautogui.screenshot(region=tuple(self.cfg["STATS_REGION"]))
                        last_poll_img = poll_cache["image"]
                except Exception:
                    poll_cache["image"] = None
                verify_cache_misses += 1
                return poll_cache["image"]

            psm = psm_sequence[index % len(psm_sequence)] if psm_sequence else (7 if index % 2 == 0 else 6)
            img = None
            signature = None
            change_score = 0.0
            image_changed = False
            signature_changed = False
            try:
                img = poll_image()
                signature = self._region_signature(img)
                if baseline_img is not None and baseline_signature is not None:
                    change_score = self._region_change_score(baseline_img, img)
                    signature_changed = bool(signature != baseline_signature)
                    image_changed = bool(signature != baseline_signature and change_score >= self._stats_verify_changed_threshold())
            except Exception:
                img = None
            if image_changed:
                image_changed_samples += 1
                max_change_score = max(max_change_score, change_score)

            ocr_img = poll_image()
            new_text = self._ocr_tesseract_image(ocr_img, psm).strip() if ocr_img is not None else self.ocr_region(self.cfg["STATS_REGION"], psm=psm).strip()
            cleaned, reason = self._recovery_text_signal(new_text, baseline_clean, baseline_numbers)
            _cleaned, _trait, _numbers, _stat_signal, _marker, _useful, unreliable = self._recovery_text_quality(new_text)
            materially_different = self._recovery_text_materially_different(
                baseline_clean,
                cleaned,
                baseline_numbers,
                _numbers,
            )
            trait_only = bool(_trait and not _stat_signal and not _numbers and not _marker)
            if self._watchdog_text_only_marker_change_is_weak(reason, image_changed, baseline_numbers, _numbers, ui_signals):
                self.log(
                    f"{context} rejected text-only watchdog activity | "
                    f"reason={reason} | image_changed={image_changed} | change_score={change_score:.2f}"
                )
                reason = None
                materially_different = False
            poll_elapsed_ms = int((time.perf_counter() - poll_started) * 1000)
            verify_poll_timings.append({
                "poll": index + 1,
                "elapsed_ms": poll_elapsed_ms,
                "cache_hit": bool(verify_cache_hits),
                "cache_miss": bool(poll_cache["loaded"]),
            })
            if unreliable:
                unreliable_samples += 1
                self.log(f"{context} rejected garbage OCR | {self._compact_debug_text(cleaned) or '<empty>'}")
                if "manual_reroll" in " ".join(ui_signals).lower() and self._reroll_popup_maybe_signal(cleaned):
                    self.log(
                        f"{context} modal text seen in stats OCR after popup-region miss | "
                        f"{self._compact_debug_text(cleaned) or '<empty>'}"
                    )
            off_target_reason = self._stats_region_control_text_reason(cleaned or new_text)
            if off_target_reason:
                off_target_ui_samples += 1
            samples.append({
                "poll": index + 1,
                "psm": psm,
                "cleaned": cleaned,
                "reason": reason,
                "unreliable": unreliable,
                "materially_different": materially_different,
                "trait_only": trait_only,
                "image_changed": image_changed,
                "signature_changed": signature_changed,
                "change_score": round(change_score, 2),
                "poll_elapsed_ms": poll_elapsed_ms,
                "cache_hits": verify_cache_hits,
                "cache_misses": verify_cache_misses,
                "off_target_ui_text": bool(off_target_reason),
            })
            self.log(
                f"{context} verify sample {index + 1}/{polls} | psm={psm} | "
                f"reason={reason or 'none'} | unreliable={unreliable} | materially_different={materially_different} | "
                f"image_changed={image_changed} | change_score={change_score:.2f} | trait_only={trait_only} | "
                f"poll_elapsed={poll_elapsed_ms}ms | cache={verify_cache_hits}/{verify_cache_misses} | "
                f"{self._compact_debug_text(cleaned) or '<empty>'}"
            )

            blocked_reason = self._session_blocked_ocr_reason(cleaned or new_text)
            if blocked_reason:
                elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
                outcome = self._make_recovery_outcome(
                    confirmed=False,
                    classification="session_blocked",
                    rejection_reason=blocked_reason,
                    signal_sources=self._session_blocked_support_signals(blocked_reason),
                    image_changed_samples=image_changed_samples,
                    max_change_score=max_change_score,
                    unreadable=False,
                    sample_text=cleaned or new_text,
                    samples=index + 1,
                    ui_signals=ui_signals,
                    weak_samples=weak_samples,
                    exit_reason=blocked_reason,
                    context=context,
                )
                self._apply_recovery_outcome(outcome)
                self.log(
                    f"{context} blocked | reason={blocked_reason} | "
                    f"sample={self._compact_debug_text(cleaned or new_text) or '<empty>'} | elapsed={elapsed_ms}ms"
                )
                self.record_decision_chain(
                    subsystem="Recovery",
                    recovery_state="blocked",
                    recovery_context=context,
                    recovery_reason=self.last_recovery_reason,
                    recovery_sample=self._compact_debug_text(cleaned or new_text, 500),
                    image_changed_samples=image_changed_samples,
                    max_change_score=round(max_change_score, 2),
                )
                return finish(False, baseline, "blocked", blocked_reason, index + 1)

            if not reason and not unreliable and not materially_different and not image_changed and not trait_only:
                weak_samples += 1

            if abandon_on_weak_samples and weak_samples >= abandon_on_weak_samples and index + 1 >= abandon_on_weak_samples:
                elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
                weak_exit_reason = "weak_non_improving_bridge_probe" if "bridge probe" in context.lower() else "weak_non_improving_dead_phase"
                outcome = self._make_recovery_outcome(
                    confirmed=False,
                    classification="not_rolling",
                    rejection_reason=weak_exit_reason,
                    signal_sources=("ocr", "popup", "banner", "image_change"),
                    image_changed_samples=image_changed_samples,
                    max_change_score=max_change_score,
                    unreadable=False,
                    sample_text=cleaned or baseline_clean,
                    samples=index + 1,
                    weak_samples=weak_samples,
                    exit_reason=weak_exit_reason,
                    context=context,
                )
                self._apply_recovery_outcome(outcome)
                self.last_recovery_verify_details["samples_detail"] = list(samples[-3:])
                self.log(
                    f"{context} early exit | reason={weak_exit_reason} | weak_samples={weak_samples}/{index + 1} | "
                    f"image_changed_samples={image_changed_samples} | max_change_score={max_change_score:.2f} | elapsed={elapsed_ms}ms"
                )
                self.record_decision_chain(
                    subsystem="Recovery",
                    recovery_state="failed",
                    recovery_context=context,
                    recovery_reason=self.last_recovery_reason,
                    weak_samples=weak_samples,
                    image_changed_samples=image_changed_samples,
                    max_change_score=round(max_change_score, 2),
                    samples=samples[-3:],
                )
                return finish(False, baseline, "failed", weak_exit_reason, index + 1)

            if reason:
                elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
                self.last_text = cleaned or new_text
                self.last_change = time.time()
                outcome = self._make_recovery_outcome(
                    confirmed=True,
                    classification="rolling",
                    reason=reason,
                    signal_sources=("ocr", "popup", "banner", "image_change"),
                    image_changed_samples=image_changed_samples,
                    max_change_score=max_change_score,
                    unreadable=False,
                    sample_text=cleaned or new_text,
                    samples=index + 1,
                    context=context,
                )
                self._apply_recovery_outcome(outcome)
                self.log(f"{context} confirmed | reason={reason} | elapsed={elapsed_ms}ms")
                self.record_decision_chain(
                    subsystem="Recovery",
                    recovery_state="confirmed",
                    recovery_context=context,
                    recovery_reason=reason,
                    recovery_sample=self._compact_debug_text(cleaned or new_text, 500),
                )
                return finish(True, cleaned or new_text, "confirmed", reason, index + 1)

            if mid_popup_check_enabled and index == polls // 2:
                popup_now = self._popup_active_checked(
                    log=True,
                    context=f"{context} mid-check",
                    fast=fast_popup_checks,
                )
                if self._stop_requested(f"{context} mid-check"):
                    self.log("Recovery aborted due to manual stop")
                    return finish(False, baseline, "aborted", "manual_stop", index + 1)
                if popup_now and self.clear_reroll_popup(f"{context} mid-check popup", already_detected=True):
                    elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
                    self.last_change = time.time()
                    outcome = self._make_recovery_outcome(
                        confirmed=True,
                        classification="rolling",
                        reason="popup_confirmed_mid_polling",
                        signal_sources=("popup",),
                        sample_text=cleaned or baseline,
                        samples=index + 1,
                        context=context,
                    )
                    self._apply_recovery_outcome(outcome)
                    self.log(f"{context} confirmed | reason={outcome.reason} | elapsed={elapsed_ms}ms")
                    self.record_decision_chain(subsystem="Recovery", recovery_state="confirmed", recovery_context=context, recovery_reason=self.last_recovery_reason)
                    return finish(True, cleaned or baseline, "confirmed", outcome.reason, index + 1)
                banner_now = self.banner_active()
                if initial_popup and not popup_now:
                    elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
                    self.last_change = time.time()
                    outcome = self._make_recovery_outcome(
                        confirmed=True,
                        classification="rolling",
                        reason="popup_disappeared",
                        signal_sources=("popup",),
                        sample_text=cleaned or baseline,
                        samples=index + 1,
                        context=context,
                    )
                    self._apply_recovery_outcome(outcome)
                    self.log(f"{context} confirmed | reason={outcome.reason} | elapsed={elapsed_ms}ms")
                    self.record_decision_chain(subsystem="Recovery", recovery_state="confirmed", recovery_context=context, recovery_reason=self.last_recovery_reason)
                    return finish(True, cleaned or baseline, "confirmed", outcome.reason, index + 1)
                if initial_banner and not banner_now:
                    elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
                    self.last_change = time.time()
                    outcome = self._make_recovery_outcome(
                        confirmed=True,
                        classification="rolling",
                        reason="banner_cleared",
                        signal_sources=("banner",),
                        sample_text=cleaned or baseline,
                        samples=index + 1,
                        context=context,
                    )
                    self._apply_recovery_outcome(outcome)
                    self.log(f"{context} confirmed | reason={outcome.reason} | elapsed={elapsed_ms}ms")
                    self.record_decision_chain(subsystem="Recovery", recovery_state="confirmed", recovery_context=context, recovery_reason=self.last_recovery_reason)
                    return finish(True, cleaned or baseline, "confirmed", outcome.reason, index + 1)

            if unreadable_fast_fail_polls and not ui_signals and not initial_popup and not initial_banner and unreliable_samples >= unreadable_fast_fail_polls and index + 1 >= unreadable_fast_fail_polls:
                elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
                verify_state = self._verify_state_label(False, True, image_changed_samples > 0)
                rejection_reason = "unreadable_context_with_screen_change" if image_changed_samples > 0 else "unreadable_context"
                outcome = self._make_recovery_outcome(
                    confirmed=False,
                    classification=verify_state,
                    rejection_reason=rejection_reason,
                    signal_sources=("ocr", "popup", "banner", "image_change"),
                    image_changed_samples=image_changed_samples,
                    max_change_score=max_change_score,
                    unreadable=True,
                    sample_text=cleaned or baseline_clean,
                    samples=index + 1,
                    context=context,
                )
                self._apply_recovery_outcome(outcome)
                self.last_recovery_verify_details["samples_detail"] = list(samples[-3:])
                self._write_ocr_debug_event(
                    "recovery_confirmation_fast_failed_unreadable",
                    {
                        "context": context,
                        "baseline": baseline_clean,
                        "baseline_numbers": baseline_numbers,
                        "samples": samples,
                        "polls": polls,
                        "unreliable_samples": unreliable_samples,
                        "verify_state": verify_state,
                        "rejection_reason": rejection_reason,
                        "image_changed_samples": image_changed_samples,
                        "max_change_score": max_change_score,
                    },
                )
                self.log(
                    f"{context} fast unreadable verify | samples={unreliable_samples}/{index + 1} | "
                    f"image_changed_samples={image_changed_samples} | max_change_score={max_change_score:.2f} | "
                    f"classification={verify_state} | rejection_reason={rejection_reason} | elapsed={elapsed_ms}ms"
                )
                self.record_decision_chain(subsystem="Recovery", recovery_state="failed", recovery_context=context, recovery_reason=self.last_recovery_reason, unreliable_samples=unreliable_samples, image_changed_samples=image_changed_samples, max_change_score=round(max_change_score, 2), samples=samples[-3:])
                return finish(False, baseline, "failed", rejection_reason, index + 1)

            if index < polls - 1 and not self._interruptible_sleep(poll_delay, f"{context} polling delay"):
                self.log("Recovery aborted due to manual stop")
                return finish(False, baseline, "aborted", "manual_stop", index + 1)

        popup_confirmed_after_polling = False
        if post_popup_check_enabled:
            if fast_post_popup_check:
                popup_confirmed_after_polling = self._popup_active_checked(
                    log=True,
                    context=f"{context} post-check popup",
                    fast=True,
                ) and self.clear_reroll_popup(f"{context} post-check popup", already_detected=True)
            else:
                popup_confirmed_after_polling = self.confirm_popup_if_present(f"{context} post-check popup")
        if popup_confirmed_after_polling:
            elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
            self.last_change = time.time()
            outcome = self._make_recovery_outcome(
                confirmed=True,
                classification="rolling",
                reason="popup_confirmed_after_polling",
                signal_sources=("popup",),
                sample_text=baseline_clean,
                samples=polls,
                context=context,
            )
            self._apply_recovery_outcome(outcome)
            self.log(f"{context} confirmed | reason={outcome.reason} | elapsed={elapsed_ms}ms")
            self._record_timing_event("recovery_verify", elapsed_ms / 1000.0, context=context, result="confirmed", reason=outcome.reason)
            self.record_decision_chain(subsystem="Recovery", recovery_state="confirmed", recovery_context=context, recovery_reason=self.last_recovery_reason)
            return finish(True, baseline, "confirmed", outcome.reason, polls)

        watchdog_ui_flow = any("watchdog" in str(signal).lower() for signal in ui_signals)
        if ui_signals and unreliable_samples >= max(1, polls - 1) and watchdog_ui_flow:
            elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
            reason = "stats_region_off_target_ui_text" if off_target_ui_samples >= max(1, polls - 1) else "stats_ocr_unreliable_after_watchdog"
            outcome = self._make_recovery_outcome(
                confirmed=False,
                classification="not_rolling",
                rejection_reason=reason,
                signal_sources=("ocr",),
                sample_text=baseline_clean,
                samples=polls,
                ui_signals=ui_signals,
                unreadable=True,
                weak_samples=weak_samples,
                exit_reason=reason,
                context=context,
            )
            self._apply_recovery_outcome(outcome)
            self.last_recovery_verify_unreadable = True
            self.log(
                f"{context} rejected unreliable watchdog verification | reason={reason} | "
                f"unreliable_samples={unreliable_samples}/{polls} | off_target_ui_samples={off_target_ui_samples}/{polls} | "
                f"elapsed={elapsed_ms}ms"
            )
            if reason == "stats_region_off_target_ui_text":
                self._log_with_cooldown(
                    "stats_region_off_target_ui_text",
                    "Current roll OCR region appears misconfigured; reading UI/control text instead of roll stats",
                    cooldown=30.0,
                )
            self._record_timing_event("recovery_verify", elapsed_ms / 1000.0, context=context, result="failed", reason=reason)
            self.record_decision_chain(
                subsystem="Recovery",
                recovery_state="failed",
                recovery_context=context,
                recovery_reason=reason,
                unreliable_samples=unreliable_samples,
                off_target_ui_samples=off_target_ui_samples,
                samples=samples[-3:],
            )
            return finish(False, baseline, "failed", reason, polls)

        if ui_signals and unreliable_samples >= max(1, polls - 1):
            elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
            self.last_change = time.time()
            reason = f"stats_ocr_unreliable_after_ui_flow:{'+'.join(ui_signals)}"
            outcome = self._make_recovery_outcome(
                confirmed=True,
                classification="rolling",
                reason=reason,
                signal_sources=("ocr", "popup", "banner", "image_change"),
                sample_text=baseline_clean,
                samples=polls,
                ui_signals=ui_signals,
                context=context,
            )
            self._apply_recovery_outcome(outcome)
            self.log(f"{context} confirmed | reason={reason} | elapsed={elapsed_ms}ms")
            self._record_timing_event("recovery_verify", elapsed_ms / 1000.0, context=context, result="confirmed", reason=reason)
            self.record_decision_chain(subsystem="Recovery", recovery_state="confirmed", recovery_context=context, recovery_reason=reason, unreliable_samples=unreliable_samples)
            return finish(True, baseline, "confirmed", reason, polls)

        candidate_text = ""
        candidate_reason = None
        candidate_note = None
        if candidate_signal_enabled:
            candidate_text, candidate_reason, candidate_note = self._recovery_candidate_signal(
                baseline_clean,
                baseline_numbers,
                image=last_poll_img,
            )
        if candidate_reason:
            elapsed_ms = int((time.perf_counter() - verify_started) * 1000)
            self.last_text = candidate_text or baseline
            self.last_change = time.time()
            outcome = self._make_recovery_outcome(
                confirmed=True,
                classification="rolling",
                reason=candidate_reason,
                signal_sources=("ocr", "image_change"),
                image_changed_samples=image_changed_samples,
                max_change_score=max_change_score,
                sample_text=candidate_text or baseline,
                samples=polls,
                context=context,
            )
            self._apply_recovery_outcome(outcome)
            self.log(f"{context} confirmed | reason={candidate_reason} | elapsed={elapsed_ms}ms")
            self.record_decision_chain(subsystem="Recovery", recovery_state="confirmed", recovery_context=context, recovery_reason=candidate_reason, recovery_sample=self._compact_debug_text(candidate_text or baseline, 500))
            return finish(True, candidate_text or baseline, "confirmed", candidate_reason, polls)
        if candidate_note:
            self.log(f"{context} multi-source OCR check | {candidate_note}")

        verify_state, rejection_reason = self._recovery_failure_outcome(
            samples,
            baseline_clean,
            polls,
            image_changed_samples,
        )
        outcome = self._make_recovery_outcome(
            confirmed=False,
            classification=verify_state,
            rejection_reason=rejection_reason,
            signal_sources=("ocr", "popup", "banner", "image_change"),
            image_changed_samples=image_changed_samples,
            max_change_score=max_change_score,
            unreadable=verify_state.startswith("unreadable"),
            sample_text=baseline_clean,
            samples=polls,
            context=context,
        )
        self._apply_recovery_outcome(outcome)
        self.last_recovery_verify_details["unreliable_samples"] = unreliable_samples
        self.last_recovery_verify_details["samples_detail"] = list(samples[-3:])
        self._write_ocr_debug_event(
            "recovery_confirmation_failed",
            {
                "context": context,
                "baseline": baseline_clean,
                "baseline_numbers": baseline_numbers,
                "samples": samples,
                "polls": polls,
                "unreliable_samples": unreliable_samples,
                "ui_signals": ui_signals,
                "verify_state": verify_state,
                "rejection_reason": rejection_reason,
                "image_changed_samples": image_changed_samples,
                "max_change_score": max_change_score,
            },
        )
        self.log(
            f"{context} confirmation failed | no activity signal after {polls} polls | "
            f"unreliable_stats_samples={unreliable_samples}/{polls} | image_changed_samples={image_changed_samples} | "
            f"max_change_score={max_change_score:.2f} | classification={verify_state} | "
            f"rejection_reason={rejection_reason} | elapsed={int((time.perf_counter() - verify_started) * 1000)}ms"
        )
        self._record_timing_event(
            "recovery_verify",
            time.perf_counter() - verify_started,
            context=context,
            result="failed",
            reason=rejection_reason,
        )
        self.record_decision_chain(subsystem="Recovery", recovery_state="failed", recovery_context=context, recovery_reason=self.last_recovery_reason, unreliable_samples=unreliable_samples, image_changed_samples=image_changed_samples, max_change_score=round(max_change_score, 2), samples=samples[-3:])
        return finish(False, baseline, "failed", rejection_reason, polls)

    def clear_recovery_failures(self, reason):
        if self.recovery_failures:
            self.log(f"Recovery attempts reset | {reason}")
        self.recovery_failures = 0

    def recovery_failed_should_stop(self, label, reason):
        self.recovery_failures += 1
        max_attempts = max(1, int(self.cfg.get("MAX_RECOVERY_ATTEMPTS", 3)))
        self.log(f"{label} failed | recovery attempt {self.recovery_failures}/{max_attempts} | {reason}")
        self.last_important_event = f"{label} failed: {reason}"
        self.last_recovery_reason = reason
        self.record_decision_chain(
            subsystem="Recovery",
            recovery_state="retrying" if self.recovery_failures < max_attempts else "failed",
            recovery_context=label,
            recovery_reason=reason,
            recovery_attempt=f"{self.recovery_failures}/{max_attempts}",
        )
        if self.recovery_failures >= max_attempts:
            self._maybe_auto_capture_debug_snapshot(
                "recovery_failure",
                extra={"label": label, "reason": reason, "attempts": self.recovery_failures},
            )
            return True
        self.last_change = time.time()
        self.log("Recovery failed but will retry before stopping.")
        return False

    def _watchdog_timeout(self):
        try:
            configured = float(self.cfg.get("UNEXPECTED_NO_ROLL_TIMEOUT", 0.0))
        except Exception:
            configured = 0.0
        if configured > 0:
            return configured
        return max(0.1, float(self.cfg.get("STUCK_TIMEOUT", DEFAULT_CONFIG["STUCK_TIMEOUT"])))

    def _watchdog_cooldown(self):
        try:
            configured = float(self.cfg.get("UNEXPECTED_NO_ROLL_COOLDOWN", 0.0))
        except Exception:
            configured = 0.0
        if configured > 0:
            return configured
        return self._watchdog_timeout()

    def _watchdog_suspicion_timeout(self):
        threshold = self._watchdog_timeout()
        try:
            configured = float(self.cfg.get("UNEXPECTED_NO_ROLL_SUSPECT_TIMEOUT", 0.0))
        except Exception:
            configured = 0.0
        if configured > 0:
            return min(threshold, max(0.5, configured))
        return min(threshold, max(2.6, threshold * 0.48))

    def _watchdog_signature(self, current_text, state, trait):
        cleaned = normalize_text(current_text or self.last_text or "")
        return f"{state or 'unknown'}|{trait or ''}|{cleaned[:160]}"

    def unexpected_not_rolling_watchdog(
        self,
        current_text,
        state,
        trait,
        idle_for,
        popup_known_clear=False,
        banner_known_clear=False,
        stage="recovery",
        allow_early=False,
    ):
        if not self.cfg.get("UNEXPECTED_NO_ROLL_WATCHDOG_ENABLED", True):
            self._set_recovery_route_snapshot(
                result="skipped",
                route_reason="watchdog_disabled",
                auto_state="unknown",
                context="watchdog",
            )
            return "skipped"
        if self.stop_event.is_set():
            self._set_recovery_route_snapshot(
                result="skipped",
                route_reason="watchdog_stop_requested",
                auto_state="unknown",
                context="watchdog",
            )
            return "skipped"
        if state in ("GOD", "HIGH_VALUE", "BAD", "DISABLED"):
            self.log(f"Unexpected No-Roll Watchdog | skipped valid stop state | state={state}")
            return "skipped"
        if self.watchdog_in_progress or self.recovery_in_progress or self.manual_reroll_active:
            self.log(
                "Unexpected No-Roll Watchdog | skipped active flow | "
                f"watchdog={self.watchdog_in_progress} recovery={self.recovery_in_progress} "
                f"manual_reroll={self.manual_reroll_active}"
            )
            return "skipped"
        threshold = self._watchdog_timeout()
        suspicion_threshold = self._watchdog_suspicion_timeout()
        effective_threshold = suspicion_threshold if stage == "suspicion" else threshold
        if not allow_early and float(idle_for or 0.0) < effective_threshold:
            return "skipped"

        signature = self._watchdog_signature(current_text, state, trait)
        now = time.time()
        cooldown = self._watchdog_cooldown()
        if signature == self.last_watchdog_signature and now - self.last_watchdog_attempt_at < cooldown:
            self.log(
                "Unexpected No-Roll Watchdog | suppressed duplicate stale event | "
                f"idle={float(idle_for or 0.0):.1f}s cooldown={cooldown:.1f}s"
            )
            return "skipped"

        blocked_reason = self._session_blocked_ocr_reason(current_text or self.last_text or "")
        if blocked_reason:
            self.log(
                "Unexpected No-Roll Watchdog | skipped session-blocked screen | "
                f"reason={blocked_reason} | sample={self._compact_debug_text(current_text or self.last_text or '')}"
            )
            self._set_recovery_route_snapshot(
                result="skipped",
                route_reason=blocked_reason,
                auto_state="not_checked",
                rolling_confirmed=False,
                failure_type=blocked_reason,
                support_signals=self._session_blocked_support_signals(blocked_reason),
                context="watchdog",
            )
            return "skipped"

        if not popup_known_clear and self.popup_active(log=True, context="Unexpected No-Roll Watchdog guard"):
            self.log("Unexpected No-Roll Watchdog | skipped popup active")
            return "skipped"
        if not banner_known_clear and self.banner_active():
            self.log("Unexpected No-Roll Watchdog | skipped banner/protected state active")
            return "skipped"

        self.watchdog_in_progress = True
        try:
            trait_text = display_trait(trait) if trait else "unknown"
            baseline = current_text or self.last_text or ""
            suspicion_details = dict(self.last_recovery_verify_details or {})
            suspicion_reason = str(self.last_recovery_reason or "")
            self.log(
                "Unexpected No-Roll Watchdog | detected | "
                f"idle={float(idle_for or 0.0):.1f}s threshold={effective_threshold:.1f}s "
                f"full_threshold={threshold:.1f}s suspicion_threshold={suspicion_threshold:.1f}s "
                f"stage={stage} state={state or 'unknown'} trait={trait_text} "
                f"baseline={self._compact_debug_text(baseline)}"
            )

            checkbox_state = self.auto_checkbox_state()
            self._log_auto_checkbox_state_read("Unexpected No-Roll Watchdog", 1, checkbox_state)
            checkbox_confidence = self._auto_checkbox_confidence_tier()
            effective_checkbox_state = self._effective_auto_checkbox_state(checkbox_state, checkbox_confidence)
            self._write_ocr_debug_event(
                "unexpected_no_roll_watchdog",
                {
                    "phase": "detected",
                    "idle_for": round(float(idle_for or 0.0), 2),
                    "threshold": effective_threshold,
                    "stage": stage,
                    "state": state,
                    "trait": trait,
                    "signature": signature,
                    "checkbox_state": checkbox_state,
                    "effective_checkbox_state": effective_checkbox_state,
                    "baseline": self._compact_debug_text(baseline, 500),
                },
            )

            if effective_checkbox_state == "strong_enabled":
                self.log(
                    "Unexpected No-Roll Watchdog | Auto appears enabled; "
                    "skipping re-enable click and falling through to recovery"
                )
                self._write_ocr_debug_event(
                    "unexpected_no_roll_watchdog",
                    {
                        "phase": "skipped",
                        "reason": "auto_visually_enabled",
                        "state": state,
                        "trait": trait,
                        "signature": signature,
                    },
                )
                return "skipped"
            if effective_checkbox_state not in ("disabled", "ambiguous", "weak_enabled"):
                self.log(
                    "Unexpected No-Roll Watchdog | skipped unsupported checkbox state="
                    f"{checkbox_state} effective={effective_checkbox_state}"
                )
                return "skipped"
            watchdog_profile = self._watchdog_verify_profile(stage)
            fast_dead_watchdog = False
            stale_non_target_proof = ""
            if effective_checkbox_state == "weak_enabled":
                fast_dead_watchdog = self._watchdog_dead_weak_enabled_fast_path(
                    suspicion_details,
                    suspicion_reason,
                    stage=stage,
                    popup_known_clear=popup_known_clear,
                    banner_known_clear=banner_known_clear,
                )
                if fast_dead_watchdog:
                    self.log(
                        "Unexpected No-Roll Watchdog | fast dead-screen weak-enabled path accepted; "
                        "skipping redundant compact verify/recheck before controlled auto re-enable"
                    )
                else:
                    if self._compact_watchdog_resume_verify(baseline, watchdog_profile, stage=stage):
                        self._write_ocr_debug_event(
                            "unexpected_no_roll_watchdog",
                            {
                                "phase": "skipped",
                                "reason": "weak_enabled_compact_verify_confirmed_rolling",
                                "state": state,
                                "trait": trait,
                                "signature": signature,
                            },
                        )
                        return "restored"
                    if not self._interruptible_sleep(
                        watchdog_profile["weak_enabled_recheck_delay"],
                        "unexpected no-roll watchdog weak-enabled validation",
                    ):
                        return "failed"
                    checkbox_state = self.auto_checkbox_state()
                    self._log_auto_checkbox_state_read("Unexpected No-Roll Watchdog weak-enabled final recheck", 2, checkbox_state)
                    checkbox_confidence = self._auto_checkbox_confidence_tier()
                    effective_checkbox_state = self._effective_auto_checkbox_state(checkbox_state, checkbox_confidence)
                    if effective_checkbox_state == "strong_enabled":
                        self.log(
                            "Unexpected No-Roll Watchdog | Auto still leans visually enabled after compact verify failure; "
                            "escalating to one controlled re-enable click because rolling still appears stale"
                        )
                    elif effective_checkbox_state not in ("disabled", "ambiguous", "weak_enabled"):
                        self.log(
                            "Unexpected No-Roll Watchdog | skipped unsupported checkbox state after weak-enabled recheck="
                            f"{checkbox_state} effective={effective_checkbox_state}"
                        )
                        return "skipped"
            elif effective_checkbox_state == "ambiguous":
                guard_started = time.perf_counter()
                confirm_changed, confirm_text = self.stats_changed(
                    baseline,
                    "Unexpected No-Roll Watchdog ambiguous checkbox confirm",
                    ui_signals=["watchdog_ambiguous_guard"],
                    polls_override=watchdog_profile["guard_polls"],
                    poll_delay_override=watchdog_profile["guard_poll_delay"],
                    unreadable_fast_fail_polls=2,
                )
                guard_elapsed_ms = int((time.perf_counter() - guard_started) * 1000)
                if confirm_changed:
                    guard_support = self._auto_reenable_guard_support(
                        self.last_recovery_verify_details,
                        self.last_recovery_reason,
                    )
                    if guard_support["strong"]:
                        self.last_text = confirm_text or baseline
                        self.last_change = time.time()
                        self.clear_recovery_failures("Unexpected No-Roll Watchdog guard saw rolling resume")
                        self.log(
                            "Unexpected No-Roll Watchdog | skipped ambiguous checkbox recovery because rolling evidence returned during guard"
                        )
                        self._write_ocr_debug_event(
                            "unexpected_no_roll_watchdog",
                            {
                                "phase": "skipped",
                                "reason": "ambiguous_checkbox_guard_confirmed_rolling",
                                "state": state,
                                "trait": trait,
                                "signature": signature,
                                "guard_support": guard_support,
                            },
                        )
                        return "restored"
                    self.log(
                        "Unexpected No-Roll Watchdog | weak rolling evidence rejected for ambiguous checkbox guard | "
                        f"reason={guard_support.get('reason', 'none')} | "
                        f"support={'+'.join(guard_support.get('signals', [])) or 'none'} | "
                        f"image_changed_samples={guard_support.get('image_changed_samples', 0)} | "
                        f"change_score={guard_support.get('max_change_score', 0.0)}"
                    )
                elif self.last_recovery_verify_state == "session_blocked":
                    blocked_reason = self.last_recovery_reason or "session_blocked"
                    self.log(
                        "Unexpected No-Roll Watchdog | skipped recovery during ambiguous checkbox guard | "
                        f"reason={blocked_reason}"
                    )
                    self._set_recovery_route_snapshot(
                        result="skipped",
                        route_reason=blocked_reason,
                        auto_state="ambiguous",
                        rolling_confirmed=False,
                        failure_type=blocked_reason,
                        support_signals=self._session_blocked_support_signals(blocked_reason),
                        context="watchdog",
                    )
                    return "skipped"
                else:
                    stale_non_target_proof = (
                        (self.last_recovery_verify_details or {}).get("exit_reason")
                        or self.last_recovery_reason
                        or "ambiguous_guard_no_activity"
                    )
                    self.log(
                        "watchdog_non_target_stale_guard_static | "
                        f"stage={stage} | state={state or 'unknown'} | trait={trait_text} | "
                        f"elapsed={guard_elapsed_ms}ms | stale_proof={stale_non_target_proof}"
                    )
                if not self._interruptible_sleep(
                    watchdog_profile["guard_recheck_delay"],
                    "unexpected no-roll watchdog ambiguous checkbox validation",
                ):
                    return "failed"
                checkbox_state = self.auto_checkbox_state()
                self._log_auto_checkbox_state_read("Unexpected No-Roll Watchdog final ambiguous recheck", 2, checkbox_state)
                checkbox_confidence = self._auto_checkbox_confidence_tier()
                effective_checkbox_state = self._effective_auto_checkbox_state(checkbox_state, checkbox_confidence)
                if effective_checkbox_state == "strong_enabled":
                    self.log(
                        "Unexpected No-Roll Watchdog | suppressed ambiguous checkbox click because Auto appears enabled "
                        "after recheck and guard verification did not show strong rolling evidence"
                    )
                    self._set_recovery_route_snapshot(
                        result="skipped",
                        route_reason="ambiguous_checkbox_enabled_without_activity",
                        auto_state=str(effective_checkbox_state),
                        rolling_confirmed=False,
                        failure_type="ambiguous_checkbox_enabled_without_activity",
                        support_signals=["ambiguous_checkbox_guard"],
                        context="watchdog",
                    )
                    self._write_ocr_debug_event(
                        "unexpected_no_roll_watchdog",
                        {
                            "phase": "skipped",
                            "reason": "ambiguous_checkbox_enabled_without_activity",
                            "checkbox_state": checkbox_state,
                            "effective_checkbox_state": effective_checkbox_state,
                            "state": state,
                            "trait": trait,
                            "signature": signature,
                        },
                    )
                    return "skipped"
                elif effective_checkbox_state in ("ambiguous", "weak_enabled"):
                    if state == "NON_TARGET" and stale_non_target_proof:
                        self.log(
                            "watchdog_non_target_stale_auto_reclick_allowed | "
                            f"stage={stage} | state={state or 'unknown'} | trait={trait_text} | "
                            f"checkbox_state={checkbox_state} | effective_checkbox_state={effective_checkbox_state} | "
                            f"idle_for={float(idle_for or 0.0):.1f}s | panel_support=pending | "
                            f"stale_proof={stale_non_target_proof}"
                        )
                    else:
                        self.log(
                            "Unexpected No-Roll Watchdog | suppressed ambiguous checkbox click because guard verification "
                            "showed no strong rolling evidence and final checkbox recheck stayed unclear | "
                            f"checkbox_state={checkbox_state} effective_state={effective_checkbox_state}"
                        )
                        self._set_recovery_route_snapshot(
                            result="skipped",
                            route_reason="ambiguous_checkbox_no_activity",
                            auto_state=str(effective_checkbox_state),
                            rolling_confirmed=False,
                            failure_type="ambiguous_checkbox_no_activity",
                            support_signals=["ambiguous_checkbox_guard"],
                            context="watchdog",
                        )
                        self._write_ocr_debug_event(
                            "unexpected_no_roll_watchdog",
                            {
                                "phase": "skipped",
                                "reason": "ambiguous_checkbox_no_activity",
                                "checkbox_state": checkbox_state,
                                "effective_checkbox_state": effective_checkbox_state,
                                "state": state,
                                "trait": trait,
                                "signature": signature,
                            },
                        )
                        return "skipped"
                elif effective_checkbox_state not in ("disabled", "ambiguous", "weak_enabled"):
                    self.log(
                        "Unexpected No-Roll Watchdog | skipped unsupported checkbox state after ambiguous recheck="
                        f"{checkbox_state} effective={effective_checkbox_state}"
                    )
                    return "skipped"

            panel_support = self._watchdog_roll_panel_support(baseline, trait=trait, effective_checkbox_state=effective_checkbox_state)
            off_target_reason = self._stats_region_control_text_reason(baseline)
            if off_target_reason:
                self._log_with_cooldown(
                    "stats_region_off_target_ui_text",
                    "Current roll OCR region appears misconfigured; reading UI/control text instead of roll stats",
                    cooldown=30.0,
                )
                self._set_recovery_route_snapshot(
                    result="skipped",
                    route_reason=off_target_reason,
                    auto_state=str(effective_checkbox_state or checkbox_state),
                    rolling_confirmed=False,
                    failure_type=off_target_reason,
                    support_signals=["off_target_ui_text"],
                    context="watchdog",
                )
                self._write_ocr_debug_event(
                    "unexpected_no_roll_watchdog",
                    {
                        "phase": "skipped",
                        "reason": off_target_reason,
                        "checkbox_state": checkbox_state,
                        "effective_checkbox_state": effective_checkbox_state,
                        "state": state,
                        "trait": trait,
                        "signature": signature,
                        "baseline": self._compact_debug_text(baseline, 500),
                    },
                )
                return "off_panel"
            if not panel_support:
                route_reason = "roll_panel_not_visible_or_unreadable"
                self.log(
                    "recovery skipped because reroll panel is not visible or OCR regions are off target | "
                    f"route_reason={route_reason} | baseline={self._compact_debug_text(baseline)} | "
                    f"checkbox_state={checkbox_state} effective_state={effective_checkbox_state}"
                )
                self._set_recovery_route_snapshot(
                    result="skipped",
                    route_reason=route_reason,
                    auto_state=str(effective_checkbox_state or checkbox_state),
                    rolling_confirmed=False,
                    failure_type=route_reason,
                    support_signals=[],
                    context="watchdog",
                )
                self._write_ocr_debug_event(
                    "unexpected_no_roll_watchdog",
                    {
                        "phase": "skipped",
                        "reason": route_reason,
                        "checkbox_state": checkbox_state,
                        "effective_checkbox_state": effective_checkbox_state,
                        "state": state,
                        "trait": trait,
                        "signature": signature,
                        "baseline": self._compact_debug_text(baseline, 500),
                    },
                )
                return "off_panel"
            if stale_non_target_proof:
                self.log(
                    "watchdog_non_target_stale_auto_reclick_allowed | "
                    f"stage={stage} | state={state or 'unknown'} | trait={trait_text} | "
                    f"checkbox_state={checkbox_state} | effective_checkbox_state={effective_checkbox_state} | "
                    f"idle_for={float(idle_for or 0.0):.1f}s | panel_support={'+'.join(panel_support) or 'none'} | "
                    f"stale_proof={stale_non_target_proof}"
                )

            self.last_watchdog_attempt_at = now
            self.last_watchdog_signature = signature
            if effective_checkbox_state == "disabled":
                click_reason = "disabled"
            elif effective_checkbox_state == "weak_enabled":
                click_reason = "weak_enabled_dead_fast_path" if fast_dead_watchdog else "weak_enabled_compact_verify_failed"
            else:
                click_reason = "non_target_stale_guard_static" if stale_non_target_proof else "unknown_but_rolls_stale"
            settle_delay = watchdog_profile["click_settle"]
            auto_reclick_started = time.perf_counter()
            self.click(
                self.cfg["AUTO_CHECKBOX"],
                "Unexpected No-Roll Watchdog Auto Re-enable",
                offset=(-self.cfg["AUTO_LEFT_NUDGE"], 0),
                settle=settle_delay,
            )
            auto_reclick_ms = int((time.perf_counter() - auto_reclick_started) * 1000)
            self.log(
                "Unexpected No-Roll Watchdog | auto re-enable attempt sent | "
                f"checkbox_state={checkbox_state} effective_state={effective_checkbox_state} reason={click_reason} stage={stage} | "
                f"watchdog_auto_reclick_ms={auto_reclick_ms}"
            )
            self.last_important_event = "Unexpected no-roll watchdog attempted Auto re-enable"
            verify_delay = min(
                float(self.cfg["AUTO_VERIFY_DELAY"]),
                watchdog_profile["verify_delay_cap"],
            )
            if not self._interruptible_sleep(verify_delay, "unexpected no-roll watchdog verify delay"):
                return "failed"

            verify_kwargs = {"ui_signals": ["watchdog_auto_reenable"]}
            verify_kwargs.update(self._stats_verify_profile("watchdog_verify", watchdog_profile=watchdog_profile))
            verify_started = time.perf_counter()
            changed, new_text = self.stats_changed(
                baseline,
                "Unexpected No-Roll Watchdog verify",
                **verify_kwargs,
            )
            watchdog_verify_ms = int((time.perf_counter() - verify_started) * 1000)
            if changed:
                self.last_text = new_text or baseline
                self.last_change = time.time()
                self.last_watchdog_attempt_at = 0.0
                self.last_watchdog_signature = ""
                self.last_important_event = "Unexpected no-roll watchdog restored rolling"
                self.log(
                    "Unexpected No-Roll Watchdog | verified rolling resumed | "
                    f"checkbox_state={checkbox_state} effective_state={effective_checkbox_state}; stale signature cleared | "
                    f"watchdog_verify_ms={watchdog_verify_ms}"
                )
                self.clear_recovery_failures("unexpected no-roll watchdog restored rolling")
                self.record_decision_chain(
                    subsystem="Recovery",
                    recovery_state="confirmed",
                    recovery_context="Unexpected No-Roll Watchdog",
                    recovery_reason="watchdog_auto_reenable_verified",
                    checkbox_state=checkbox_state,
                )
                self._set_recovery_route_snapshot(
                    result="confirmed",
                    route_reason="watchdog_auto_reenable_verified",
                    auto_state=str(effective_checkbox_state or checkbox_state),
                    rolling_confirmed=True,
                    support_signals=(
                        ["non_target_stale_proof", "bounded_auto_reenable"]
                        if stale_non_target_proof
                        else ["watchdog_auto_reenable"]
                    ),
                    context="watchdog",
                )
                self._write_ocr_debug_event(
                    "unexpected_no_roll_watchdog",
                    {
                        "phase": "verified",
                        "result": "recovered",
                        "checkbox_state": checkbox_state,
                        "state": state,
                        "trait": trait,
                        "sample": self._compact_debug_text(new_text or baseline, 500),
                    },
                )
                return "recovered"

            if self.last_recovery_verify_state == "session_blocked":
                blocked_reason = self.last_recovery_reason or "session_blocked"
                self.log(
                    "Unexpected No-Roll Watchdog | skipped recovery verify due to session-blocked screen | "
                    f"reason={blocked_reason}"
                )
                self._set_recovery_route_snapshot(
                    result="skipped",
                    route_reason=blocked_reason,
                    auto_state=str(effective_checkbox_state or checkbox_state),
                    rolling_confirmed=False,
                    failure_type=blocked_reason,
                    support_signals=self._session_blocked_support_signals(blocked_reason),
                    context="watchdog",
                )
                return "skipped"

            self.log(
                "Unexpected No-Roll Watchdog | failed to restore rolling | "
                f"checkbox_state={checkbox_state} effective_state={effective_checkbox_state}"
            )
            self.last_important_event = "Unexpected no-roll watchdog failed"
            self.record_decision_chain(
                subsystem="Recovery",
                recovery_state="failed",
                recovery_context="Unexpected No-Roll Watchdog",
                recovery_reason="watchdog_auto_reenable_failed",
                checkbox_state=checkbox_state,
            )
            self._set_recovery_route_snapshot(
                result="failed",
                route_reason="watchdog_auto_reenable_failed",
                auto_state=str(effective_checkbox_state or checkbox_state),
                rolling_confirmed=False,
                failure_type="watchdog_auto_reenable_failed",
                support_signals=["watchdog_auto_reenable"],
                context="watchdog",
            )
            self._write_ocr_debug_event(
                "unexpected_no_roll_watchdog",
                {
                    "phase": "verified",
                    "result": "failed",
                    "checkbox_state": checkbox_state,
                    "state": state,
                    "trait": trait,
                },
            )
            return "failed"
        finally:
            self.watchdog_in_progress = False

    def _should_trigger_watchdog_suspicion(self, current_text, state, trait, idle_for):
        threshold = self._watchdog_suspicion_timeout()
        if float(idle_for or 0.0) < threshold:
            return False
        if self.stop_event.is_set() or state != "NON_TARGET":
            return False
        blocked_reason = self._session_blocked_ocr_reason(current_text or self.last_text or "")
        if blocked_reason:
            self.log(
                "[Watchdog] stale suspicion skipped | "
                f"reason={blocked_reason} | idle={float(idle_for or 0.0):.1f}s threshold={threshold:.1f}s"
            )
            self._set_recovery_route_snapshot(
                result="skipped",
                route_reason=blocked_reason,
                auto_state="not_checked",
                rolling_confirmed=False,
                failure_type=blocked_reason,
                support_signals=self._session_blocked_support_signals(blocked_reason),
                context="watchdog_suspicion",
            )
            return False
        started = time.perf_counter()
        if self.popup_active(log=True, context="Unexpected No-Roll Watchdog suspicion"):
            self.log(
                "[Watchdog] stale suspicion skipped | reason=popup_active | "
                f"idle={float(idle_for or 0.0):.1f}s threshold={threshold:.1f}s"
            )
            return False
        if self.banner_active():
            self.log(
                "[Watchdog] stale suspicion skipped | reason=banner_active | "
                f"idle={float(idle_for or 0.0):.1f}s threshold={threshold:.1f}s"
            )
            return False
        changed, _ = self.stats_changed(
            current_text,
            "Unexpected No-Roll Watchdog suspicion",
            ui_signals=["watchdog_stale_suspicion"],
            **self._stats_verify_profile("watchdog_suspicion"),
        )
        details = self.last_recovery_verify_details or {}
        if self.last_recovery_verify_state == "session_blocked":
            blocked_reason = self.last_recovery_reason or "session_blocked"
            self.log(
                "[Watchdog] stale suspicion skipped | "
                f"reason={blocked_reason} | elapsed={int((time.perf_counter() - started) * 1000)}ms"
            )
            self._set_recovery_route_snapshot(
                result="skipped",
                route_reason=blocked_reason,
                auto_state="not_checked",
                rolling_confirmed=False,
                failure_type=blocked_reason,
                support_signals=self._session_blocked_support_signals(blocked_reason),
                context="watchdog_suspicion",
            )
            return False
        usefulness = "strong" if changed else ("weak" if details.get("weak_samples", 0) else "marginal")
        exit_reason = details.get("exit_reason") or self.last_recovery_reason or ("activity_detected" if changed else "flat_static")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        secondary_changed = False
        if not changed and usefulness == "marginal":
            second_started = time.perf_counter()
            secondary_changed, _ = self.stats_changed(
                current_text,
                "Unexpected No-Roll Watchdog suspicion confirm",
                ui_signals=["watchdog_stale_suspicion_confirm"],
                **self._stats_verify_profile("watchdog_suspicion"),
            )
            self.log(
                "[Watchdog] stale suspicion confirm | "
                f"elapsed={int((time.perf_counter() - second_started) * 1000)}ms | changed={secondary_changed}"
            )
            if self.last_recovery_verify_state == "session_blocked":
                blocked_reason = self.last_recovery_reason or "session_blocked"
                self.log(
                    "[Watchdog] stale suspicion skipped after confirm | "
                    f"reason={blocked_reason}"
                )
                self._set_recovery_route_snapshot(
                    result="skipped",
                    route_reason=blocked_reason,
                    auto_state="not_checked",
                    rolling_confirmed=False,
                    failure_type=blocked_reason,
                    support_signals=self._session_blocked_support_signals(blocked_reason),
                    context="watchdog_suspicion",
                )
                return False
        final_changed = changed or secondary_changed
        self.log(
            "[Watchdog] stale suspicion | "
            f"elapsed={elapsed_ms}ms | threshold={threshold:.1f}s | stage=suspicion | usefulness={usefulness} | "
            f"exit_reason={exit_reason} | changed={final_changed} | startup_logic_version={STARTUP_LOGIC_VERSION}"
        )
        return not final_changed and usefulness in {"weak", "marginal"}

    def _watchdog_dead_weak_enabled_fast_path(
        self,
        suspicion_details,
        suspicion_reason,
        stage="recovery",
        popup_known_clear=False,
        banner_known_clear=False,
    ):
        if str(stage or "recovery").lower() != "suspicion":
            return False
        if not popup_known_clear or not banner_known_clear:
            return False
        details = suspicion_details or {}
        reason = str(suspicion_reason or details.get("exit_reason") or "")
        if reason not in {"weak_non_improving_dead_phase", "weak_non_improving_bridge_probe"}:
            return False
        if int(details.get("image_changed_samples", 0) or 0) > 0:
            return False
        if float(details.get("max_change_score", 0.0) or 0.0) > 0.0:
            return False
        if int(details.get("weak_samples", 0) or 0) < 1:
            return False
        return True

    def _watchdog_verify_profile(self, stage):
        suspicion = str(stage or "recovery").lower() == "suspicion"
        if suspicion:
            return {
                "guard_polls": 2,
                "guard_poll_delay": 0.03,
                "guard_recheck_delay": 0.03,
                "click_settle": 0.08,
                "verify_delay_cap": 0.04,
                "weak_enabled_verify_polls": 2,
                "weak_enabled_verify_poll_delay": 0.02,
                "weak_enabled_recheck_delay": 0.02,
                "weak_enabled_psm_sequence": (6,),
                "weak_enabled_abandon_on_weak_samples": 1,
                "verify_kwargs": {
                    "polls_override": 2,
                    "poll_delay_override": 0.02,
                    "unreadable_fast_fail_polls": 2,
                    "psm_sequence_override": (6, 7),
                    "candidate_signal_enabled": False,
                    "abandon_on_weak_samples": 1,
                    "post_popup_check_enabled": False,
                },
            }
        return {
            "guard_polls": 3,
            "guard_poll_delay": 0.04,
            "guard_recheck_delay": 0.04,
            "click_settle": 0.14,
            "verify_delay_cap": 0.08,
            "weak_enabled_verify_polls": 2,
            "weak_enabled_verify_poll_delay": 0.03,
            "weak_enabled_recheck_delay": 0.02,
            "weak_enabled_psm_sequence": (6,),
            "weak_enabled_abandon_on_weak_samples": 1,
            "verify_kwargs": {
                "polls_override": 3,
                "poll_delay_override": 0.04,
                "unreadable_fast_fail_polls": 2,
                "psm_sequence_override": (6, 7, 6),
            },
        }

    def _auto_reenable_timing_profile(self, context):
        manual_resume = "manual reroll" in str(context or "").lower()
        if manual_resume:
            return {
                "guard_polls": 1,
                "guard_poll_delay": 0.03,
                "guard_recheck_delay": 0.02,
                "click_settle": 0.10,
                "verify_delay_cap": 0.06,
                "verify_polls": 2,
                "verify_poll_delay": 0.03,
                "guard_psm_sequence": (6,),
            }
        return {
            "guard_polls": 2,
            "guard_poll_delay": 0.05,
            "guard_recheck_delay": 0.05,
            "click_settle": 0.14,
            "verify_delay_cap": 0.12,
            "verify_polls": 2,
            "verify_poll_delay": 0.06,
        }

    def _manual_reroll_timing_profile(self, startup_bad_current_spec=False):
        if startup_bad_current_spec:
            return {
                "roll_click_settle": 0.24,
                "post_click_settle": 0.06,
                "popup_timeout": 0.55,
                "popup_poll_delay": 0.04,
                "fallback_yes_delay": 0.04,
                "cleared_settle": 0.03,
                "resume_verify_delay_cap": 0.06,
                "resume_verify_poll_delay": 0.05,
            }
        return {
            "roll_click_settle": 0.24,
            "post_click_settle": 0.06,
            "popup_timeout": 0.70,
            "popup_poll_delay": 0.04,
            "fallback_yes_delay": 0.04,
            "cleared_settle": 0.03,
            "resume_verify_delay_cap": 0.04,
            "resume_verify_poll_delay": 0.03,
            "compact_verify_polls": 2,
            "compact_verify_poll_delay": 0.02,
            "compact_verify_abandon_on_weak_samples": 1,
        }

    def _stats_verify_profile(self, profile_name, **kwargs):
        if profile_name == "startup_safe_filler_preflight":
            popup_known_false = bool(kwargs.get("popup_known_false", False))
            return {
                "polls_override": 1,
                "poll_delay_override": 0.0,
                "unreadable_fast_fail_polls": 1,
                "psm_sequence_override": (6,),
                "candidate_signal_enabled": False,
                "abandon_on_weak_samples": 1,
                "post_popup_check_enabled": False,
                "initial_popup_known_false": popup_known_false,
                "fast_popup_checks": True,
                "fast_post_popup_check": True,
                "single_useful_sample_ok": True,
            }
        if profile_name == "startup_guarded_retry_preflight":
            return {
                "polls_override": 1,
                "poll_delay_override": 0.01,
                "unreadable_fast_fail_polls": 1,
                "psm_sequence_override": (6,),
                "candidate_signal_enabled": False,
                "abandon_on_weak_samples": 1,
                "post_popup_check_enabled": False,
                "fast_popup_checks": True,
                "fast_post_popup_check": True,
                "single_useful_sample_ok": True,
            }
        if profile_name == "manual_reroll_compact_resume":
            transition_profile = kwargs["transition_profile"]
            popup_known_false = bool(kwargs.get("popup_known_false", False))
            return {
                "ui_signals": ["manual_reroll_auto_resume", "manual_reroll_compact_verify"],
                "polls_override": 1 if popup_known_false else transition_profile.get("compact_verify_polls", 2),
                "poll_delay_override": transition_profile.get("compact_verify_poll_delay", 0.03),
                "unreadable_fast_fail_polls": 1 if popup_known_false else 2,
                "psm_sequence_override": (6,) if popup_known_false else None,
                "candidate_signal_enabled": False,
                "abandon_on_weak_samples": transition_profile.get("compact_verify_abandon_on_weak_samples", 1),
                "initial_popup_known_false": popup_known_false,
                "post_popup_check_enabled": not popup_known_false,
                "mid_popup_check_enabled": not popup_known_false,
                "fast_popup_checks": True,
                "fast_post_popup_check": True,
                "single_useful_sample_ok": True,
            }
        if profile_name == "manual_reroll_resume_verify":
            transition_profile = kwargs["transition_profile"]
            popup_known_false = bool(kwargs.get("popup_known_false", False))
            return {
                "ui_signals": ["manual_reroll_auto_resume"],
                "polls_override": 1 if popup_known_false else 2,
                "poll_delay_override": transition_profile["resume_verify_poll_delay"],
                "unreadable_fast_fail_polls": 1 if popup_known_false else 2,
                "psm_sequence_override": (6,) if popup_known_false else None,
                "candidate_signal_enabled": False,
                "initial_popup_known_false": popup_known_false,
                "post_popup_check_enabled": not popup_known_false,
                "mid_popup_check_enabled": not popup_known_false,
                "fast_popup_checks": True,
                "fast_post_popup_check": True,
                "single_useful_sample_ok": True,
            }
        if profile_name == "auto_reenable_guard":
            timing = kwargs["timing"]
            popup_known_false = bool(kwargs.get("popup_known_false", False))
            return {
                "polls_override": timing["guard_polls"],
                "poll_delay_override": timing["guard_poll_delay"],
                "unreadable_fast_fail_polls": 2,
                "psm_sequence_override": timing.get("guard_psm_sequence"),
                "initial_popup_known_false": popup_known_false,
                "post_popup_check_enabled": not popup_known_false,
                "fast_popup_checks": True,
                "fast_post_popup_check": True,
                "single_useful_sample_ok": True,
            }
        if profile_name == "auto_reenable_verify":
            timing = kwargs["timing"]
            popup_known_false = bool(kwargs.get("popup_known_false", False))
            return {
                "polls_override": timing["verify_polls"],
                "poll_delay_override": timing["verify_poll_delay"],
                "unreadable_fast_fail_polls": 2,
                "initial_popup_known_false": popup_known_false,
                "post_popup_check_enabled": not popup_known_false,
                "fast_popup_checks": True,
                "fast_post_popup_check": True,
                "single_useful_sample_ok": True,
            }
        if profile_name == "watchdog_verify":
            watchdog_profile = kwargs["watchdog_profile"]
            return {
                **dict(watchdog_profile["verify_kwargs"]),
                "fast_popup_checks": True,
                "fast_post_popup_check": True,
                "single_useful_sample_ok": True,
            }
        if profile_name == "watchdog_suspicion":
            return {
                "polls_override": 1,
                "poll_delay_override": 0.02,
                "unreadable_fast_fail_polls": 1,
                "psm_sequence_override": (6,),
                "candidate_signal_enabled": False,
                "abandon_on_weak_samples": 1,
                "post_popup_check_enabled": False,
                "fast_popup_checks": True,
                "fast_post_popup_check": True,
                "single_useful_sample_ok": True,
            }
        raise KeyError(f"unknown stats verify profile: {profile_name}")

    def _manual_reroll_recently_confirmed(self, max_age: float = 1.5) -> bool:
        return (
            self.last_manual_reroll_confirmed_at > 0.0
            and (time.perf_counter() - self.last_manual_reroll_confirmed_at) <= max_age
        )

    def _auto_reenable_guard_support(self, verify_details=None, verify_reason=None):
        outcome = self._recovery_outcome_from_inputs(None, verify_details, verify_reason)
        verify_reason = self._recovery_outcome_reason(outcome)
        image_changed_samples = int(outcome.image_changed_samples or 0)
        max_change_score = float(outcome.max_change_score or 0.0)
        support_signals = []
        if verify_reason.startswith("popup_"):
            support_signals.append("popup")
        if verify_reason.startswith("banner_"):
            support_signals.append("banner")
        if image_changed_samples > 0:
            support_signals.append("image_change")
        return {
            "strong": bool(support_signals),
            "reason": verify_reason or "none",
            "signals": support_signals,
            "image_changed_samples": image_changed_samples,
            "max_change_score": round(max_change_score, 2),
        }

    def _manual_reroll_roll_like_refresh_sample(self, samples, require_image_changed=False):
        for sample in samples or []:
            cleaned = str(sample.get("cleaned") or "").strip()
            if not cleaned or sample.get("unreliable") or sample.get("trait_only"):
                continue
            if require_image_changed and not sample.get("image_changed"):
                continue
            if not sample.get("materially_different") and not sample.get("reason"):
                continue
            if self._session_blocked_ocr_reason(cleaned):
                continue
            numbers = extract_numbers(cleaned)
            stat_signal = self._has_activity_stat_signal(cleaned)
            trait = self.detect_rollable_trait(cleaned) or self._generic_rollable_non_target_from_text(cleaned)
            if numbers and (stat_signal or trait):
                return cleaned
        return ""

    def _manual_reroll_resume_support(self, verify_details=None, verify_reason=None, popup_recently_cleared=False):
        outcome = self._recovery_outcome_from_inputs(None, verify_details, verify_reason)
        resolved_reason = self._recovery_outcome_reason(outcome)
        confirmed_like = bool(
            outcome.confirmed
            or (
                resolved_reason
                and not outcome.rejection_reason
                and outcome.classification not in {
                    "session_blocked",
                    "unreadable_static",
                    "unreadable_but_changed",
                }
            )
        )
        if confirmed_like:
            support = self._auto_reenable_guard_support(verify_details, verify_reason)
            if support.get("strong"):
                return support
        else:
            support = {
                "strong": False,
                "reason": resolved_reason or "none",
                "signals": [],
                "image_changed_samples": int(outcome.image_changed_samples or 0),
                "max_change_score": round(float(outcome.max_change_score or 0.0), 2),
            }
            if (
                popup_recently_cleared
                and not outcome.unreadable
                and outcome.classification == "not_rolling"
                and resolved_reason == "readable_insufficient_change"
            ):
                sample_text = self._manual_reroll_roll_like_refresh_sample(
                    (verify_details or {}).get("samples_detail") or []
                )
                if sample_text:
                    signals = ["recent_popup_clear", "roll_like_ocr"]
                    if int(outcome.image_changed_samples or 0) > 0:
                        signals.insert(1, "image_change")
                    elif any(sample.get("signature_changed") for sample in (verify_details or {}).get("samples_detail") or []):
                        signals.insert(1, "screen_signature_change")
                    return {
                        **support,
                        "strong": True,
                        "reason": (
                            "recent_popup_clear_roll_like_ocr_after_image_change"
                            if int(outcome.image_changed_samples or 0) > 0
                            else "recent_popup_clear_roll_like_ocr_after_signature_change"
                            if "screen_signature_change" in signals
                            else "recent_popup_clear_roll_like_ocr"
                        ),
                        "signals": signals,
                        "sample_text": sample_text,
                    }
            return support
        verify_reason = str(verify_reason or support.get("reason") or "").strip()
        refresh_reason = any(
            token in verify_reason
            for token in (
                "current_spec_marker",
                "multi_source_current_spec_marker",
                "trait_changed:",
                "multi_source_trait_changed:",
                "stat_numbers_changed",
                "trait_values_changed",
            )
        )
        if popup_recently_cleared and refresh_reason and not self.last_recovery_verify_unreadable:
            signals = list(support.get("signals") or [])
            signals.extend(sig for sig in ("recent_popup_clear", "current_spec_refresh") if sig not in signals)
            return {
                **support,
                "strong": True,
                "signals": signals,
            }
        return support

    def _manual_reroll_visual_resume_support(self, baseline_img, popup_recently_cleared=False):
        if not popup_recently_cleared or baseline_img is None:
            return {"strong": False, "reason": "visual_resume_unavailable", "signals": []}
        current_img = self._safe_region_screenshot(self.cfg["STATS_REGION"])
        if current_img is None:
            return {"strong": False, "reason": "visual_resume_missing_sample", "signals": []}
        change_score = self._region_change_score(baseline_img, current_img)
        signature_changed = self._region_signature(baseline_img) != self._region_signature(current_img)
        threshold = self._manual_visual_change_threshold()
        strong = bool(signature_changed and change_score >= threshold)
        signals = ["recent_popup_clear"]
        if strong:
            signals.append("stats_region_visual_change")
        return {
            "strong": strong,
            "reason": "popup_cleared_stats_region_visual_refresh" if strong else "stats_region_visual_refresh_too_weak",
            "signals": signals,
            "image_changed_samples": 1 if strong else 0,
            "max_change_score": round(change_score, 2),
            "threshold": round(threshold, 2),
        }

    def _compact_manual_reroll_resume_verify(self, baseline, transition_profile, popup_recently_cleared=False):
        context = "Manual Reroll Auto Resume Compact Verify"
        changed, new_text = self.stats_changed(
            baseline,
            context,
            **self._stats_verify_profile(
                "manual_reroll_compact_resume",
                transition_profile=transition_profile,
                popup_known_false=popup_recently_cleared,
            ),
        )
        if not changed:
            self.log("Manual reroll compact resume verify did not confirm rolling activity")
            return False
        support = self._manual_reroll_resume_support(
            self.last_recovery_verify_details,
            self.last_recovery_reason,
            popup_recently_cleared=popup_recently_cleared,
        )
        if not support.get("strong"):
            self.log(
                "Manual reroll compact resume verify rejected as too weak | "
                f"reason={support.get('reason', 'none')} | "
                f"support={'+'.join(support.get('signals', [])) or 'none'} | "
                f"image_changed_samples={support.get('image_changed_samples', 0)} | "
                f"change_score={support.get('max_change_score', 0.0)}"
            )
            return False
        self.last_text = new_text or baseline
        self.last_change = time.time()
        self.clear_recovery_failures("Manual reroll compact resume verify confirmed rolling")
        self.log(
            "Manual reroll compact resume verify confirmed rolling activity | "
            f"reason={support.get('reason', 'none')} | "
            f"support={'+'.join(support.get('signals', [])) or 'none'}"
        )
        return True

    def _compact_watchdog_resume_verify(self, baseline, watchdog_profile, stage="recovery"):
        context = "Unexpected No-Roll Watchdog weak-enabled compact verify"
        changed, new_text = self.stats_changed(
            baseline,
            context,
            ui_signals=["watchdog_weak_enabled_compact"],
            polls_override=watchdog_profile.get("weak_enabled_verify_polls", 2),
            poll_delay_override=watchdog_profile.get("weak_enabled_verify_poll_delay", 0.03),
            unreadable_fast_fail_polls=1,
            psm_sequence_override=watchdog_profile.get("weak_enabled_psm_sequence", (6,)),
            candidate_signal_enabled=False,
            abandon_on_weak_samples=watchdog_profile.get("weak_enabled_abandon_on_weak_samples", 1),
            initial_popup_known_false=True,
            post_popup_check_enabled=False,
        )
        if not changed:
            self.log(
                "Unexpected No-Roll Watchdog | weak-enabled compact verify did not confirm rolling activity | "
                f"stage={stage}"
            )
            return False
        support = self._auto_reenable_guard_support(
            self.last_recovery_verify_details,
            self.last_recovery_reason,
        )
        if not support.get("strong"):
            self.log(
                "Unexpected No-Roll Watchdog | weak-enabled compact verify rejected as too weak | "
                f"reason={support.get('reason', 'none')} | "
                f"support={'+'.join(support.get('signals', [])) or 'none'} | "
                f"image_changed_samples={support.get('image_changed_samples', 0)} | "
                f"change_score={support.get('max_change_score', 0.0)} | "
                f"stage={stage}"
            )
            return False
        self.last_text = new_text or baseline
        self.last_change = time.time()
        self.clear_recovery_failures("Unexpected No-Roll Watchdog weak-enabled compact verify confirmed rolling")
        self.log(
            "Unexpected No-Roll Watchdog | weak-enabled compact verify confirmed rolling activity | "
            f"reason={support.get('reason', 'none')} | "
            f"support={'+'.join(support.get('signals', [])) or 'none'} | "
            f"stage={stage}"
        )
        return True

    def _attempt_auto_reenable_once(
        self,
        context,
        baseline,
        trait=None,
        state=None,
        verify_signal="auto_reenable",
        force_click_on_ambiguous=False,
        popup_recently_cleared=False,
        direct_click_on_forced_unknown=False,
    ):
        """One controlled auto re-enable/verify attempt for paths that should not wait for stale watchdog timeout."""
        checkbox_state = self.auto_checkbox_state()
        self._log_auto_checkbox_state_read(context, 1, checkbox_state)
        trait_text = display_trait(trait) if trait else "unknown"
        self.log(
            f"{context} | immediate auto re-enable check | state={checkbox_state} "
            + f"trait={trait_text} roll_state={state or 'unknown'}"
        )
        clicked = False
        timing = self._auto_reenable_timing_profile(context)
        ambiguous_checkbox = checkbox_state in ("unknown", "weak_enabled")

        def send_auto_reenable(click_reason):
            nonlocal clicked
            self.click(
                self.cfg["AUTO_CHECKBOX"],
                f"{context} Auto Re-enable",
                offset=(-self.cfg["AUTO_LEFT_NUDGE"], 0),
                settle=timing["click_settle"],
            )
            clicked = True
            if click_reason == "ambiguous_manual_resume_direct":
                self.manual_reroll_direct_recovery_clicks += 1
            self.log(
                f"{context} | auto re-enable attempt sent | checkbox_state={checkbox_state} reason={click_reason}"
            )
            verify_delay = min(
                max(0.0, float(self.cfg.get("AUTO_VERIFY_DELAY", DEFAULT_CONFIG["AUTO_VERIFY_DELAY"]))),
                timing["verify_delay_cap"],
            )
            return self._interruptible_sleep(verify_delay, f"{context} verify delay")

        if ambiguous_checkbox:
            direct_forced_unknown = (
                direct_click_on_forced_unknown
                and force_click_on_ambiguous
                and checkbox_state == "unknown"
            )
            if direct_forced_unknown:
                self.log(
                    f"{context} | optimized manual reroll unknown checkbox path; "
                    "skipping ambiguous guard and clicking once before bounded verify"
                )
                if not send_auto_reenable("ambiguous_manual_resume_direct"):
                    return False
            else:
                changed, new_text = self.stats_changed(
                    baseline,
                    f"{context} ambiguous checkbox guard",
                    ui_signals=[verify_signal, "ambiguous_checkbox_guard"],
                    **self._stats_verify_profile(
                        "auto_reenable_guard",
                        timing=timing,
                        popup_known_false=popup_recently_cleared,
                    ),
                )
                if changed:
                    guard_support = self._auto_reenable_guard_support(
                        self.last_recovery_verify_details,
                        self.last_recovery_reason,
                    )
                    if guard_support["strong"]:
                        self.last_text = new_text or baseline
                        self.last_change = time.time()
                        self.clear_recovery_failures(f"{context} guard observed rolling")
                        self.log(
                            f"{context} | skipped auto re-enable on ambiguous checkbox state because rolling evidence returned"
                        )
                        return True
                    self.log(
                        f"{context} | weak rolling evidence rejected for ambiguous checkbox guard | "
                        f"reason={guard_support.get('reason', 'none')} | "
                        f"support={'+'.join(guard_support.get('signals', [])) or 'none'} | "
                        f"image_changed_samples={guard_support.get('image_changed_samples', 0)} | "
                        f"change_score={guard_support.get('max_change_score', 0.0)}"
                    )
                if force_click_on_ambiguous:
                    if not self._interruptible_sleep(
                        timing["guard_recheck_delay"],
                        f"{context} ambiguous checkbox validation",
                    ):
                        return False
                    checkbox_state = self.auto_checkbox_state()
                    self._log_auto_checkbox_state_read(f"{context} final ambiguous recheck", 2, checkbox_state)
                    if checkbox_state in ("enabled", "weak_enabled"):
                        self.log(f"{context} | Auto appears enabled after ambiguous recheck; verifying without forced click")
                    elif not send_auto_reenable("ambiguous_manual_resume"):
                        return False
                else:
                    self.log(
                        f"{context} | skipped auto re-enable on ambiguous checkbox state; waiting for clearer visual disable"
                    )
        elif checkbox_state == "disabled":
            if not send_auto_reenable("disabled"):
                return False
        else:
            self.log(f"{context} | Auto appears enabled; verifying rolling without extra click")

        changed, new_text = self.stats_changed(
            baseline,
            f"{context} verify",
            ui_signals=[verify_signal],
            **self._stats_verify_profile(
                "auto_reenable_verify",
                timing=timing,
                popup_known_false=popup_recently_cleared,
            ),
        )
        if changed:
            self.last_text = new_text or baseline
            self.last_change = time.time()
            self.clear_recovery_failures(f"{context} restored rolling")
            self.log(f"{context} | rolling activity confirmed | checkbox_state={checkbox_state} clicked={clicked}")
            return True
        self.log(f"{context} | rolling activity NOT confirmed | checkbox_state={checkbox_state} clicked={clicked}")
        return False

    def _startup_fast_power_probe_support(self, state, trait, summary, ocr_text):
        if self.roll_domain != "powers":
            return {"strong": False, "reason": "non_power_domain", "quality": 0, "parsed_values": 0}
        if state not in {"BAD", "DISABLED", "HIGH_VALUE", "GOD"}:
            return {"strong": False, "reason": f"state={state or 'unknown'}", "quality": 0, "parsed_values": 0}
        combined = "\n".join(
            part.strip() for part in (summary or "", ocr_text or "") if str(part or "").strip()
        )
        parsed = parse_power_roll_text(combined)
        if not parsed:
            return {"strong": False, "reason": "parse_failed", "quality": 0, "parsed_values": 0}
        power_key = parsed.get("power")
        if not power_key or power_key != trait:
            return {
                "strong": False,
                "reason": f"parsed_trait_mismatch:{power_key or 'none'}",
                "quality": 0,
                "parsed_values": 0,
            }
        values = parsed.get("values") or {}
        passive = parsed.get("passive")
        quality = self._power_candidate_quality(power_key, values, combined, passive)
        parsed_values = sum(value is not None for value in values.values())
        strong = quality >= 100 and parsed_values >= 3
        return {
            "strong": bool(strong),
            "reason": "supported_power_fast_probe_strong" if strong else "insufficient_fast_probe_quality",
            "quality": quality,
            "parsed_values": parsed_values,
            "passive_detected": bool(passive and passive.get("detected")),
        }

    def _startup_fast_spec_bad_support(self, state, trait, summary, ocr_text, missing, chain=None):
        if self.roll_domain != "specs" or state not in ("BAD", "DISABLED"):
            return {"strong": False, "values": {}, "value_count": 0}
        trait = canonical_spec_trait(trait)
        if not trait or not self.is_target_trait(trait):
            return {"strong": False, "values": {}, "value_count": 0}
        text = f"{summary or ''}\n{ocr_text or ''}"
        if not self.has_current_spec_marker(text):
            return {"strong": False, "values": {}, "value_count": 0}
        chain = dict(chain or {})
        parsed_values = dict(chain.get("parsed_values") or {})
        values = self.extract_labeled_values(trait, text)
        labels = STAT_LABELS.get(trait, [])
        fallback_values = {
            label: values[index] if index < len(values) else None
            for index, label in enumerate(labels)
        }
        merged_values = {
            label: parsed_values.get(label) if parsed_values.get(label) is not None else fallback_values.get(label)
            for label in labels
        }
        value_count = sum(value is not None for value in merged_values.values())
        needed = len(labels)
        enough_values = bool(needed) and value_count >= needed
        strong = state == "DISABLED" or (bool(missing) and enough_values)
        return {"strong": bool(strong), "values": merged_values, "value_count": value_count}

    def _startup_followup_proves_different_spec(self, initial_trait, followup_state, followup_trait, followup_text):
        if followup_state in ("GOD", "HIGH_VALUE"):
            return True
        initial_trait = canonical_spec_trait(initial_trait)
        followup_trait = canonical_spec_trait(followup_trait) or self.detect_rollable_trait(followup_text or "")
        if not followup_trait or followup_trait == "non_target":
            return False
        return followup_trait != initial_trait

    def _startup_power_bad_from_verify_samples(self, label, verify_details=None):
        if self.roll_domain != "powers":
            return "none"
        details = dict(verify_details or self.last_recovery_verify_details or {})
        samples = details.get("samples_detail") or []
        if not samples:
            return "none"
        for sample in reversed(samples):
            text = str(sample.get("cleaned") or sample.get("sample_text") or "").strip()
            if not text:
                continue
            parsed = parse_power_roll_text(text)
            if not parsed:
                continue
            power_key = parsed.get("power")
            if power_key not in SUPPORTED_POWER_DEFINITIONS:
                continue
            state, trait, summary, ocr_text, missing, _near = self.evaluate_power_trait_with_values(
                power_key,
                parsed.get("values") or {},
                text,
                source_name=f"{label} verify sample",
                passive=parsed.get("passive"),
            )
            if state != "BAD":
                continue
            self.log(
                "Startup verification saw supported BAD Power; routing to manual reroll | "
                f"trait={power_display_name(trait)} | missing={' ; '.join(missing or []) or 'target stats not met'} | "
                f"sample={self._compact_debug_text(text)}"
            )
            if not self._confirm_power_bad_before_manual_reroll(
                trait,
                missing,
                context=f"{label} sampled Power BAD manual reroll",
            ):
                self.log("Startup sampled Power BAD was not stable enough for manual reroll; continuing safe failure path")
                return "deferred"
            if self.manual_reroll_flow(f"{label.lower()} current bad {trait or 'unknown'}"):
                return "rerolled"
            return "failed"
        return "none"

    def _power_required_target_values(self, power_key, values, passive=None):
        required = {}
        definition = SUPPORTED_POWER_DEFINITIONS.get(power_key)
        if not definition:
            return required
        for target in definition.rule_targets:
            if not target.required:
                continue
            if target.source == "passive":
                value = None
                if passive and passive.get("detected"):
                    value = passive.get("value")
            else:
                value = (values or {}).get(target.key)
            try:
                required[target.label] = round(float(value), 4) if value is not None else None
            except Exception:
                required[target.label] = None
        return required

    def _power_parse_completeness(self, power_key, values, passive=None):
        required = self._power_required_target_values(power_key, values, passive)
        missing = [label for label, value in required.items() if value is None]
        return {
            "coherent": bool(required) and not missing,
            "required_values": required,
            "required_present": len(required) - len(missing),
            "required_total": len(required),
            "missing_required": missing,
            "passive_detected": bool(passive and passive.get("detected")),
        }

    def _power_required_values_match(self, first, second):
        return dict(first or {}) == dict(second or {})

    def _power_bad_confirmation_stable(self, confirm_state, confirm_trait, confirm_missing, confirm_chain, initial_required, trait, missing):
        confirm_required = dict((confirm_chain or {}).get("power_required_values") or {})
        stable = (
            confirm_state == "BAD"
            and confirm_trait == trait
            and bool((confirm_chain or {}).get("power_parse_coherent"))
            and self._power_required_values_match(initial_required, confirm_required)
            and list(confirm_missing or []) == list(missing or [])
        )
        return stable, confirm_required

    def _power_bad_fast_confirm_allowed(self, trait=None):
        if self.roll_domain != "powers":
            return False
        chain = dict(self.last_decision_chain or {})
        if chain.get("classification") != "BAD":
            return False
        if trait and power_display_name(trait) != str(chain.get("current_trait") or ""):
            return False
        if not chain.get("power_parse_coherent"):
            return False
        required = chain.get("power_required_values") or {}
        if not required or any(value is None for value in required.values()):
            return False
        try:
            quality = float(chain.get("power_candidate_quality") or 0)
        except Exception:
            quality = 0.0
        return quality >= 110.0

    def _confirm_power_bad_before_manual_reroll(self, trait, missing, context="Power BAD manual reroll", fast_first=False):
        if self.roll_domain != "powers":
            return True
        initial_chain = dict(self.last_decision_chain or {})
        initial_required = initial_chain.get("power_required_values") or {}
        if not trait or not initial_chain.get("power_parse_coherent"):
            self.log(
                f"{context} deferred | reason=incomplete_initial_power_parse | "
                f"trait={power_display_name(trait) if trait else 'unknown'}"
            )
            return False
        if self._stop_requested("power BAD confirmation"):
            return False
        delay = min(0.08, max(0.0, float(self.cfg.get("PARTIAL_TARGET_CONFIRM_DELAY", 0.08))))
        if delay and not self._interruptible_sleep(delay, "power BAD confirmation delay"):
            return False
        if fast_first:
            startup_confirm = "startup" in str(context).lower()
            fast_route = "fast_startup_power_probe" if startup_confirm else "fast_power_probe"
            confirm_state, confirm_trait, _summary, _ocr_text, confirm_missing, _near = self.check_roll(
                allow_fallback=False,
                startup_fast=startup_confirm,
            )
            confirm_chain = dict(self.last_decision_chain or {})
            stable, confirm_required = self._power_bad_confirmation_stable(
                confirm_state,
                confirm_trait,
                confirm_missing,
                confirm_chain,
                initial_required,
                trait,
                missing,
            )
            if stable:
                self.log(
                    f"{context} confirmed | route={fast_route} | trait={power_display_name(trait)} | "
                    f"missing={' ; '.join(missing or []) or 'none'} | "
                    f"quality={confirm_chain.get('power_candidate_quality', 'unknown')} | "
                    f"required={confirm_required} | startup_profile={startup_confirm}"
                )
                return True
            self.log(
                f"{context} rejected | route={fast_route} | "
                f"initial_trait={power_display_name(trait)} | "
                f"confirm_state={confirm_state} confirm_trait={power_display_name(confirm_trait) if confirm_trait else 'unknown'} | "
                f"initial_required={initial_required} confirm_required={confirm_required} | "
                f"initial_missing={' ; '.join(missing or []) or 'none'} | "
                f"confirm_missing={' ; '.join(confirm_missing or []) or 'none'} | startup_profile={startup_confirm}"
            )
            return False
        self.log(f"{context} using full fallback confirmation | reason=fast_confirmation_not_requested")
        confirm_state, confirm_trait, _summary, _ocr_text, confirm_missing, _near = self.check_roll(allow_fallback=True)
        confirm_chain = dict(self.last_decision_chain or {})
        stable, confirm_required = self._power_bad_confirmation_stable(
            confirm_state,
            confirm_trait,
            confirm_missing,
            confirm_chain,
            initial_required,
            trait,
            missing,
        )
        if stable:
            self.log(
                f"{context} confirmed | trait={power_display_name(trait)} | "
                f"missing={' ; '.join(missing or []) or 'none'} | "
                f"quality={confirm_chain.get('power_candidate_quality', 'unknown')} | "
                f"required={confirm_required}"
            )
            return True
        self.log(
            f"{context} rejected | initial_trait={power_display_name(trait)} | "
            f"confirm_state={confirm_state} confirm_trait={power_display_name(confirm_trait) if confirm_trait else 'unknown'} | "
            f"initial_required={initial_required} confirm_required={confirm_required} | "
            f"initial_missing={' ; '.join(missing or []) or 'none'} | "
            f"confirm_missing={' ; '.join(confirm_missing or []) or 'none'}"
        )
        return False

    def clear_reroll_popup(self, reason="popup", attempts=3, already_detected=False):
        started = time.perf_counter()
        if self._stop_requested("popup clear"):
            return False
        if not already_detected and not self._popup_active_checked(log=True, context=reason, fast=True):
            return False

        self.log(f"Reroll popup detected | {reason}")
        self.last_important_event = f"Reroll popup detected ({reason})"
        fast_startup_popup = self._startup_context_active() and str(reason).lower().startswith("manual reroll attempt")
        retry_delay = max(0.04, float(self.cfg.get("POPUP_RETRY_DELAY", 0.04 if fast_startup_popup else 0.08)))
        popup_click_settle = 0.16 if fast_startup_popup else 0.22
        for attempt in range(1, max(1, int(attempts)) + 1):
            if self._stop_requested("popup clear"):
                self.log("Stop requested during popup clear")
                return False
            self.log(f"Reroll popup Yes click attempt {attempt}/{attempts} | {reason}")
            self.click(self.cfg["YES_BUTTON"], "Confirm Popup", settle=popup_click_settle)
            if not self._interruptible_sleep(retry_delay, "popup clear retry delay"):
                return False
            if not self._popup_active_checked(log=True, context=f"{reason} after Yes {attempt}", fast=True):
                elapsed = time.perf_counter() - started
                self.popup_clear_duration_total += elapsed
                self.popup_clear_duration_count += 1
                avg_ms = int((self.popup_clear_duration_total / max(1, self.popup_clear_duration_count)) * 1000)
                self.log(
                    f"Reroll popup cleared | {reason} | attempt={attempt} | "
                    f"elapsed={int(elapsed * 1000)}ms | avg_popup_clear={avg_ms}ms"
                )
                self.last_important_event = f"Reroll popup cleared ({reason})"
                self._mark_startup_popup_confirmed()
                return True
            self.log(f"Reroll popup still present | {reason} | attempt={attempt}")

        self.log(f"Reroll popup still present after retry | {reason}")
        self.alert_popup_stuck(reason)
        return False

    def _manual_reroll_fast_popup_confirm(self, baseline_img, reason, transition_profile):
        if baseline_img is None:
            return None, {"route": "visual_unavailable", "reason": "missing_baseline"}
        before_yes = self._safe_region_screenshot(self.cfg["POPUP_REGION"])
        if before_yes is None:
            return None, {"route": "visual_unavailable", "reason": "missing_popup_sample"}
        threshold = self._manual_visual_change_threshold()
        appeared_score = self._region_change_score(baseline_img, before_yes)
        appeared = bool(self._region_signature(baseline_img) != self._region_signature(before_yes) and appeared_score >= threshold)
        if not appeared:
            return None, {
                "route": "visual_ambiguous",
                "reason": "popup_region_did_not_change",
                "appeared_score": round(appeared_score, 2),
            }

        click_settle = 0.12 if self._startup_context_active() else 0.16
        self.log(
            "Manual reroll fast popup visual confirm | "
            f"{reason} | appeared_score={appeared_score:.2f} | threshold={threshold:.2f}"
        )
        self.click(self.cfg["YES_BUTTON"], "Confirm Popup", settle=click_settle)
        retry_delay = max(0.02, float(self.cfg.get("POPUP_RETRY_DELAY", 0.04)))
        if not self._interruptible_sleep(retry_delay, "manual reroll fast popup clear visual delay"):
            return False, {
                "route": "fast_visual",
                "reason": "manual_stop",
                "appeared_score": round(appeared_score, 2),
            }

        after_yes = self._safe_region_screenshot(self.cfg["POPUP_REGION"])
        if after_yes is None:
            return None, {
                "route": "visual_unavailable",
                "reason": "missing_clear_sample",
                "appeared_score": round(appeared_score, 2),
            }
        cleared_score = self._region_change_score(before_yes, after_yes)
        cleared = bool(self._region_signature(before_yes) != self._region_signature(after_yes) and cleared_score >= threshold)
        if not cleared:
            return None, {
                "route": "visual_ambiguous",
                "reason": "popup_region_did_not_clear",
                "appeared_score": round(appeared_score, 2),
                "cleared_score": round(cleared_score, 2),
            }
        self._mark_startup_popup_confirmed()
        self.last_important_event = f"Reroll popup cleared ({reason})"
        return True, {
            "route": "fast_visual",
            "reason": "popup_region_changed_then_cleared",
            "appeared_score": round(appeared_score, 2),
            "cleared_score": round(cleared_score, 2),
        }

    def confirm_popup_if_present(self, reason="popup"):
        return self.clear_reroll_popup(reason=reason)

    def start_or_recover(self, label="Auto-Roll"):
        started = time.perf_counter()
        startup_recovery = "Initial Auto Start" in label
        local_startup_context = False
        if startup_recovery and not self._startup_context_active():
            self._begin_startup_context("direct initial auto start")
            local_startup_context = True
        previous_recovery_in_progress = self.recovery_in_progress
        self.recovery_in_progress = True

        def finish(value, result=None, rolling_confirmed=False):
            self.recovery_in_progress = previous_recovery_in_progress
            if startup_recovery:
                final_result = result or STARTUP_FAILED_NO_ROLL_DETECTED
                self._set_startup_result(final_result, rolling_confirmed=rolling_confirmed)
                if local_startup_context:
                    self._finish_startup_summary(final_result)
            return value

        def failed_result(auto_result=None):
            if auto_result in AUTO_UNCERTAIN_CLICK_RESULTS:
                return STARTUP_FAILED_UNCERTAIN_AUTO_STATE
            if self.last_recovery_verify_unreadable:
                return STARTUP_FAILED_UNREADABLE_UI
            return STARTUP_FAILED_NO_ROLL_DETECTED

        fast_unreadable_context = startup_recovery or (
            "Stuck Recovery" in label and self.last_recovery_fallback_unclassified
        )
        verify_delay = max(0.0, float(self.cfg["AUTO_VERIFY_DELAY"]))
        verify_polls = max(1, int(self.cfg["AUTO_VERIFY_POLLS"]))
        verify_poll_delay = max(0.0, float(self.cfg["AUTO_VERIFY_POLL_DELAY"]))
        if startup_recovery:
            verify_delay = self._startup_verify_delay_cap(clicked=False)
            verify_poll_delay = self._startup_verify_poll_delay_cap(preflight=False)
        quick_verify_kwargs = {}
        if fast_unreadable_context:
            startup_poll_cap = 2 if startup_recovery else 4
            startup_fast_fail = 2 if startup_recovery else 3
            startup_poll_delay = self._startup_verify_poll_delay_cap(preflight=False) if startup_recovery else 0.12
            quick_verify_kwargs = {
                "polls_override": min(verify_polls, startup_poll_cap),
                "poll_delay_override": min(verify_poll_delay, startup_poll_delay),
                "unreadable_fast_fail_polls": min(startup_fast_fail, max(1, verify_polls)),
                "candidate_signal_enabled": False,
                "abandon_on_weak_samples": 2 if startup_recovery else None,
                "post_popup_check_enabled": False if startup_recovery else True,
                "fast_popup_checks": bool(startup_recovery),
                "fast_post_popup_check": bool(startup_recovery),
            }
        if self._stop_requested(label):
            self.log("Recovery aborted due to manual stop")
            return finish(False, STARTUP_FAILED_TIMEOUT)
        if "Recovery" in label:
            self.session_recovery_count += 1
            self.last_important_event = f"{label} started"
        baseline = self.ocr_region(self.cfg["STATS_REGION"]).strip() or self.last_text

        self.set_status(f"{label}...")
        startup_log_prefix = "[Startup] " if startup_recovery else ""
        startup_verify_prefix = "[Startup Verify] " if startup_recovery else ""
        self.log(f"{startup_log_prefix}{label} | trying auto-roll")
        if startup_recovery:
            self.log(
                f"[Startup Timing] verify_delay={verify_delay:.2f}s | verify_polls={min(verify_polls, 2)} | "
                f"verify_poll_delay={verify_poll_delay:.2f}s | preflight_poll_delay={self._startup_verify_poll_delay_cap(preflight=True):.2f}s | strategy=adaptive_early_exit"
            )

        if self._stop_requested(label):
            self.log("Recovery aborted due to manual stop")
            return finish(False, STARTUP_FAILED_TIMEOUT)

        auto_enable_result = None
        startup_observed_state = None
        startup_popup_state = False
        startup_preflight_rolling_state = "not_rolling"
        startup_guarded_click_used = False
        startup_skip_uncertainty_validation = False
        startup_skip_primary_verify = False
        startup_compact_checkbox_mode = None
        startup_primary_support = {
            "strong": False,
            "signals": [],
            "reason": "none",
            "image_changed_samples": 0,
            "max_change_score": 0.0,
        }
        startup_preflight_support = {
            "strong": False,
            "signals": [],
            "reason": "none",
            "image_changed_samples": 0,
            "max_change_score": 0.0,
        }
        powers_autoskip_startup = False
        if startup_recovery:
            startup_ctx = getattr(self, "_startup_context", {}) if self._startup_context_active() else {}
            startup_spec_class = startup_ctx.get("current_spec_class", "unknown")
            safe_filler_state = startup_spec_class == "NON_TARGET filler"
            bridge_fallback_reason = startup_ctx.get("preflight_fallback_reason", "none")
            powers_autoskip_startup = bool(
                self.roll_domain == "powers"
                and safe_filler_state
                and startup_ctx.get("powers_autoskip_current")
            )
            compact_non_target_preflight = (
                powers_autoskip_startup
                or (
                    self.roll_domain == "powers" and safe_filler_state and bridge_fallback_reason in {
                        "weak_non_improving_bridge_probe",
                        "weak_non_improving_dead_phase",
                        "none",
                        "stat_numbers_changed",
                    }
                )
            )
            if powers_autoskip_startup:
                quick_verify_kwargs = self._stats_verify_profile(
                    "startup_safe_filler_preflight",
                    popup_known_false=True,
                )
            reused_popup_clear = compact_non_target_preflight
            startup_popup_state = False if reused_popup_clear else self._popup_active_checked(
                log=True,
                context=f"{label} startup observe",
                fast=True,
            )
            fast_non_target_preflight = startup_spec_class == "NON_TARGET filler" and not startup_popup_state
            if compact_non_target_preflight:
                preflight_kwargs = self._stats_verify_profile(
                    "startup_safe_filler_preflight",
                    popup_known_false=reused_popup_clear,
                )
            else:
                preflight_kwargs = {
                    "polls_override": min(2, verify_polls),
                    "poll_delay_override": self._startup_verify_poll_delay_cap(preflight=True),
                    "unreadable_fast_fail_polls": 1,
                    "psm_sequence_override": (6, 7) if fast_non_target_preflight else None,
                    "post_popup_check_enabled": True,
                    "candidate_signal_enabled": True,
                    "abandon_on_weak_samples": None,
                    "initial_popup_known_false": reused_popup_clear,
                    "fast_popup_checks": True,
                    "fast_post_popup_check": True,
                }
            preflight_started = time.perf_counter()
            if powers_autoskip_startup:
                preflight_changed = False
                preflight_text = baseline
                startup_preflight_rolling_state = "not_rolling"
                self.log(
                    f"[Startup Timing] powers_autoskip_preflight_skipped=True | "
                    f"reason=autoskip_power_not_listed | {label}"
                )
            else:
                preflight_changed, preflight_text = self.stats_changed(
                    baseline,
                    f"{label} preflight rolling check",
                    **preflight_kwargs,
                )
                startup_preflight_rolling_state = self.last_recovery_verify_state if not preflight_changed else "rolling"
            self.log(
                f"[Startup Observe] auto_state=pending | rolling_state={startup_preflight_rolling_state} | "
                f"popup_state={startup_popup_state} | phase=preflight | "
                f"elapsed={int((time.perf_counter() - preflight_started) * 1000)}ms | "
                f"startup_preflight_ms={int((time.perf_counter() - preflight_started) * 1000)} | "
                f"fast_non_target_preflight={fast_non_target_preflight} | compact_non_target_preflight={compact_non_target_preflight} | "
                f"reused_popup_clear={reused_popup_clear} | bridge_fallback_reason={bridge_fallback_reason}"
            )
            if preflight_changed:
                preflight_details = self.last_recovery_verify_details or {}
                preflight_support = self._startup_confirmation_support(
                    "rolling",
                    preflight_details,
                    self.last_recovery_reason,
                    popup_state=startup_popup_state,
                )
                startup_preflight_support = dict(preflight_support)
                if preflight_support["strong"]:
                    self.log(
                        f"[Startup Decide] auto_state=skipped | rolling_state=rolling | popup_state={startup_popup_state} | "
                        f"decision=continue | reason=behavior already confirms rolling before checkbox action | "
                        f"support={'+'.join(preflight_support['signals']) or 'ocr'} | confidence=strong | {label}"
                    )
                    self._record_recovery_duration(label, started)
                    self.log(f"[Startup Reliability] startup_attempt_reliability=strong | first_attempt_exit_reason=preflight_confirmed | retry_trigger_reason=none | guarded_recovery=not_needed | {label}")
                    self.log(f"Auto-roll already active during startup preflight | OCR: {preflight_text[:80]}")
                    self.clear_recovery_failures(f"{label} preflight confirmed")
                    return finish(True, STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)
                startup_preflight_rolling_state = self.last_recovery_verify_state or "not_rolling"
                if startup_preflight_rolling_state == "rolling":
                    startup_preflight_rolling_state = "not_rolling"
                self.log(
                    f"[Startup Decide] auto_state=pending | rolling_state={startup_preflight_rolling_state} | popup_state={startup_popup_state} | "
                    f"decision=reobserve_via_checkbox_path | reason=preflight rolling signal was marginal and cannot suppress guarded startup seed path | "
                    f"support={'+'.join(preflight_support['signals']) or 'none'} | confidence=marginal | {label}"
                )
            def _startup_observe_without_toggle_reason(observed_state: str) -> str:
                if (
                    not safe_filler_state
                    or startup_popup_state
                    or observed_state not in ("disabled", "unknown")
                ):
                    return ""
                if self.roll_domain == "specs" and bool(startup_preflight_support.get("signals")):
                    return "startup_specs_observe_without_toggle"
                if self.roll_domain == "powers" and (
                    powers_autoskip_startup or bool(startup_preflight_support.get("signals"))
                ):
                    return "startup_powers_observe_without_toggle"
                return ""

            def _finish_startup_observe_without_toggle(reason: str, observed_state: str) -> bool:
                checkbox_confidence = self._auto_checkbox_confidence_tier()
                supports = list(startup_preflight_support.get("signals") or [])
                if reason == "startup_powers_observe_without_toggle" and powers_autoskip_startup:
                    if "autoskip_power_not_listed" not in supports:
                        supports.append("autoskip_power_not_listed")
                fallback_support = (
                    ["autoskip_power_not_listed"]
                    if reason == "startup_powers_observe_without_toggle" and powers_autoskip_startup
                    else ["weak_current_spec_refresh"]
                )
                self._record_startup_route(
                    "continue",
                    reason=reason,
                    confidence="marginal",
                    supports=supports or fallback_support,
                )
                self._record_startup_auto_result("observe_without_toggle")
                self.last_change = time.time()
                domain_label = "powers" if reason == "startup_powers_observe_without_toggle" else "specs"
                self.clear_recovery_failures(f"{label} {domain_label} observe without toggle")
                power_fields = ""
                if reason == "startup_powers_observe_without_toggle":
                    power_fields = (
                        f"powers_autoskip_current={bool(powers_autoskip_startup)} | "
                    )
                self.log(
                    f"[Startup Decide] auto_state={observed_state} | rolling_state={startup_preflight_rolling_state} | "
                    f"popup_state={startup_popup_state} | decision=skip_toggle_observe_first | "
                    f"reason={reason} | checkbox_confidence={checkbox_confidence} | "
                    f"startup_spec_class={startup_spec_class} | {power_fields}"
                    f"ocr_reason={startup_preflight_support.get('reason', 'none')} | "
                    f"change_score={startup_preflight_support.get('max_change_score', 0.0)} | "
                    f"support={'+'.join(supports) or 'none'} | {label}"
                )
                self._record_recovery_duration(label, started)
                return finish(True, STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)

            def _block_startup_auto_click(action_reason: str, checkbox_state: str = "", verify_state: str = "", supports=None) -> bool:
                blocked_checkbox_state = checkbox_state or startup_observed_state or "unknown"
                blocked_verify_state = verify_state or startup_preflight_rolling_state or "unknown"
                blocked_supports = list(supports or [])
                if not blocked_supports:
                    blocked_supports = [
                        f"roll_domain:{self.roll_domain}",
                        f"spec_class:{startup_spec_class or 'unknown'}",
                        f"auto:{blocked_checkbox_state or 'unknown'}",
                        f"verify:{blocked_verify_state or 'unknown'}",
                    ]
                self._record_startup_route(
                    "fail_safe",
                    reason="startup_auto_click_blocked_non_bad_current_roll",
                    confidence="weak",
                    supports=blocked_supports,
                    failure_type="non_bad_startup_auto_click_blocked",
                )
                self._record_startup_auto_result("observe_without_toggle")
                self.log(
                    f"[Startup Act] action=blocked | reason=startup_auto_click_blocked_non_bad_current_roll | "
                    f"roll_domain={self.roll_domain} | startup_spec_class={startup_spec_class or 'unknown'} | "
                    f"checkbox_state={blocked_checkbox_state or 'unknown'} | verify_state={blocked_verify_state or 'unknown'} | "
                    f"source={action_reason} | {label}"
                )
                self.log(
                    "Startup Auto click blocked because no BAD/DISABLED listed mythical or confirmed manual-reroll path was detected"
                )
                self._record_recovery_duration(label, started, success=False)
                return finish(False, failed_result("uncertain_existing_state"))

            if compact_non_target_preflight and startup_preflight_rolling_state == "not_rolling" and not startup_popup_state:
                startup_observed_state = self.auto_checkbox_state()
                self._log_auto_checkbox_state_read(f"{label} compact startup check", 1, startup_observed_state)
                self._record_startup_auto_state(startup_observed_state, 1)
                observe_without_toggle_reason = _startup_observe_without_toggle_reason(startup_observed_state)
                if observe_without_toggle_reason:
                    return _finish_startup_observe_without_toggle(observe_without_toggle_reason, startup_observed_state)
                if startup_observed_state == "enabled":
                    startup_compact_checkbox_mode = "enabled_no_click"
                    auto_enable_result = "already_enabled"
                    startup_skip_uncertainty_validation = True
                    self._record_startup_auto_result("compact_enabled_no_click")
                    self.log(
                        f"[Startup Decide] auto_state=enabled_no_click | rolling_state={startup_preflight_rolling_state} | popup_state={startup_popup_state} | "
                        f"decision=continue_without_toggle | reason=compact trusted NON_TARGET preflight stayed not_rolling but Auto already appears enabled; verify behavior next | {label}"
                    )
                    if powers_autoskip_startup and not self._auto_checkbox_enabled_is_weak():
                        self._record_startup_route(
                            "continue",
                            reason="powers_autoskip_auto_already_enabled",
                            confidence="strong",
                            supports=["autoskip_power_not_listed", "auto:enabled"],
                        )
                        self._record_recovery_duration(label, started)
                        self.last_change = time.time()
                        self.clear_recovery_failures(f"{label} powers autoskip already enabled")
                        self.log(
                            f"[Startup Route] powers_autoskip=True | action=continue | "
                            f"reason=listed Mythical not present and Auto is enabled | {label}"
                        )
                        return finish(True, STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)
                elif startup_observed_state == "disabled":
                    return _block_startup_auto_click(
                        "compact_non_target_disabled",
                        checkbox_state=startup_observed_state,
                        verify_state=startup_preflight_rolling_state,
                        supports=["compact_preflight", "non_bad_current_roll", f"spec_class:{startup_spec_class}"],
                    )
                else:
                    return _block_startup_auto_click(
                        "compact_non_target_unknown",
                        checkbox_state=startup_observed_state,
                        verify_state=startup_preflight_rolling_state,
                        supports=["compact_preflight", "non_bad_current_roll", f"spec_class:{startup_spec_class}"],
                    )
            else:
                startup_observed_state = self._observe_auto_state(label)
                if startup_observed_state == "aborted":
                    self.log("Recovery aborted due to manual stop")
                    return finish(False, STARTUP_FAILED_TIMEOUT)
                self.log(
                    f"[Startup Observe] auto_state={startup_observed_state} | rolling_state={startup_preflight_rolling_state} | "
                    f"popup_state={startup_popup_state} | phase=decision_inputs"
                )
                observe_without_toggle_reason = _startup_observe_without_toggle_reason(startup_observed_state)
                if observe_without_toggle_reason:
                    return _finish_startup_observe_without_toggle(observe_without_toggle_reason, startup_observed_state)
                if startup_observed_state == "enabled":
                    if self._auto_checkbox_enabled_is_weak():
                        self.log(
                            f"[Startup Decide] auto_state=enabled | rolling_state={startup_preflight_rolling_state} | popup_state={startup_popup_state} | decision=verify_then_guarded_seed_if_needed | "
                            f"reason=enabled read is weak/untrusted; treat as ambiguous and do not suppress guarded startup seed path | {label}"
                        )
                        self._record_startup_auto_result("weak_enabled_untrusted")
                        startup_observed_state = "unknown"
                        auto_enable_result = "uncertain_existing_state"
                    else:
                        self.log(
                            f"[Startup Decide] auto_state=enabled | rolling_state={startup_preflight_rolling_state} | popup_state={startup_popup_state} | decision=continue_without_toggle | "
                            f"reason=checkbox already enabled; verify behavior next | {label}"
                        )
                        self._record_startup_auto_result("already_enabled")
                        auto_enable_result = "already_enabled"
                elif startup_observed_state == "disabled":
                    return _block_startup_auto_click(
                        "checkbox_disabled",
                        checkbox_state=startup_observed_state,
                        verify_state=startup_preflight_rolling_state,
                    )
                else:
                    self.log(
                        f"[Startup Decide] auto_state=unknown | rolling_state={startup_preflight_rolling_state} | popup_state={startup_popup_state} | decision=verify_without_toggle | "
                        f"reason=checkbox state unreadable; verify behavior before any guarded action | {label}"
                    )
                    self._record_startup_auto_result("uncertain")
                    auto_enable_result = "uncertain_existing_state"
        else:
            auto_enable_result = self.ensure_auto_enabled(label, allow_uncertain_enable=True)

        if startup_recovery and auto_enable_result == "uncertain" and not startup_skip_uncertainty_validation:
            followup_state = self.auto_checkbox_state()
            self._log_auto_checkbox_state_read(f"{label} startup uncertainty validation", 3, followup_state)
            if followup_state == "enabled":
                self.log(
                    f"{label} startup uncertainty validation says Auto is already enabled; "
                    "continuing without another checkbox click"
                )
                auto_enable_result = "already_enabled"
            elif followup_state == "disabled":
                return _block_startup_auto_click(
                    "startup_uncertainty_validation_disabled",
                    checkbox_state=followup_state,
                    verify_state=startup_preflight_rolling_state,
                )
            else:
                self.log(
                    f"Startup auto checkbox state stayed unreadable after validation; "
                    f"not sending a speculative click and proceeding to rolling verification | {label}"
                )
                auto_enable_result = "uncertain_existing_state"
        if startup_recovery and auto_enable_result == "clicked_uncertain_rolled_back":
            self.log(f"Startup auto enable failed after safety rollback | {label}")
            self._record_recovery_duration(label, started, success=False)
            return finish(False, STARTUP_FAILED_UNCERTAIN_AUTO_STATE)
        click_verify_delay = self._startup_verify_delay_cap(clicked=True) if startup_recovery else verify_delay
        if auto_enable_result in AUTO_ENABLE_CLICK_RESULTS and not self._interruptible_sleep(click_verify_delay, f"{label} auto verify delay"):
            self.log("Recovery aborted due to manual stop")
            return finish(False, STARTUP_FAILED_TIMEOUT)

        popup_after_auto = False
        popup_cleared_during_startup = False
        if not startup_skip_primary_verify:
            popup_after_auto = self._popup_active_checked(log=True, context=f"{label} after auto ensure", fast=True)
        if popup_after_auto:
            if not self.clear_reroll_popup(f"{label} after auto ensure", already_detected=True):
                self.log(f"{label} recovery popup clear failed after auto ensure; using manual fallback")
                if not self.manual_reroll_flow(f"{label.lower()} popup recovery"):
                    return finish(False, STARTUP_FAILED_NO_ROLL_DETECTED)
            else:
                popup_cleared_during_startup = True
                self.log(f"{label} popup cleared after auto ensure; resuming auto-roll")
            if self._stop_requested(label):
                self.log("Recovery aborted due to manual stop")
                return finish(False, STARTUP_FAILED_TIMEOUT)
            resume_result = self.ensure_auto_enabled(f"{label} Auto Resume", allow_uncertain_enable=True)
            if resume_result == "uncertain":
                self.log(f"{label} auto resume uncertain after popup clear; verifying without toggle")
            if startup_recovery and resume_result == "clicked_uncertain_rolled_back":
                self.log(f"Startup auto resume failed after safety rollback | {label}")
                self._record_recovery_duration(label, started, success=False)
                return finish(False, STARTUP_FAILED_UNCERTAIN_AUTO_STATE)
            resume_verify_delay = self._startup_verify_delay_cap(clicked=True) if startup_recovery else verify_delay
            if resume_result in AUTO_ENABLE_CLICK_RESULTS and not self._interruptible_sleep(resume_verify_delay, f"{label} resume verify delay"):
                self.log("Recovery aborted due to manual stop")
                return finish(False, STARTUP_FAILED_TIMEOUT)

        auto_verify_state = "not_rolling"
        auto_verify_details = {}
        guarded_verify_state = "not_rolling"
        guarded_verify_details = {}
        skip_double_check = False
        skip_double_check_reason = ""
        changed = False
        if startup_skip_primary_verify:
            self.log(
                f"[Startup Route] compact_preflight_shortcut=True | phase=primary | "
                f"action=skip_primary_verify_and_go_guarded | {label}"
            )
        else:
            stage_started = time.perf_counter()
            changed, new_text = self.stats_changed(baseline, f"{label} auto verify", **quick_verify_kwargs)
            auto_verify_state = self.last_recovery_verify_state if not changed else "rolling"
            auto_verify_details = self.last_recovery_verify_details or {}
            self.log(
                f"[Startup Verify] verify_attempt=primary | signal_sources={'+'.join(auto_verify_details.get('signal_sources', ['ocr', 'popup', 'banner', 'image_change']))} | "
                f"material_change={auto_verify_details.get('image_changed_samples', 0) > 0} | change_score={auto_verify_details.get('max_change_score', 0.0)} | "
                f"ocr_quality={'unreadable' if self.last_recovery_verify_unreadable else 'readable_or_mixed'} | classification={auto_verify_state} | "
                f"reason={self.last_recovery_reason or auto_verify_details.get('reason', 'none')} | elapsed={int((time.perf_counter() - stage_started) * 1000)}ms | early_exit={changed} | {label}"
            )
            if changed:
                startup_changed_confirmed = True
                if startup_recovery:
                    startup_changed_confirmed, startup_primary_support = self._startup_accepts_changed_confirmation(
                        auto_verify_details,
                        self.last_recovery_reason,
                        popup_state=popup_after_auto,
                        popup_cleared=popup_cleared_during_startup,
                        phase="primary",
                    )
                if startup_changed_confirmed:
                    if auto_enable_result in AUTO_UNCERTAIN_CLICK_RESULTS:
                        validation_text = "Startup auto enable validated" if startup_recovery else "Auto enable validated"
                        self.log(f"{validation_text} | {label}")
                    self._record_recovery_duration(label, started)
                    self.log(f"Auto-roll active | OCR: {new_text[:80]}")
                    self.clear_recovery_failures(f"{label} confirmed")
                    result = STARTUP_POPUP_CLEARED_AND_RESUMED if popup_cleared_during_startup else STARTUP_CONFIRMED_ROLLING
                    return finish(True, result, rolling_confirmed=True)
                changed = False
                auto_verify_state = "not_rolling"
                self.log(
                    f"[Startup Route] weak_evidence_rejected=True | phase=primary | "
                    f"reason={startup_primary_support.get('reason', 'none')} | "
                    f"support={'+'.join(startup_primary_support.get('signals', [])) or 'none'} | "
                    f"action=reopen_guarded_startup_path | {label}"
                )
            elif (
                startup_recovery
                and startup_compact_checkbox_mode == "enabled_no_click"
                and auto_verify_state == "not_rolling"
                and not self.last_recovery_verify_unreadable
                and not popup_after_auto
            ):
                skip_double_check = True
                skip_double_check_reason = "compact_enabled_no_click_decisive_nonconfirming_primary"
                self.log(
                    f"[Startup Route] double_check_skipped=True | reason={skip_double_check_reason} | "
                    f"verify_state={auto_verify_state} | {label}"
                )
            elif (
                startup_recovery
                and powers_autoskip_startup
                and startup_compact_checkbox_mode == "disabled_clicked"
                and auto_verify_state in {"not_rolling", "unreadable_static"}
                and not popup_after_auto
            ):
                skip_double_check = True
                skip_double_check_reason = "powers_autoskip_disabled_click_fast_verify_complete"
                self.log(
                    f"[Startup Route] double_check_skipped=True | reason={skip_double_check_reason} | "
                    f"verify_state={auto_verify_state} | {label}"
                )
        if auto_enable_result in AUTO_UNCERTAIN_CLICK_RESULTS:
            failure_context = (
                "Startup auto enable failed after uncertain-state handling"
                if startup_recovery
                else "Auto enable failed after uncertain-state handling"
            )
            self.log(f"{failure_context} | {label}")

        startup_primary_support_summary = "+".join(startup_primary_support.get("signals", [])) or "none"
        startup_primary_support_is_marker_only = (
            "current_spec_refresh" in startup_primary_support.get("signals", [])
            and len(startup_primary_support.get("signals", [])) == 1
            and int(startup_primary_support.get("image_changed_samples", 0) or 0) <= 0
        )
        startup_guarded_seed_needed = (
            self.last_recovery_verify_unreadable
            or auto_verify_state in {"not_rolling", "unreadable_static", "unreadable_but_changed"}
            or startup_primary_support_is_marker_only
        )
        if (
            startup_recovery
            and not changed
            and not startup_guarded_click_used
            and startup_observed_state == "unknown"
            and startup_preflight_rolling_state != "rolling"
            and not popup_after_auto
            and startup_guarded_seed_needed
        ):
            if self.roll_domain == "powers" and auto_verify_state in {"not_rolling", "unreadable_static", "unreadable_but_changed"}:
                sampled_power_route = self._startup_power_bad_from_verify_samples(label, auto_verify_details)
                if sampled_power_route == "rerolled":
                    self._record_startup_route(
                        "manual_reroll",
                        reason="startup_verify_sample_supported_bad_power",
                        confidence="strong",
                        supports=["verify_sample_bad_power"],
                    )
                    self._record_recovery_duration(label, started)
                    return finish(True, STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)
                if sampled_power_route == "failed":
                    self._record_startup_route(
                        "manual_reroll",
                        reason="startup_verify_sample_bad_power_manual_reroll_failed",
                        confidence="strong",
                        supports=["verify_sample_bad_power"],
                        failure_type="manual_reroll_failed",
                    )
                    self._record_recovery_duration(label, started, success=False)
                    return finish(False, STARTUP_FAILED_NO_ROLL_DETECTED)
            if self.roll_domain == "specs" and safe_filler_state:
                weak_support = list(startup_primary_support.get("signals") or [])
                if weak_support:
                    self._record_startup_route(
                        "fail_safe",
                        reason="spec_safe_filler_weak_stale_evidence_rejected",
                        confidence="weak",
                        supports=weak_support,
                        failure_type="weak_stale_evidence_not_proving_rolling",
                    )
                    self.log(
                        "spec safe filler startup avoided blind Auto click | "
                        "route_reason=spec_safe_filler_weak_stale_evidence_rejected | "
                        f"reason=weak_or_stale_rolling_signal | support={'+'.join(weak_support)} | "
                        "decision=fail_safe_without_fake_confirm | "
                        f"{label}"
                    )
                    self._record_recovery_duration(label, started, success=False)
                    return finish(False, failed_result("uncertain_existing_state"))
                self._record_startup_route(
                    "fail_safe",
                    reason="spec_safe_filler_unproven_auto_state_fail_safe",
                    confidence="weak",
                    supports=["safe_filler_state", f"auto:{startup_observed_state}", f"verify:{auto_verify_state}"],
                    failure_type="safe_filler_unproven_auto_state",
                )
                self.log(
                    "spec safe filler startup avoided blind Auto click | "
                    "route_reason=spec_safe_filler_unproven_auto_state_fail_safe | "
                    f"reason=unproven_auto_state | auto_state={startup_observed_state} | verify_state={auto_verify_state} | {label}"
                )
                self.log("manual reroll blocked for safe filler because current roll was not BAD/DISABLED")
                self._record_recovery_duration(label, started, success=False)
                return finish(False, failed_result("uncertain_existing_state"))
            if startup_compact_checkbox_mode == "unknown_guarded_path":
                return _block_startup_auto_click(
                    "compact_unknown_guarded_recovery",
                    checkbox_state=startup_observed_state,
                    verify_state=auto_verify_state,
                    supports=["compact_preflight", "non_bad_current_roll", f"verify:{auto_verify_state}"],
                )
            return _block_startup_auto_click(
                "guarded_unreadable_recovery",
                checkbox_state=startup_observed_state,
                verify_state=auto_verify_state,
                supports=[f"support:{startup_primary_support_summary}", f"verify:{auto_verify_state}"],
            )

        if self.last_recovery_verify_unreadable and self.last_recovery_verify_state != "unreadable_but_changed" and (
            ("Stuck Recovery" in label and self.last_recovery_fallback_unclassified)
            or "Initial Auto Start" in label
        ):
            if auto_enable_result == "startup_fallback_clicked":
                self.log(f"Startup fallback click did not confirm rolling | {label}")
                if safe_filler_state and guarded_verify_state in ("not_rolling", "unreadable_static", "unreadable_but_changed"):
                    retry_preflight_started = time.perf_counter()
                    retry_preflight_changed, retry_preflight_text = self.stats_changed(
                        baseline,
                        f"{label} guarded recovery retry preflight",
                        **self._stats_verify_profile("startup_guarded_retry_preflight"),
                    )
                    retry_preflight_state = self.last_recovery_verify_state if not retry_preflight_changed else "rolling"
                    retry_preflight_details = self.last_recovery_verify_details or {}
                    retry_elapsed_ms = int((time.perf_counter() - retry_preflight_started) * 1000)
                    self.log(
                        f"[Startup Verify] verify_attempt=guarded_retry_preflight | signal_sources={'+'.join(retry_preflight_details.get('signal_sources', ['ocr','popup','banner','image_change']))} | "
                        f"material_change={retry_preflight_details.get('image_changed_samples', 0) > 0} | change_score={retry_preflight_details.get('max_change_score', 0.0)} | "
                        f"ocr_quality={'unreadable' if self.last_recovery_verify_unreadable else 'readable_or_mixed'} | classification={retry_preflight_state} | "
                        f"reason={self.last_recovery_reason or retry_preflight_details.get('reason', 'none')} | elapsed={retry_elapsed_ms}ms | early_exit={retry_preflight_changed} | {label}"
                    )
                    if retry_preflight_changed:
                        self._record_startup_route(
                            "continue",
                            reason="guarded_recovery_retry_preflight_confirmed",
                            confidence="strong",
                            supports=["safe_filler_state", "guarded_retry_preflight:rolling"],
                        )
                        self._record_recovery_duration(label, started)
                        self.log(f"[Startup Reliability] startup_attempt_reliability=marginal | first_attempt_exit_reason=guarded_retry_preflight_confirmed | retry_trigger_reason=none | guarded_recovery=productive | {label}")
                        self.log(f"Auto-roll active after guarded recovery retry preflight | OCR: {retry_preflight_text[:80]}")
                        self.clear_recovery_failures(f"{label} guarded retry preflight confirmed")
                        result = STARTUP_POPUP_CLEARED_AND_RESUMED if popup_cleared_during_startup else STARTUP_CONFIRMED_ROLLING
                        return finish(True, result, rolling_confirmed=True)
            self.log(
                f"{startup_verify_prefix}{label} fast-fail | unreadable context after auto verify; "
                "skipping duplicate verify/manual chain"
            )
            self.log(f"[Startup Reliability] startup_attempt_reliability=weak | first_attempt_exit_reason=guarded_recovery_no_effect | retry_trigger_reason=guarded_recovery_static | guarded_recovery=abandoned_early | {label}")
            self._record_recovery_duration(label, started, success=False)
            return finish(False, failed_result(auto_enable_result))

        if skip_double_check:
            double_verify_state = guarded_verify_state if startup_guarded_click_used else auto_verify_state
            double_verify_details = guarded_verify_details if startup_guarded_click_used else auto_verify_details
        else:
            double_check_delay = self._startup_verify_delay_cap(clicked=False) if startup_recovery else verify_delay
            if not self._interruptible_sleep(double_check_delay, f"{label} double-check delay"):
                self.log("Recovery aborted due to manual stop")
                return finish(False, STARTUP_FAILED_TIMEOUT)
            stage_started = time.perf_counter()
            changed, new_text = self.stats_changed(baseline, f"{label} double check", **quick_verify_kwargs)
            double_verify_state = self.last_recovery_verify_state if not changed else "rolling"
            double_verify_details = self.last_recovery_verify_details or {}
            self.log(
                f"[Startup Verify] verify_attempt=double_check | signal_sources={'+'.join(double_verify_details.get('signal_sources', ['ocr', 'popup', 'banner', 'image_change']))} | material_change={double_verify_details.get('image_changed_samples', 0) > 0} | change_score={double_verify_details.get('max_change_score', 0.0)} | ocr_quality={'unreadable' if self.last_recovery_verify_unreadable else 'readable_or_mixed'} | classification={double_verify_state} | reason={self.last_recovery_reason or double_verify_details.get('reason', 'none')} | elapsed={int((time.perf_counter() - stage_started) * 1000)}ms | early_exit={changed} | {label}"
            )
            if changed:
                double_changed_confirmed = True
                if startup_recovery:
                    double_changed_confirmed, _startup_double_support = self._startup_accepts_changed_confirmation(
                        double_verify_details,
                        self.last_recovery_reason,
                        popup_state=popup_after_auto,
                        popup_cleared=popup_cleared_during_startup,
                        phase="double_check",
                    )
                if double_changed_confirmed:
                    self._record_recovery_duration(label, started)
                    self.log(f"Auto-roll active after double check | OCR: {new_text[:80]}")
                    self.clear_recovery_failures(f"{label} double-check confirmed")
                    result = STARTUP_POPUP_CLEARED_AND_RESUMED if popup_cleared_during_startup else STARTUP_CONFIRMED_ROLLING
                    return finish(True, result, rolling_confirmed=True)
                changed = False
                double_verify_state = self.last_recovery_verify_state or "not_rolling"

        if startup_recovery:
            followup_state = self.auto_checkbox_state()
            self._log_auto_checkbox_state_read(f"{label} final startup check", 3, followup_state)
            final_verify_details = double_verify_details if not changed else (self.last_recovery_verify_details or {})
            final_verify_state = double_verify_state if not changed else "rolling"
            final_support = self._startup_confirmation_support(
                final_verify_state,
                final_verify_details,
                self.last_recovery_reason,
                popup_state=popup_after_auto,
                popup_cleared=popup_cleared_during_startup,
            )
            if self.roll_domain == "powers" and final_verify_state in ("not_rolling", "unreadable_static", "unreadable_but_changed"):
                sampled_power_route = self._startup_power_bad_from_verify_samples(label, final_verify_details)
                if sampled_power_route == "rerolled":
                    self._record_startup_route(
                        "manual_reroll",
                        reason="startup_verify_sample_supported_bad_power",
                        confidence="strong",
                        supports=["verify_sample_bad_power"],
                    )
                    self._record_recovery_duration(label, started)
                    return finish(True, STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)
                if sampled_power_route == "failed":
                    self._record_startup_route(
                        "manual_reroll",
                        reason="startup_verify_sample_bad_power_manual_reroll_failed",
                        confidence="strong",
                        supports=["verify_sample_bad_power"],
                        failure_type="manual_reroll_failed",
                    )
                    self._record_recovery_duration(label, started, success=False)
                    return finish(False, STARTUP_FAILED_NO_ROLL_DETECTED)
            support_signals = final_support.get("signals") or []
            startup_spec_class = startup_spec_class if startup_recovery else (getattr(self, "_startup_context", {}).get("current_spec_class", "unknown") if self._startup_context_active() else "unknown")
            safe_filler_state = (safe_filler_state if startup_recovery else startup_spec_class == "NON_TARGET filler") and not popup_after_auto
            if powers_autoskip_startup and followup_state == "enabled":
                self._record_startup_route(
                    "continue",
                    reason="powers_autoskip_enabled_after_bounded_check",
                    confidence="strong",
                    supports=support_signals or ["autoskip_power_not_listed", "auto:enabled"],
                )
                self.log(
                    f"{label} powers autoskip accepted enabled Auto after bounded check | "
                    f"verify_state={final_verify_state} | support={'+'.join(support_signals) or 'auto:enabled'}"
                )
                self.last_change = time.time()
                self.clear_recovery_failures(f"{label} powers autoskip enabled")
                self._record_recovery_duration(label, started)
                return finish(True, STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)
            if followup_state == "enabled" and final_support["strong"]:
                self._record_startup_route(
                    "continue",
                    reason="enabled_checkbox_with_supporting_behavior_evidence",
                    confidence="strong",
                    supports=support_signals,
                )
                self.log(
                    f"{label} final startup check accepted enabled checkbox only with supporting behavior evidence | "
                    f"support={'+'.join(support_signals) or 'ocr'} | verify_state={final_verify_state} | "
                    "continuing into main loop and deferring confirmation to watchdog"
                )
                self.last_change = time.time()
                self.clear_recovery_failures(f"{label} enabled fallback accepted with behavior support")
                self._record_recovery_duration(label, started)
                return finish(True, STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)
            if followup_state == "enabled":
                self.log(
                    f"{label} final startup check rejected enabled checkbox as sole success signal | "
                    f"verify_state={final_verify_state} | support={'+'.join(support_signals) or 'none'} | "
                    "reason=checkbox alone is not enough without supporting behavior evidence"
                )
                if safe_filler_state and final_verify_state in ("rolling", "not_rolling", "unreadable_static") and not final_support["strong"]:
                    if self.roll_domain == "specs":
                        self._record_startup_route(
                            "fail_safe",
                            reason="manual_reroll_blocked_for_non_bad_spec_startup",
                            confidence="weak",
                            supports=support_signals or ["enabled_checkbox_only"],
                            failure_type="non_bad_spec_startup_manual_reroll_blocked",
                        )
                        self.log(
                            f"[Startup Route] fallback_route=fail_safe | route_reason=manual_reroll_blocked_for_non_bad_spec_startup | "
                            f"decision_confidence=weak | supports={'+'.join(support_signals) or 'enabled_checkbox_only'} | "
                            f"state={final_verify_state} | trait={self.last_trait_seen or 'unknown'} | "
                            f"startup_spec_class={startup_spec_class} | auto_state={followup_state} | "
                            f"popup_confirmed={bool(popup_after_auto or popup_cleared_during_startup)}"
                        )
                        self._record_recovery_duration(label, started, success=False)
                        return finish(False, failed_result("uncertain_existing_state"))
                    self._record_startup_route(
                        "manual_reroll",
                        reason="enabled_checkbox_without_behavior_support_on_safe_filler",
                        confidence="weak",
                        supports=support_signals or ["enabled_checkbox_only"],
                        failure_type="enabled_checkbox_not_proving_rolling",
                    )
                    self.log(
                        f"[Startup Route] fallback_route=manual_reroll | route_reason=enabled_checkbox_without_real_rolling_proof | "
                        f"decision_confidence=weak | supports={'+'.join(support_signals) or 'enabled_checkbox_only'} | "
                        f"spec_class={startup_spec_class}"
                    )
                    self.log("Manual reroll blocked for safe filler because current roll was not BAD/DISABLED")
                    return _block_startup_auto_click(
                        "enabled_checkbox_without_real_rolling_proof",
                        checkbox_state=followup_state,
                        verify_state=final_verify_state,
                        supports=support_signals or ["enabled_checkbox_only", "safe_filler_state"],
                    )
            spec_safe_filler_manual_fallback = False
            manual_fallback_reason = "auto_resume_path_exhausted_or_manual_confirm_suspected"
            manual_fallback_log_reason = "auto_resume_not_confirmed_and_manual_fallback_selected"
            manual_fallback_confidence = "weak" if safe_filler_state else "marginal"
            manual_fallback_supports = support_signals or [f"verify:{final_verify_state}", f"auto:{followup_state}"]
            manual_reroll_blocked = (
                safe_filler_state
                and not spec_safe_filler_manual_fallback
                and followup_state != "enabled"
                and final_verify_state in ("not_rolling", "unreadable_static")
            )
            if self.roll_domain == "specs" and safe_filler_state and followup_state != "disabled":
                if support_signals:
                    self._record_startup_route(
                        "fail_safe",
                        reason="spec_safe_filler_weak_stale_evidence_rejected",
                        confidence="weak",
                        supports=support_signals,
                        failure_type="weak_stale_evidence_not_proving_rolling",
                    )
                    self.log(
                        "spec safe filler startup avoided blind Auto click | "
                        "route_reason=spec_safe_filler_weak_stale_evidence_rejected | "
                        f"reason=weak_or_stale_rolling_signal | support={'+'.join(support_signals)} | "
                        "decision=fail_safe_without_fake_confirm | "
                        f"{label}"
                    )
                    self._record_recovery_duration(label, started, success=False)
                    return finish(False, failed_result(auto_enable_result))
                self._record_startup_route(
                    "fail_safe",
                    reason="spec_safe_filler_unproven_auto_state_fail_safe",
                    confidence="weak",
                    supports=["safe_filler_state", f"verify:{final_verify_state}", f"auto:{followup_state}"],
                    failure_type="safe_filler_unproven_auto_state",
                )
                self.log(
                    "spec safe filler startup avoided blind Auto click | "
                    "route_reason=spec_safe_filler_unproven_auto_state_fail_safe | "
                    f"reason=unproven_auto_state | auto_state={followup_state} | verify_state={final_verify_state} | {label}"
                )
                self.log("manual reroll blocked for safe filler because current roll was not BAD/DISABLED")
                self._record_recovery_duration(label, started, success=False)
                return finish(False, failed_result("uncertain_existing_state"))
            if auto_enable_result == "startup_fallback_clicked":
                if spec_safe_filler_manual_fallback and final_verify_state in ("not_rolling", "unreadable_static"):
                    manual_fallback_reason = "spec_safe_filler_auto_resume_unresolved_manual_fallback"
                    manual_fallback_log_reason = manual_fallback_reason
                    manual_fallback_confidence = "weak"
                    manual_fallback_supports = support_signals or ["safe_filler_state", f"verify:{final_verify_state}", f"auto:{followup_state}"]
                    self.log("Specs safe-filler Auto resume remained unresolved after guarded startup click; allowing manual reroll fallback.")
                else:
                    self._record_startup_route(
                        "fail_safe",
                        reason="guarded_auto_resume_did_not_confirm_rolling",
                        confidence="weak",
                        supports=support_signals,
                        failure_type="guarded_click_no_effect",
                    )
                    self.log(f"Startup fallback click did not confirm rolling | {label}")
                    self._record_recovery_duration(label, started, success=False)
                    return finish(False, failed_result(auto_enable_result))

            if followup_state == "disabled" and startup_compact_checkbox_mode == "disabled_clicked":
                self._record_startup_route(
                    "fail_safe",
                    reason="compact_disabled_click_did_not_hold",
                    confidence="weak",
                    supports=["compact_preflight", "disabled_clicked", f"verify:{final_verify_state}"],
                    failure_type="compact_disabled_click_no_effect",
                )
                self.log(
                    f"{label} compact startup enable click still ended with Auto disabled on final check; "
                    "not repeating the same startup click path"
                )
                self._record_recovery_duration(label, started, success=False)
                return finish(False, failed_result("clicked"))

            if safe_filler_state and final_verify_state in ("not_rolling", "unreadable_static") and followup_state != "enabled":
                if followup_state != "disabled":
                    if spec_safe_filler_manual_fallback:
                        manual_fallback_reason = "spec_safe_filler_auto_resume_unresolved_manual_fallback"
                        manual_fallback_log_reason = manual_fallback_reason
                        manual_fallback_confidence = "weak"
                        manual_fallback_supports = ["safe_filler_state", f"verify:{final_verify_state}", f"auto:{followup_state}"]
                        self.log(
                            f"Specs safe-filler Auto resume remained unresolved with checkbox_state={followup_state}; allowing manual reroll fallback | {label}"
                        )
                    else:
                        self._record_startup_route(
                            "auto_resume",
                            reason="safe_non_target_filler_blocked_manual_reroll_route",
                            confidence="marginal" if startup_observed_state == "unknown" else "strong",
                            supports=["safe_filler_state", f"verify:{final_verify_state}", f"auto:{followup_state}"],
                            failure_type="manual_reroll_blocked_for_safe_filler",
                        )
                        self.log(
                            f"[Startup Route] fallback_route=auto_resume | route_reason=safe_non_target_filler_prefers_auto_resume | "
                            f"decision_confidence={'marginal' if startup_observed_state == 'unknown' else 'strong'} | "
                            f"supports=safe_filler_state+verify:{final_verify_state}+auto:{followup_state} | spec_class={startup_spec_class} | "
                            "manual_reroll_blocked=True"
                        )
                        self._record_startup_route(
                            "fail_safe",
                            reason="safe_filler_auto_resume_blocked_unknown_checkbox_state",
                            confidence="weak",
                            supports=["safe_filler_state", f"verify:{final_verify_state}", f"auto:{followup_state}"],
                            failure_type="safe_filler_auto_resume_blocked_unknown_state",
                        )
                        self.log(
                            f"[Startup Act] action=blocked | source=final_non_target_route_guard | reason=checkbox_state_not_confirmed_disabled | "
                            f"checkbox_state={followup_state} | {label}"
                        )
                        self.log(
                            f"Safe filler auto resume blocked to avoid toggling autoroll off while checkbox state was ambiguous | {label}"
                        )
                        self._record_recovery_duration(label, started, success=False)
                        return finish(False, failed_result("uncertain_existing_state"))
                else:
                    return _block_startup_auto_click(
                        "safe_filler_disabled_auto_resume",
                        checkbox_state=followup_state,
                        verify_state=final_verify_state,
                        supports=["safe_filler_state", f"verify:{final_verify_state}", f"auto:{followup_state}"],
                    )

            self._record_startup_route(
                "manual_reroll",
                reason=manual_fallback_reason,
                confidence=manual_fallback_confidence,
                supports=manual_fallback_supports,
                failure_type="manual_fallback_selected",
            )
            self.log(
                f"[Startup Route] fallback_route=manual_reroll | route_reason={manual_fallback_log_reason} | "
                f"decision_confidence={manual_fallback_confidence} | supports={'+'.join(manual_fallback_supports)} | "
                f"spec_class={startup_spec_class} | manual_reroll_blocked={str(manual_reroll_blocked)}"
            )
            if not bool(popup_after_auto or popup_cleared_during_startup):
                self.log("Manual reroll blocked for startup because no BAD/DISABLED mythical or popup was confirmed")
                return _block_startup_auto_click(
                    "manual_fallback_without_bad_roll",
                    checkbox_state=followup_state,
                    verify_state=final_verify_state,
                    supports=manual_fallback_supports,
                )

        if (
            startup_recovery
            and self.roll_domain == "specs"
            and not bool(popup_after_auto or popup_cleared_during_startup)
        ):
            startup_spec_class = (
                startup_spec_class
                if "startup_spec_class" in locals()
                else (
                    getattr(self, "_startup_context", {}).get("current_spec_class", "unknown")
                    if self._startup_context_active()
                    else "unknown"
                )
            )
            final_verify_state = final_verify_state if "final_verify_state" in locals() else self.last_recovery_verify_state
            followup_state = followup_state if "followup_state" in locals() else "unknown"
            self._record_startup_route(
                "fail_safe",
                reason="manual_reroll_blocked_for_non_bad_spec_startup",
                confidence="weak",
                supports=[
                    f"state:{final_verify_state or 'unknown'}",
                    f"auto:{followup_state or 'unknown'}",
                    f"spec_class:{startup_spec_class or 'unknown'}",
                ],
                failure_type="non_bad_spec_startup_manual_reroll_blocked",
            )
            self.log(
                "[Startup Route] fallback_route=fail_safe | "
                "route_reason=manual_reroll_blocked_for_non_bad_spec_startup | "
                "decision_confidence=weak | "
                f"state={final_verify_state or 'unknown'} | trait={self.last_trait_seen or 'unknown'} | "
                f"startup_spec_class={startup_spec_class or 'unknown'} | auto_state={followup_state or 'unknown'} | "
                f"popup_confirmed={bool(popup_after_auto or popup_cleared_during_startup)}"
            )
            self.log("Manual reroll blocked for Specs startup because no BAD/DISABLED mythical or popup was confirmed")
            self._record_recovery_duration(label, started, success=False)
            return finish(False, failed_result(auto_enable_result))

        self.log("Auto-roll still not confirmed after double check. Using manual reroll fallback.")
        if self._stop_requested(label):
            self.log("Recovery aborted due to manual stop")
            return finish(False, STARTUP_FAILED_TIMEOUT)
        stage_started = time.perf_counter()
        if startup_recovery:
            self._mark_startup_manual_reroll(fallback=True)
        if not self.manual_reroll_flow(f"{label.lower()} fallback"):
            self.log(
                f"{startup_verify_prefix}{label} manual fallback elapsed | "
                f"{int((time.perf_counter() - stage_started) * 1000)}ms | completed=False"
            )
            self.log(f"{label} manual fallback could not clear popup or resume safely")
            self._record_recovery_duration(label, started, success=False)
            return finish(False, failed_result(auto_enable_result))
        self.log(
            f"{startup_verify_prefix}{label} manual fallback elapsed | "
            f"{int((time.perf_counter() - stage_started) * 1000)}ms | completed=True"
        )
        if self._manual_reroll_recently_confirmed():
            self.log(
                f"{startup_verify_prefix}{label} manual fallback verify skipped | "
                "source=manual_reroll_flow_behavior_confirmed | elapsed=0ms"
            )
            self._record_recovery_duration(label, started)
            self.log("Manual fallback worked | source=manual_reroll_flow_behavior_confirmed")
            self.clear_recovery_failures(f"{label} manual fallback confirmed")
            result = STARTUP_POPUP_CLEARED_AND_RESUMED if popup_cleared_during_startup else STARTUP_CONFIRMED_ROLLING
            return finish(True, result, rolling_confirmed=True)

        if not self._interruptible_sleep(verify_delay, f"{label} manual fallback verify delay"):
            self.log("Recovery aborted due to manual stop")
            return finish(False, STARTUP_FAILED_TIMEOUT)
        manual_verify_kwargs = dict(quick_verify_kwargs)
        manual_verify_kwargs.pop("unreadable_fast_fail_polls", None)
        stage_started = time.perf_counter()
        changed, new_text = self.stats_changed(
            baseline,
            f"{label} manual fallback verify",
            ui_signals=["manual_reroll_flow_completed"],
            **manual_verify_kwargs,
        )
        self.log(
            f"{startup_verify_prefix}{label} manual fallback verify elapsed | "
            f"{int((time.perf_counter() - stage_started) * 1000)}ms | changed={changed}"
        )
        if changed:
            self._record_recovery_duration(label, started)
            self.log(f"Manual fallback worked | OCR: {new_text[:80]}")
            self.clear_recovery_failures(f"{label} manual fallback confirmed")
            result = STARTUP_POPUP_CLEARED_AND_RESUMED if popup_cleared_during_startup else STARTUP_CONFIRMED_ROLLING
            return finish(True, result, rolling_confirmed=True)

        self.log(f"Manual fallback finished, but rolling still did not confirm | baseline={self._compact_debug_text(baseline)}")
        self._record_recovery_duration(label, started, success=False)
        return finish(False, failed_result(auto_enable_result))

    def _record_recovery_duration(self, label, started, success=True):
        elapsed = max(0.0, time.perf_counter() - started)
        if success:
            self.recovery_duration_total += elapsed
            self.recovery_duration_count += 1
        avg_ms = int((self.recovery_duration_total / max(1, self.recovery_duration_count)) * 1000)
        self.log(
            f"{label} recovery timing | result={'confirmed' if success else 'failed'} | "
            f"elapsed={int(elapsed * 1000)}ms | "
            f"avg_recovery={avg_ms}ms | recoveries={self.session_recovery_count}"
        )

    def _manual_reroll_target_kind(self) -> str:
        return "power" if self.roll_domain == "powers" else "mythical"

    def _manual_reroll_reason_text(self, reason="bad mythical") -> str:
        text = str(reason or "").strip()
        target_kind = self._manual_reroll_target_kind()
        if not text:
            return f"bad {target_kind}"
        if target_kind == "power" and text == "bad mythical":
            return "bad power"
        if target_kind == "mythical" and text == "bad power":
            return "bad mythical"
        return text

    def _manual_reroll_log_context(self) -> str:
        return f"domain={self.roll_domain} target={self._manual_reroll_target_kind()}"

    def _manual_reroll_failure_reason(self) -> str:
        return f"bad {self._manual_reroll_target_kind()} manual reroll could not resume Auto safely"

    def _manual_reroll_power_decision_context(self):
        if self.roll_domain != "powers":
            return ""
        chain = dict(self.last_decision_chain or {})
        if chain.get("classification") != "BAD":
            return ""
        trait = chain.get("current_trait") or "unknown"
        missing = " ; ".join(chain.get("missing") or []) or "target stats not met"
        source = chain.get("power_candidate_source") or "unknown"
        quality = chain.get("power_candidate_quality", "unknown")
        required = chain.get("power_required_values") or {}
        return (
            f" | trigger=power_bad trait={trait} | missing={missing} | "
            f"source={source} | quality={quality} | required={required}"
        )

    def manual_reroll_flow(self, reason="bad mythical"):
        started = time.perf_counter()
        if self._stop_requested("manual reroll flow"):
            return False
        previous_manual_reroll_active = self.manual_reroll_active
        self.manual_reroll_active = True
        reason_text = self._manual_reroll_reason_text(reason)
        reroll_context = self._manual_reroll_log_context()

        def finish(value):
            self.manual_reroll_active = previous_manual_reroll_active
            return value

        if self.roll_domain == "powers":
            self.set_status("Manual power reroll")
        else:
            self.set_status("Manual reroll flow")
        self.log(f"Manual reroll flow | {reason_text} | {reroll_context}{self._manual_reroll_power_decision_context()}")
        self._set_recovery_route_snapshot(
            result="pending",
            route_reason="manual_reroll_started",
            auto_state="unknown",
            context="manual_reroll",
        )
        if self._startup_context_active():
            self._mark_startup_manual_reroll(fallback="fallback" in reason_text.lower())
        resume_baseline = self.last_text or reason_text

        startup_bad_current_spec = self._startup_context_active() and "startup current" in reason_text.lower()
        transition_profile = self._manual_reroll_timing_profile(startup_bad_current_spec)
        manual_timings = {
            "roll_click_ms": 0,
            "popup_detect_ms": 0,
            "popup_clear_ms": 0,
            "auto_checkbox_ms": 0,
            "resume_verify_ms": 0,
            "popup_route": "pending",
        }

        def log_manual_timing(result):
            total_ms = int((time.perf_counter() - started) * 1000)
            self.log(
                "Manual reroll timing | "
                f"result={result} | route={manual_timings.get('popup_route', 'unknown')} | "
                f"roll_click={manual_timings.get('roll_click_ms', 0)}ms | "
                f"popup_detect={manual_timings.get('popup_detect_ms', 0)}ms | "
                f"popup_clear={manual_timings.get('popup_clear_ms', 0)}ms | "
                f"auto_checkbox={manual_timings.get('auto_checkbox_ms', 0)}ms | "
                f"resume_verify={manual_timings.get('resume_verify_ms', 0)}ms | "
                f"total={total_ms}ms | {reroll_context}"
            )

        popup_baseline_img = self._safe_region_screenshot(self.cfg["POPUP_REGION"])
        stats_baseline_img = self._safe_region_screenshot(self.cfg["STATS_REGION"])
        roll_click_settle = transition_profile["roll_click_settle"]
        post_click_settle = transition_profile["post_click_settle"]
        roll_click_started = time.perf_counter()
        self.click(self.cfg["ROLL_BUTTON"], "Manual Reroll", settle=roll_click_settle)
        manual_timings["roll_click_ms"] = int((time.perf_counter() - roll_click_started) * 1000)
        if not self._interruptible_sleep(post_click_settle, "manual reroll settle"):
            return finish(False)

        popup_started = time.perf_counter()
        saw_popup = False
        popup_verified_clear = False
        fast_popup_result, fast_popup_details = self._manual_reroll_fast_popup_confirm(
            popup_baseline_img,
            "manual reroll fast visual",
            transition_profile,
        )
        if fast_popup_result is True:
            saw_popup = True
            popup_verified_clear = True
            manual_timings["popup_route"] = "fast_visual"
            manual_timings["popup_detect_ms"] = int((time.perf_counter() - popup_started) * 1000)
            manual_timings["popup_clear_ms"] = manual_timings["popup_detect_ms"]
            self.popup_clear_duration_total += time.perf_counter() - popup_started
            self.popup_clear_duration_count += 1
            avg_ms = int((self.popup_clear_duration_total / max(1, self.popup_clear_duration_count)) * 1000)
            self.log(
                "Reroll popup cleared | manual reroll fast visual | "
                f"route=fast_visual | appeared_score={fast_popup_details.get('appeared_score', 0)} | "
                f"cleared_score={fast_popup_details.get('cleared_score', 0)} | "
                f"elapsed={manual_timings['popup_clear_ms']}ms | avg_popup_clear={avg_ms}ms"
            )
            self._record_timing_event(
                "manual_reroll_popup_confirm",
                time.perf_counter() - popup_started,
                result="fast_visual",
                domain=self.roll_domain,
                target=self._manual_reroll_target_kind(),
            )
        elif fast_popup_result is False:
            manual_timings["popup_route"] = "fast_visual_failed"
            log_manual_timing("failed")
            return finish(False)
        else:
            manual_timings["popup_route"] = fast_popup_details.get("route", "ocr_fallback")
            self.log(
                "Manual reroll fast popup visual fallback | "
                f"route={manual_timings['popup_route']} | reason={fast_popup_details.get('reason', 'unknown')} | "
                f"appeared_score={fast_popup_details.get('appeared_score', 0)} | "
                f"cleared_score={fast_popup_details.get('cleared_score', 0)}"
            )
        popup_timeout_default = transition_profile["popup_timeout"]
        popup_poll_default = transition_profile["popup_poll_delay"]
        deadline = time.time() + max(0.5, float(self.cfg.get("MANUAL_POPUP_TIMEOUT", popup_timeout_default)))
        poll_delay = max(0.05, float(self.cfg.get("MANUAL_POPUP_POLL_DELAY", popup_poll_default)))
        attempt = 1
        while not saw_popup and time.time() < deadline:
            if self._stop_requested("manual reroll flow"):
                return finish(False)
            popup_context = f"manual reroll popup poll {attempt}"
            if self._popup_active_checked(log=True, context=popup_context, fast=False):
                saw_popup = True
                manual_timings["popup_route"] = "ocr_fallback"
                if not self.clear_reroll_popup(f"manual reroll attempt {attempt}", already_detected=True):
                    self.log("Manual reroll popup recovery failed; continuing only after defensive re-checks.")
                    break
                popup_verified_clear = True
                manual_timings["popup_clear_ms"] = int((time.perf_counter() - popup_started) * 1000)
                break
            attempt += 1
            if not self._interruptible_sleep(poll_delay, "manual reroll popup polling"):
                return finish(False)
        if manual_timings["popup_detect_ms"] <= 0:
            manual_timings["popup_detect_ms"] = int((time.perf_counter() - popup_started) * 1000)
        if not saw_popup:
            self.log(
                "Manual reroll popup not confirmed; pressing fallback Yes | "
                f"{reroll_context}"
            )
            manual_timings["popup_route"] = "direct_confirm"
            if self._stop_requested("manual reroll flow"):
                return finish(False)
            self.click(self.cfg["YES_BUTTON"], "Confirm Reroll", settle=0.22 if startup_bad_current_spec else 0.30)
            fallback_yes_delay = transition_profile["fallback_yes_delay"]
            if not self._interruptible_sleep(fallback_yes_delay, "manual reroll fallback Yes delay"):
                return finish(False)
            if self._popup_active_checked(log=True, context="manual reroll fallback Yes re-check", fast=False):
                self.log(
                    "Manual reroll fallback recovery needed; popup still present after cautious Yes | "
                    f"{reroll_context}"
                )
                popup_verified_clear = self.clear_reroll_popup("manual reroll fallback re-check", already_detected=True)
            self._record_timing_event(
                "manual_reroll_popup_confirm",
                time.perf_counter() - popup_started,
                result="fallback_yes",
                domain=self.roll_domain,
                target=self._manual_reroll_target_kind(),
            )
            manual_timings["popup_clear_ms"] = int((time.perf_counter() - popup_started) * 1000)
        else:
            cleared_settle = transition_profile["cleared_settle"]
            if not self._interruptible_sleep(cleared_settle, "manual reroll cleared settle"):
                return finish(False)
            if self.roll_domain == "powers":
                self.log(
                    "Manual power reroll popup cleared; treating popup as route confirmation | "
                    f"{reroll_context}"
                )
            self._record_timing_event(
                "manual_reroll_popup_confirm",
                time.perf_counter() - popup_started,
                result="detected_and_cleared" if manual_timings.get("popup_route") != "fast_visual" else "fast_visual",
                domain=self.roll_domain,
                target=self._manual_reroll_target_kind(),
            )
            if manual_timings["popup_clear_ms"] <= 0:
                manual_timings["popup_clear_ms"] = int((time.perf_counter() - popup_started) * 1000)

        if not popup_verified_clear and self._popup_active_checked(log=True, context="manual reroll before auto resume", fast=False):
            if not self.clear_reroll_popup("manual reroll before auto resume", already_detected=True):
                self.log(
                    "Manual reroll popup still present before auto resume; recovery may retry | "
                    f"{reroll_context}"
                )
                return finish(False)

        if self._stop_requested("manual reroll flow"):
            return finish(False)
        auto_resume_started = time.perf_counter()
        auto_checkbox_started = time.perf_counter()
        auto_result = self.ensure_auto_enabled("Manual Reroll Auto Resume", allow_uncertain_enable=True)
        manual_timings["auto_checkbox_ms"] = int((time.perf_counter() - auto_checkbox_started) * 1000)
        if auto_result == "weak_enabled":
            self.log(
                "Manual reroll auto resume has weak-enabled checkbox lean; attempting compact resume verify | "
                f"{reroll_context}"
            )
            if self._compact_manual_reroll_resume_verify(
                resume_baseline,
                transition_profile,
                popup_recently_cleared=popup_verified_clear,
            ):
                self.last_manual_reroll_confirmed_at = time.perf_counter()
                self.last_manual_reroll_confirm_reason = reason_text
                self._set_recovery_route_snapshot(
                    result="confirmed",
                    route_reason="manual_reroll_compact_verify_confirmed",
                    auto_state="weak_enabled",
                    rolling_confirmed=True,
                    support_signals=["compact_verify"],
                    context="manual_reroll",
                )
                self.log(f"Manual reroll auto resume confirmed by compact verify | {reroll_context}")
                self._record_timing_event(
                    "manual_reroll_auto_resume",
                    time.perf_counter() - auto_resume_started,
                    result="compact_verify_confirmed",
                    auto_state=str(auto_result or "unknown"),
                    domain=self.roll_domain,
                )
                manual_timings["resume_verify_ms"] = int((time.perf_counter() - auto_resume_started) * 1000) - manual_timings["auto_checkbox_ms"]
                log_manual_timing("confirmed")
                self.log(
                    f"Manual reroll flow complete | {reason_text} | {reroll_context} | "
                    f"elapsed={int((time.perf_counter() - started) * 1000)}ms"
                )
                return finish(True)
            self.log(
                "Manual reroll compact resume verify failed; escalating to immediate controlled auto re-enable verify | "
                f"{reroll_context}"
            )
            auto_result = "uncertain"
        if auto_result == "uncertain":
            self.log(
                "Manual reroll auto resume uncertain after checkbox validation; escalating to bounded recovery re-enable verify | "
                f"{reroll_context}"
            )
            recovered = self._attempt_auto_reenable_once(
                "Manual Reroll Auto Resume Recovery",
                resume_baseline,
                trait=self.last_trait_seen,
                state="BAD" if "bad" in reason_text.lower() else None,
                verify_signal="manual_reroll_auto_reenable",
                force_click_on_ambiguous=True,
                popup_recently_cleared=popup_verified_clear,
                direct_click_on_forced_unknown=True,
            )
            if not recovered:
                self._set_recovery_route_snapshot(
                    result="failed",
                    route_reason="manual_reroll_bounded_auto_reenable_failed",
                    auto_state=str(auto_result or "unknown"),
                    rolling_confirmed=False,
                    failure_type="bounded_auto_reenable_failed",
                    support_signals=["bounded_auto_reenable"],
                    context="manual_reroll",
                )
                self.log(
                    "Manual reroll auto resume bounded recovery did not safely confirm rolling; "
                    f"result={auto_result}; not reporting flow complete | {reroll_context}"
                )
                self._record_timing_event(
                    "manual_reroll_auto_resume",
                    time.perf_counter() - auto_resume_started,
                    result="bounded_recovery_failed",
                    auto_state=str(auto_result or "unknown"),
                    domain=self.roll_domain,
                )
                return finish(False)
            self.last_change = time.time()
            self.last_manual_reroll_confirmed_at = time.perf_counter()
            self.last_manual_reroll_confirm_reason = reason_text
            self._set_recovery_route_snapshot(
                result="confirmed",
                route_reason="manual_reroll_bounded_auto_reenable_confirmed",
                auto_state=str(auto_result or "unknown"),
                rolling_confirmed=True,
                support_signals=["bounded_auto_reenable"],
                context="manual_reroll",
            )
            self.log(f"Manual reroll auto resume restored by bounded recovery path | {reroll_context}")
            self._record_timing_event(
                "manual_reroll_auto_resume",
                time.perf_counter() - auto_resume_started,
                result="bounded_recovery_confirmed",
                auto_state=str(auto_result or "unknown"),
                domain=self.roll_domain,
            )
            manual_timings["resume_verify_ms"] = int((time.perf_counter() - auto_resume_started) * 1000) - manual_timings["auto_checkbox_ms"]
            log_manual_timing("confirmed")
            self.log(
                f"Manual reroll flow complete | {reason_text} | {reroll_context} | "
                f"elapsed={int((time.perf_counter() - started) * 1000)}ms"
            )
            return finish(True)
        if auto_result in AUTO_UNSAFE_RESUME_RESULTS:
            self._set_recovery_route_snapshot(
                result="failed",
                route_reason="manual_reroll_auto_resume_unsafe",
                auto_state=str(auto_result or "unknown"),
                rolling_confirmed=False,
                failure_type="unsafe_resume_result",
                context="manual_reroll",
            )
            self.log(
                "Manual reroll auto resume not safely confirmed; "
                f"result={auto_result}; not reporting flow complete | {reroll_context}"
            )
            self._record_timing_event(
                "manual_reroll_auto_resume",
                time.perf_counter() - auto_resume_started,
                result="unsafe_resume_result",
                auto_state=str(auto_result or "unknown"),
                domain=self.roll_domain,
            )
            return finish(False)
        self.log(f"Manual reroll auto resume safely confirmed | result={auto_result} | {reroll_context}")
        if auto_result in AUTO_ENABLE_CLICK_RESULTS:
            resume_verify_delay = min(
                max(0.0, float(self.cfg.get("AUTO_VERIFY_DELAY", DEFAULT_CONFIG["AUTO_VERIFY_DELAY"]))),
                transition_profile["resume_verify_delay_cap"],
            )
            if not self._interruptible_sleep(resume_verify_delay, "manual reroll auto resume delay"):
                return finish(False)
        visual_support = self._manual_reroll_visual_resume_support(
            stats_baseline_img,
            popup_recently_cleared=popup_verified_clear,
        )
        if visual_support.get("strong"):
            if auto_result in AUTO_ENABLE_CLICK_RESULTS:
                self.log(
                    "Manual reroll visual refresh observed after Auto click; running bounded resume verify | "
                    f"result={auto_result} | reason={visual_support.get('reason', 'none')} | "
                    f"change_score={visual_support.get('max_change_score', 0.0)} | {reroll_context}"
                )
            else:
                self.last_change = time.time()
                self.last_manual_reroll_confirmed_at = time.perf_counter()
                self.last_manual_reroll_confirm_reason = reason_text
                self._set_recovery_route_snapshot(
                    result="confirmed",
                    route_reason="manual_reroll_visual_resume_confirmed",
                    auto_state=str(auto_result or "unknown"),
                    rolling_confirmed=True,
                    support_signals=list(visual_support.get("signals") or []),
                    context="manual_reroll",
                )
                self.log(
                    "Manual reroll auto resume confirmed by visual roll refresh | "
                    f"result={auto_result} | reason={visual_support.get('reason', 'none')} | "
                    f"support={'+'.join(visual_support.get('signals', [])) or 'none'} | "
                    f"change_score={visual_support.get('max_change_score', 0.0)} | "
                    f"threshold={visual_support.get('threshold', 0.0)} | {reroll_context}"
                )
                self._record_timing_event(
                    "manual_reroll_auto_resume",
                    time.perf_counter() - auto_resume_started,
                    result="visual_refresh_confirmed",
                    auto_state=str(auto_result or "unknown"),
                    domain=self.roll_domain,
                )
                manual_timings["resume_verify_ms"] = int((time.perf_counter() - auto_resume_started) * 1000) - manual_timings["auto_checkbox_ms"]
                log_manual_timing("confirmed")
                self.log(
                    f"Manual reroll flow complete | {reason_text} | {reroll_context} | "
                    f"elapsed={int((time.perf_counter() - started) * 1000)}ms"
                )
                return finish(True)
        resume_verify_started = time.perf_counter()
        changed, _verify_text = self.stats_changed(
            resume_baseline,
            "Manual Reroll Auto Resume verify",
            **self._stats_verify_profile(
                "manual_reroll_resume_verify",
                transition_profile=transition_profile,
                popup_known_false=popup_verified_clear,
            ),
        )
        manual_timings["resume_verify_ms"] = int((time.perf_counter() - resume_verify_started) * 1000)
        if not changed:
            support = self._manual_reroll_resume_support(
                self.last_recovery_verify_details,
                self.last_recovery_reason,
                popup_recently_cleared=popup_verified_clear,
            )
            if support.get("strong"):
                self.last_text = support.get("sample_text") or resume_baseline
                self.last_change = time.time()
                self.last_manual_reroll_confirmed_at = time.perf_counter()
                self.last_manual_reroll_confirm_reason = reason_text
                self._set_recovery_route_snapshot(
                    result="confirmed",
                    route_reason="manual_reroll_popup_cleared_refresh_confirmed",
                    auto_state=str(auto_result or "unknown"),
                    rolling_confirmed=True,
                    support_signals=list(support.get("signals") or []),
                    context="manual_reroll",
                )
                self.log(
                    "Manual reroll auto resume confirmed by popup-cleared roll refresh | "
                    f"result={auto_result} | reason={support.get('reason', 'none')} | "
                    f"support={'+'.join(support.get('signals', [])) or 'none'} | "
                    f"image_changed_samples={support.get('image_changed_samples', 0)} | "
                    f"change_score={support.get('max_change_score', 0.0)} | {reroll_context}"
                )
                self._record_timing_event(
                    "manual_reroll_auto_resume",
                    time.perf_counter() - auto_resume_started,
                    result="popup_cleared_refresh_confirmed",
                    auto_state=str(auto_result or "unknown"),
                    domain=self.roll_domain,
                )
                log_manual_timing("confirmed")
                self.log(
                    f"Manual reroll flow complete | {reason_text} | {reroll_context} | "
                    f"elapsed={int((time.perf_counter() - started) * 1000)}ms"
                )
                return finish(True)
            self._set_recovery_route_snapshot(
                result="failed",
                route_reason="manual_reroll_verify_did_not_confirm_rolling",
                auto_state=str(auto_result or "unknown"),
                rolling_confirmed=False,
                failure_type="resume_verify_failed",
                context="manual_reroll",
            )
            self.log(
                "Manual reroll auto resume did not confirm rolling activity; "
                f"result={auto_result}; reason={support.get('reason', 'none')}; "
                f"support={'+'.join(support.get('signals', [])) or 'none'}; "
                f"not reporting flow complete | {reroll_context}"
            )
            self._record_timing_event(
                "manual_reroll_auto_resume",
                time.perf_counter() - auto_resume_started,
                result="verify_failed",
                auto_state=str(auto_result or "unknown"),
                domain=self.roll_domain,
            )
            return finish(False)
        self.log(f"Manual reroll auto resume rolling activity confirmed | result={auto_result} | {reroll_context}")
        self._record_timing_event(
            "manual_reroll_auto_resume",
            time.perf_counter() - auto_resume_started,
            result="verify_confirmed",
            auto_state=str(auto_result or "unknown"),
            domain=self.roll_domain,
        )

        self.last_change = time.time()
        self.last_manual_reroll_confirmed_at = time.perf_counter()
        self.last_manual_reroll_confirm_reason = reason_text
        self._set_recovery_route_snapshot(
            result="confirmed",
            route_reason="manual_reroll_verify_confirmed",
            auto_state=str(auto_result or "unknown"),
            rolling_confirmed=True,
            support_signals=["resume_verify"],
            context="manual_reroll",
        )
        log_manual_timing("confirmed")
        self.log(
            f"Manual reroll flow complete | {reason_text} | {reroll_context} | "
            f"elapsed={int((time.perf_counter() - started) * 1000)}ms"
        )
        return finish(True)

    def recovery_fallback_evaluate_current_roll(self, label="Recovery fallback"):
        self.last_recovery_fallback_unclassified = False
        if self._stop_requested(label):
            self.log("Recovery aborted due to manual stop")
            return "failed"
        state, trait, summary, ocr_text, missing, near = self.check_roll()
        trait_text = display_trait(trait) if trait else "unknown"
        detail = f"state={state} trait={trait_text}"
        if state == "ROLLING":
            detail += " unreadable OCR"
        self.log(f"Recovery fallback evaluation | {detail}")

        if state == "GOD":
            self.last_trait_seen = trait or self.last_trait_seen
            self._set_terminal_stop_reason(f"God roll found: {display_trait(trait)}")
            self.set_status(f"GOD ROLL | {display_trait(trait)}")
            shot = ""
            webhook_sent = False
            if self.cfg["WEBHOOK_URL"].strip():
                shot = self.capture_screen(trait)
                webhook_sent = self.send_webhook(shot, trait, summary, ocr_text)
                if webhook_sent and self.cfg.get("DELETE_SCREENSHOTS_AFTER_WEBHOOK", True):
                    shot = ""
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.on_god_roll(stamp, trait, summary, shot, webhook_sent)
            self.log("Recovery fallback found GOD roll; stopping as usual.")
            return "terminal"

        if state == "HIGH_VALUE":
            if near:
                miss_text = " | ".join(missing) if missing else "target stats not met"
                stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                distance = self._near_miss_distance_from_summary(trait, summary)
                self.on_near_miss(stamp, trait, summary, "", miss_text, distance)
                self.send_near_miss_alert(trait, summary, miss_text, distance)
            self._set_terminal_stop_reason(f"High value roll: {display_trait(trait)}")
            self.set_status(f"HIGH VALUE | {display_trait(trait)}")
            self.log("Recovery fallback found HIGH_VALUE roll; stopping as configured.")
            return "terminal"

        if state == "NON_TARGET":
            self.log(
                "Recovery fallback | current spec is NON_TARGET rollable filler; "
                "continuing normal auto-roll recovery"
            )
            return "rollable_filler"

        if state in ("BAD", "DISABLED"):
            self.log(f"Recovery fallback | current spec is {state}, rerolling manually")
            if not self.manual_reroll_flow(f"{label.lower()} current {state.lower()} {trait or 'unknown'}"):
                self.log("Recovery fallback manual reroll failed before verification")
                return "failed"
            changed, _new_text = self.stats_changed(
                ocr_text,
                f"{label} current-roll fallback verify",
                ui_signals=["classification_bad_manual_reroll"],
            )
            if changed:
                self.clear_recovery_failures(f"{label} current-roll fallback succeeded")
                self.log("Recovery fallback succeeded")
                return "recovered"
            self.log("Recovery fallback manual reroll did not verify rolling")
            return "failed"

        self.log("Recovery fallback could not classify current screen")
        self.last_recovery_fallback_unclassified = True
        return "unclassified"

    def has_current_spec_marker(self, text):
        cleaned = normalize_text(text).replace("-", " ").replace("\u2014", " ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        compact = re.sub(r"[^a-z0-9]+", "", cleaned)
        markers = [
            "currentspec",
            "currentspece",
            "currentspecs",
            "curentspec",
            "currentspee",
            "currentspecification",
        ]
        if any(m in compact for m in markers):
            return True

        words = re.findall(r"[a-z0-9]+", cleaned)
        for first, second in zip(words, words[1:]):
            first_ok = first.startswith("current") or difflib.SequenceMatcher(None, first, "current").ratio() >= 0.74
            second_ok = second.startswith("spec") or difflib.SequenceMatcher(None, second, "spec").ratio() >= 0.66
            if first_ok and second_ok:
                return True
        return False

    def _current_spec_marker_region(self):
        x, y, width, height = [int(part) for part in self.cfg["STATS_REGION"]]
        pad = 8
        marker_height = max(24, min(height, int(height * 0.42)))
        x2 = max(0, x - pad)
        y2 = max(0, y - pad)
        return (x2, y2, width + (x - x2) + pad, marker_height + (y - y2) + pad)

    def read_current_spec_marker(self):
        if not self.cfg.get("CURRENT_SPEC_MARKER_OCR", True):
            return False, ""
        marker_label = "CURRENT POWER" if self.roll_domain == "powers" else "CURRENT SPEC"
        try:
            region = self._current_spec_marker_region()
            samples = []
            for psm in (7, 6):
                text = self.ocr_region(region, psm=psm)
                samples.append(f"psm{psm}={self._compact_debug_text(text) or '<empty>'}")
                if self.has_current_spec_marker(text):
                    self.log(f"Dedicated {marker_label} marker OCR succeeded | region={region} | {' | '.join(samples)}")
                    return True, text
            self.log(f"Dedicated {marker_label} marker OCR did not find marker | region={region} | {' | '.join(samples)}")
            return False, " | ".join(samples)
        except Exception as e:
            self.log(f"Dedicated {marker_label} marker OCR skipped: {e}")
            return False, ""

    def _search_value(self, text, patterns, min_v=None, max_v=None):
        for pattern in patterns:
            m = re.search(pattern, text)
            if not m:
                continue
            val = parse_match_number(text, m, 1)
            if val is None:
                continue
            if min_v is not None and val < min_v:
                continue
            if max_v is not None and val > max_v:
                continue
            return val
        return None

    def _search_label_value(self, text, labels, min_v=None, max_v=None, exclude_before=(), reject_orphan_prefix=False):
        normalized_text = normalize_stat_tokens(text)

        def valid(value):
            if min_v is not None and value < min_v:
                return False
            if max_v is not None and value > max_v:
                return False
            return True

        normalized_labels = []
        for label in labels:
            key = canonical_stat_key(label)
            normalized_labels.append(key or normalize_ocr_text(label).replace(" ", "_"))

        for label in normalized_labels:
            label_expr = re.escape(label).replace(r"\ ", r"\s+")
            for match in re.finditer(rf"\b{label_expr}\b", normalized_text):
                prefix = normalized_text[max(0, match.start() - 18) : match.start()].strip()
                if any(prefix.endswith(word) for word in exclude_before):
                    continue

                after = normalized_text[match.end() : match.end() + 28]
                after_numbers = extract_numbers(after)
                if after_numbers:
                    value = after_numbers[0]
                    next_stat = re.search(
                        r"\b(combo_ramp|damage|crit_rate|crit_damage|npc_damage|drop|luck)\b",
                        after,
                    )
                    leading = after[: next_stat.start()] if next_stat else after
                    orphan_prefixed = bool(
                        reject_orphan_prefix
                        and 0 <= value <= 9
                        and re.fullmatch(r"\s*[a-z]\s+\d(?:\.0+)?\s*", leading or "")
                    )
                    if valid(value) and not orphan_prefixed:
                        return value

                before = normalized_text[max(0, match.start() - 28) : match.start()]
                if not re.search(r"\b(combo_ramp|damage|crit_rate|crit_damage|npc_damage|drop|luck)\b", before):
                    numbers = extract_numbers(before)
                    for value in reversed(numbers):
                        if valid(value):
                            return value

        for match in re.finditer(r"(?<![a-zA-Z0-9])\d+(?:\.\d+)?(?![a-zA-Z0-9])", normalized_text):
            value = float(match.group(0))
            if not valid(value):
                continue
            context = (
                normalized_text[max(0, match.start() - 26) : match.start()]
                + " "
                + normalized_text[match.end() : match.end() + 26]
            )
            nearby_stat_tokens = set(re.findall(r"\b(combo_ramp|damage|crit_rate|crit_damage|npc_damage|drop|luck)\b", context))
            if nearby_stat_tokens and not nearby_stat_tokens.intersection(normalized_labels):
                continue
            if len(nearby_stat_tokens) > 1:
                continue
            key = canonical_stat_key(re.sub(r"[0-9.]+", " ", context), cutoff=0.58)
            if key in normalized_labels:
                return value
        return None

    def _trait_stat_keys(self, trait):
        return [
            canonical_stat_key(label) or normalize_ocr_text(label).replace(" ", "_")
            for label in STAT_LABELS.get(trait, [])
        ]

    def _split_ocr_rows(self, text):
        raw_rows = re.split(r"[\r\n|]+", text or "")
        rows = [row.strip() for row in raw_rows if row and row.strip()]
        if text and text.strip() not in rows:
            rows.append(text.strip())
        return rows

    def _validate_labeled_value(self, trait, index, value):
        caps = STAT_CAPS.get(trait, [])
        if index >= len(caps):
            return True, ""
        cap = caps[index]
        if value < -0.05 or value > cap + 0.1:
            label = STAT_LABELS[trait][index]
            return False, f"{label}: parsed {value:g} outside plausible 0-{cap:g}"
        return True, ""

    def _coerced_value_status(self, trait, index, value):
        original = value
        value, correction = self._coerce_ocr_stat_value(trait, index, value)
        ok, reason = self._validate_labeled_value(trait, index, value)
        return ok, value, correction, reason, original

    def _coerce_ocr_stat_value(self, trait, index, value):
        caps = STAT_CAPS.get(trait, [])
        if index >= len(caps):
            return value, ""

        cap = caps[index]
        if 0 <= value <= cap + 0.1:
            return value, ""

        decimal_shifted = value / 10.0
        integer_like = abs(value - round(value)) < 0.001
        if integer_like and value >= 10 and 0 <= decimal_shifted <= cap + 0.1:
            return round(decimal_shifted, 1), f"{value:g} -> {decimal_shifted:g}"
        hundred_shifted = value / 100.0
        if trait == "rampage" and index == 3 and integer_like and value >= 200 and 0 <= hundred_shifted <= cap + 0.1:
            return round(hundred_shifted, 2), f"{value:g} -> {hundred_shifted:g}"

        return value, ""

    def _assign_labeled_value(self, trait, values, stat_key, value, source, debug):
        stat_keys = self._trait_stat_keys(trait)
        if stat_key not in stat_keys:
            return

        index = stat_keys.index(stat_key)
        label = STAT_LABELS[trait][index]
        ok, value, correction, reason, original_value = self._coerced_value_status(trait, index, value)
        if not ok:
            rejected = f"{label}=rejected({original_value:g}) from {source}"
            if values[index] is None:
                debug["parse_errors"].append(reason)
            else:
                debug.setdefault("parse_warnings", []).append(reason)
            debug["detected_labels"].append(rejected)
            return

        if values[index] is None:
            values[index] = value
            correction_note = f" corrected({correction})" if correction else ""
            debug["detected_labels"].append(f"{label}={value:g}{correction_note} from {source}")
            if stat_key == "crit_damage":
                raw_source = source.split(" in ", 1)[1] if " in " in source else source
                source_text = normalize_ocr_text(raw_source).replace(" ", "")
                if "critdamage" not in source_text:
                    debug["detected_labels"].append(f"Crit Damage recovered from fuzzy OCR label | source={source}")

    def _select_label_number(self, trait, stat_key, numbers, source, debug):
        stat_keys = self._trait_stat_keys(trait)
        if stat_key not in stat_keys or not numbers:
            return None
        index = stat_keys.index(stat_key)
        label = STAT_LABELS[trait][index]
        chosen = None
        for value in numbers:
            ok, coerced, correction, reason, original = self._coerced_value_status(trait, index, value)
            if ok and chosen is None:
                chosen = original
                debug["detected_labels"].append(
                    f"{label} matched alias {stat_key} | candidate={original:g}"
                    + (f" corrected({correction})" if correction else "")
                    + f" | source={source}"
                )
                continue
            if not ok:
                debug.setdefault("parse_warnings", []).append(reason)
                debug["detected_labels"].append(
                    f"{label} ignored noisy candidate {original:g} outside plausible range | source={source}"
                )
        return chosen

    def _filter_label_numbers(self, trait, stat_key, span, numbers, source, debug):
        filtered = list(numbers or [])
        if trait != "rampage" or stat_key != "damage" or len(filtered) != 1:
            return filtered
        value = filtered[0]
        compact_span = re.sub(r"\s+", " ", normalize_stat_tokens(span or "")).strip()
        if 0 <= value <= 9 and re.fullmatch(r"[a-z]\s+\d(?:\.0+)?", compact_span):
            debug.setdefault("parse_warnings", []).append(
                f"Damage: ignored orphan OCR debris {compact_span!r} from {source}"
            )
            debug["detected_labels"].append(
                f"Damage ignored orphan OCR debris {compact_span!r} | source={source}"
            )
            return []
        return filtered

    def _extract_values_from_segment(self, trait, segment, values, debug):
        stat_keys = self._trait_stat_keys(trait)
        if not stat_keys:
            return

        normalized = normalize_stat_tokens(normalize_text(segment))
        numbers = extract_numbers(normalized)
        if numbers:
            debug.setdefault("extracted_numbers", []).extend(numbers)
        key_expr = "|".join(re.escape(key) for key in sorted(stat_keys, key=len, reverse=True))
        matches = list(re.finditer(rf"\b({key_expr})\b", normalized))
        if not matches:
            fuzzy_key = canonical_stat_key(re.sub(r"[0-9.]+", " ", normalized), cutoff=0.58)
            if fuzzy_key in stat_keys and numbers:
                chosen = self._select_label_number(trait, fuzzy_key, numbers, f"fuzzy {segment}", debug)
                if chosen is not None:
                    self._assign_labeled_value(trait, values, fuzzy_key, chosen, f"fuzzy {segment}", debug)
                else:
                    self._assign_labeled_value(trait, values, fuzzy_key, numbers[0], f"fuzzy {segment}", debug)
            return

        debug["segments"].append(normalized)
        for idx, match in enumerate(matches):
            stat_key = match.group(1)
            next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(normalized)
            after = normalized[match.end() : next_start]
            after_numbers = extract_numbers(after)
            after_numbers = self._filter_label_numbers(
                trait,
                stat_key,
                after,
                after_numbers,
                f"alias {stat_key} in {segment}",
                debug,
            )
            if after_numbers:
                chosen = self._select_label_number(trait, stat_key, after_numbers, f"alias {stat_key} in {segment}", debug)
                if chosen is not None:
                    self._assign_labeled_value(trait, values, stat_key, chosen, f"alias {stat_key} in {segment}", debug)
                else:
                    self._assign_labeled_value(trait, values, stat_key, after_numbers[0], f"alias {stat_key} in {segment}", debug)
                continue

            before = normalized[max(0, match.start() - 28) : match.start()]
            if idx == 0 and not re.search(rf"\b({key_expr})\b", before):
                before_numbers = extract_numbers(before)
                if before_numbers:
                    chosen = self._select_label_number(trait, stat_key, list(reversed(before_numbers)), f"before alias {stat_key} in {segment}", debug)
                    if chosen is not None:
                        self._assign_labeled_value(trait, values, stat_key, chosen, f"before alias {stat_key} in {segment}", debug)
                    else:
                        self._assign_labeled_value(trait, values, stat_key, before_numbers[-1], f"before alias {stat_key} in {segment}", debug)

    def _extract_rampage_ordered_values(self, text, debug):
        stat_keys = self._trait_stat_keys("rampage")
        values = [None] * len(stat_keys)
        normalized = normalize_stat_tokens(normalize_text(text))
        key_expr = "|".join(re.escape(key) for key in stat_keys)
        matches = list(re.finditer(rf"\b({key_expr})\b", normalized))
        if not matches:
            return values

        debug.setdefault("ordered_segments", [])
        cursor = 0
        for index, stat_key in enumerate(stat_keys):
            match = next((m for m in matches if m.group(1) == stat_key and m.start() >= cursor), None)
            if not match:
                continue

            later_matches = [
                m.start()
                for m in matches
                if m.start() > match.end() and stat_keys.index(m.group(1)) > index
            ]
            next_start = min(later_matches) if later_matches else len(normalized)
            span = normalized[match.end() : next_start]
            numbers = extract_numbers(span)
            numbers = self._filter_label_numbers(
                "rampage",
                stat_key,
                span,
                numbers,
                f"ordered alias {stat_key} in {span.strip() or normalized}",
                debug,
            )
            if numbers:
                source = f"ordered alias {stat_key} in {span.strip() or normalized}"
                chosen = self._select_label_number("rampage", stat_key, numbers, source, debug)
                if chosen is not None:
                    self._assign_labeled_value("rampage", values, stat_key, chosen, source, debug)
                else:
                    self._assign_labeled_value("rampage", values, stat_key, numbers[0], source, debug)
                debug["ordered_segments"].append(f"{stat_key}:{span.strip()}")
            cursor = match.end()

        return values

    def _extract_labeled_values_by_rows(self, trait, text):
        values = [None] * len(STAT_LABELS.get(trait, []))
        debug = {
            "raw_text": text or "",
            "normalized_text": normalize_text(text or ""),
            "segments": [],
            "detected_labels": [],
            "assigned_values": {},
            "extracted_numbers": [],
            "parse_errors": [],
            "parse_warnings": [],
            "ordered_segments": [],
        }

        for row in self._split_ocr_rows(text):
            self._extract_values_from_segment(trait, row, values, debug)

        debug["assigned_values"] = {
            label: values[index] if index < len(values) else None
            for index, label in enumerate(STAT_LABELS.get(trait, []))
        }
        return values, debug

    def _merge_extracted_values(self, primary, fallback):
        primary = list(primary or [])
        fallback = list(fallback or [])
        length = max(len(primary), len(fallback))
        merged = []
        for index in range(length):
            first = primary[index] if index < len(primary) else None
            second = fallback[index] if index < len(fallback) else None
            merged.append(first if first is not None else second)
        return merged

    def _finalize_extracted_values(self, trait, values, debug):
        finalized = list(values or [])
        labels = STAT_LABELS.get(trait, [])
        for index, value in enumerate(finalized):
            if value is None:
                continue
            ok, reason = self._validate_labeled_value(trait, index, value)
            if not ok:
                finalized[index] = None
                if reason not in debug["parse_errors"]:
                    debug["parse_errors"].append(reason)
        debug["assigned_values"] = {
            label: finalized[index] if index < len(finalized) else None
            for index, label in enumerate(labels)
        }
        return finalized

    def extract_labeled_values(self, trait, text, return_debug=False):
        trait = canonical_spec_trait(trait) or trait
        row_values, debug = self._extract_labeled_values_by_rows(trait, text)

        if trait == "fortune":
            t = normalize_text(text)
            drop = self._search_value(
                t,
                [
                    r"([0-9]+(?:\.[0-9]+)?)\D{0,8}chance\s*\+?1",
                    r"fortune\s*chosen\D{0,6}([0-9]+(?:\.[0-9]+)?)",
                    r"drop(?:\s*chance)?\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                    r"\+?([0-9]+(?:\.[0-9]+)?)\D{0,12}drop(?:\s*chance)?",
                ],
                min_v=10,
                max_v=35,
            )
            if drop is None:
                drop = self._search_label_value(t, ["drop chance", "drop", "fortune chosen"], min_v=10, max_v=35)
            if drop is None:
                nums = [n for n in extract_numbers(t) if 10 <= n <= 35]
                if nums:
                    drop = nums[0]
            luck = self._search_value(
                t,
                [
                    r"luck\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                    r"\+?([0-9]+(?:\.[0-9]+)?)\D{0,12}luck",
                ],
                min_v=0,
                max_v=15,
            )
            if luck is None:
                luck = self._search_label_value(t, ["luck"], min_v=0, max_v=15)
            legacy_values = [drop, luck]
            values = self._merge_extracted_values(row_values, legacy_values)
            debug["fallback_values"] = legacy_values
            values = self._finalize_extracted_values(trait, values, debug)
            return (values, debug) if return_debug else values

        if trait == "executioner":
            t = normalize_text(text)
            npc = self._search_value(
                t,
                [
                    r"hp\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)\D{0,6}dmg",
                    r"below\s*50\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)\D{0,6}dmg",
                    r"npc\D{0,8}(?:dmg|damage)\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                    r"\+?([0-9]+(?:\.[0-9]+)?)\D{0,12}npc\D{0,8}(?:dmg|damage)",
                ],
                min_v=0,
                max_v=49.9,
            )
            if npc is None:
                npc = self._search_label_value(
                    t,
                    ["npc dmg", "npc damage", "hp"],
                    min_v=0,
                    max_v=49.9,
                    exclude_before=("crit",),
                )
            crit_damage = self._search_value(
                t,
                [
                    r"crit damage\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                ],
                min_v=0,
                max_v=30,
            )
            if crit_damage is None:
                crit_damage = self._search_label_value(t, ["crit damage"], min_v=0, max_v=30)
            crit_chance = self._search_value(
                t,
                [
                    r"crit chance\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                ],
                min_v=0,
                max_v=10,
            )
            if crit_chance is None:
                crit_chance = self._search_label_value(t, ["crit chance"], min_v=0, max_v=10)
            legacy_values = [npc, crit_chance, crit_damage]
            values = self._merge_extracted_values(row_values, legacy_values)
            debug["fallback_values"] = legacy_values
            values = self._finalize_extracted_values(trait, values, debug)
            return (values, debug) if return_debug else values

        if trait == "rampage":
            t = normalize_text(text)
            ordered_values = self._extract_rampage_ordered_values(text, debug)
            combo_ramp = self._search_value(
                t,
                [
                    r"combo\s*ramp\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                    r"\+?([0-9]+(?:\.[0-9]+)?)\D{0,12}combo\s*ramp",
                    r"rampage\D{0,14}combo\s*ramp\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                    r"rampage\D{0,24}\+?([0-9]+(?:\.[0-9]+)?)\D{0,24}cap\D{0,8}damage",
                ],
                min_v=0,
                max_v=30,
            )
            if combo_ramp is None:
                combo_ramp = self._search_label_value(t, ["combo ramp", "combo"], min_v=0, max_v=30)

            damage = self._search_value(
                t,
                [
                    r"cap\D{0,8}damage[\s.,:%+\-]{0,6}([0-9]+(?:\.[0-9]+)?)",
                    r"(?:^|[|;])\s*damage[\s.,:%+\-]{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                ],
                min_v=0,
                max_v=30,
            )
            if damage is None:
                damage = self._search_label_value(
                    t,
                    ["damage cap", "cap damage", "damage"],
                    min_v=0,
                    max_v=30,
                    exclude_before=("crit",),
                    reject_orphan_prefix=True,
                )
            crit_rate = self._search_value(
                t,
                [
                    r"crit (?:rate|chance)\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                ],
                min_v=0,
                max_v=10,
            )
            if crit_rate is None:
                crit_rate = self._search_label_value(t, ["crit rate", "crit chance"], min_v=0, max_v=10)
            crit_damage = self._search_value(
                t,
                [
                    r"crit damage\D{0,12}\+?([0-9]+(?:\.[0-9]+)?)",
                ],
                min_v=0,
                max_v=20,
            )
            if crit_damage is None:
                crit_damage = self._search_label_value(t, ["crit damage"], min_v=0, max_v=20)
            legacy_values = [combo_ramp, damage, crit_rate, crit_damage]
            values = self._merge_extracted_values(ordered_values, row_values)
            values = self._merge_extracted_values(values, legacy_values)
            debug["fallback_values"] = legacy_values
            debug["ordered_values"] = ordered_values
            values = self._finalize_extracted_values(trait, values, debug)
            return (values, debug) if return_debug else values

        return ([], debug) if return_debug else []

    def build_summary_from_labeled(self, trait, labeled_values):
        labels = STAT_LABELS[trait]
        parts = []
        for label, value in zip(labels, labeled_values):
            if value is None:
                parts.append(f"{label} ?")
            else:
                parts.append(f"{label} {value:g}")
        return " | ".join(parts)

    def summarize_check(self, trait, values, matched, labeled_values=None):
        labels = STAT_LABELS[trait]
        parts = []
        missing = []

        for i, (label, (low, high, ok)) in enumerate(zip(labels, matched)):
            target = f"{low:g}-{high:g}"
            chosen = None
            if labeled_values and i < len(labeled_values):
                chosen = labeled_values[i]
            if chosen is None:
                chosen = nearest_value(values, low, high)
            if ok:
                parts.append(f"{label} ok ({target})")
            else:
                got = f"{chosen:g}" if chosen is not None else "not found"
                parts.append(f"{label} miss (got {got}, need {target})")
                missing.append(f"{label}: {got} -> {target}")

        return " | ".join(parts), missing

    def choose_unique_value_for_range(self, values, low, high, used_indexes, tol=0.08):
        candidates = [
            (i, v)
            for i, v in enumerate(values)
            if i not in used_indexes and (low - tol) <= v <= (high + tol)
        ]
        if candidates:
            center = (low + high) / 2.0
            idx, val = min(candidates, key=lambda t: abs(t[1] - center))
            used_indexes.add(idx)
            return val

        remaining = [(i, v) for i, v in enumerate(values) if i not in used_indexes]
        if not remaining:
            return None

        idx, val = min(remaining, key=lambda t: min(abs(t[1] - low), abs(t[1] - high)))
        used_indexes.add(idx)
        return val

    def is_close_value_for_range(self, value, low, high):
        if low <= value <= high:
            return True
        margin = 0.5 if high <= 10 else 1.0
        return min(abs(value - low), abs(value - high)) <= margin

    def is_near_miss(self, trait, values, matched):
        if not values:
            return False
        ok_count = sum(1 for _, _, ok in matched if ok)
        if ok_count >= max(1, len(matched) - 1):
            return True
        close_hits = 0
        used = set()
        for low, high, _ok in matched:
            val = self.choose_unique_value_for_range(values, low, high, used)
            if val is not None and self.is_close_value_for_range(val, low, high):
                close_hits += 1
        return close_hits >= max(1, len(matched) - 1)

    def describe_miss_distance(self, trait, labeled_values, matched):
        labels = STAT_LABELS.get(trait, [])
        pieces = []
        for i, (label, (low, high, ok)) in enumerate(zip(labels, matched)):
            if ok:
                continue
            value = labeled_values[i] if i < len(labeled_values) else None
            if value is None:
                pieces.append(f"{label}: not read")
            elif value < low:
                pieces.append(f"{label}: {low - value:g} below min")
            elif value > high:
                pieces.append(f"{label}: {value - high:g} above max")
            else:
                pieces.append(f"{label}: outside tolerance")
        return " | ".join(pieces) if pieces else "Within target"

    def score_roll(self, trait, labeled_values, matched):
        caps = STAT_CAPS.get(trait, [])
        if not matched:
            return 0.0

        total = 0.0
        for index, (low, high, ok) in enumerate(matched):
            value = labeled_values[index] if index < len(labeled_values) else None
            cap = caps[index] if index < len(caps) and caps[index] else high
            if value is None:
                contribution = 0.0
            elif ok:
                contribution = 1.0
            elif value < low:
                contribution = max(0.0, 1.0 - ((low - value) / max(cap, 1.0)))
            else:
                contribution = max(0.0, 1.0 - ((value - high) / max(cap, 1.0)))
            total += contribution
        return round((total / len(matched)) * 100.0, 2)

    def build_actual_roll_summary(self, trait, values, labeled_values=None):
        if labeled_values:
            return self.build_summary_from_labeled(trait, labeled_values)

        labels = STAT_LABELS[trait]
        used_indexes = set()
        parts = []
        for label, (low, high) in zip(labels, self.rules[trait]):
            val = self.choose_unique_value_for_range(values, low, high, used_indexes)
            if val is None:
                parts.append(f"{label} ?")
            else:
                parts.append(f"{label} {val:g}")
        return " | ".join(parts)

    def merge_labeled_values(self, trait, easy_values=None, psm6_values=None):
        trait = canonical_spec_trait(trait) or trait
        easy_values = list(easy_values or [])
        psm6_values = list(psm6_values or [])

        def pick(i, primary, secondary):
            v1 = primary[i] if i < len(primary) else None
            v2 = secondary[i] if i < len(secondary) else None
            return v1 if v1 is not None else v2

        if trait == "fortune":
            return [
                pick(0, easy_values, psm6_values),
                pick(1, easy_values, psm6_values),
            ]

        if trait == "executioner":
            return [
                pick(0, easy_values, psm6_values),
                pick(1, easy_values, psm6_values),
                pick(2, easy_values, psm6_values),
            ]

        if trait == "rampage":
            return [
                pick(0, easy_values, psm6_values),
                pick(1, easy_values, psm6_values),
                pick(2, easy_values, psm6_values),
                pick(3, easy_values, psm6_values),
            ]

        return easy_values or psm6_values or []

    def _unpack_ocr_candidate(self, candidate):
        if len(candidate) >= 3:
            engine, text, raw_text = candidate[:3]
            return engine, text, raw_text
        engine, text = candidate[:2]
        return engine, text, text

    def _compact_debug_text(self, text, limit=260):
        cleaned = re.sub(r"\s+", " ", (text or "").strip())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3] + "..."

    def _log_fragment_rejection(self, engine, structure, trait, values):
        values_map = dict(zip(STAT_LABELS.get(trait, []), values))
        populated = tuple(
            (label, round(float(value))) for label, value in values_map.items() if value is not None
        )
        key = (trait, structure.get("reason", ""), populated)
        now = time.time()
        state = self._fragment_rejection_dedup.get(
            key,
            {"last_seen": 0.0, "last_logged": 0.0, "last_summary": 0.0, "suppressed": 0, "summary_at": 0},
        )
        if now - float(state.get("last_seen", 0.0)) < 90.0:
            state["suppressed"] = int(state.get("suppressed", 0)) + 1
            state["last_seen"] = now
            suppressed = state["suppressed"]
            summary_at = int(state.get("summary_at", 0))
            last_summary = float(state.get("last_summary", 0.0))
            should_summarize = suppressed in (10, 25) or (suppressed >= 50 and suppressed % 50 == 0)
            should_summarize = should_summarize or (suppressed >= 10 and now - last_summary >= 30.0)
            if should_summarize:
                if suppressed != summary_at:
                    self.log(f"Suppressed repeated fragmentary Rampage rejection x{suppressed}")
                    state["summary_at"] = suppressed
                    state["last_summary"] = now
            self._fragment_rejection_dedup[key] = state
            return
        suppressed = int(state.get("suppressed", 0))
        if suppressed:
            self.log(f"Suppressed repeated fragmentary Rampage rejection x{suppressed}")
        self.log(
            "Rejected fragmentary Rampage read | "
            f"{structure['reason']} | source={engine} | values={values_map}"
        )
        self.log("Rampage fragment recognized but not usable for classification")
        self._fragment_rejection_dedup[key] = {
            "last_seen": now,
            "last_logged": now,
            "last_summary": 0.0,
            "suppressed": 0,
            "summary_at": 0,
        }

    def _safe_artifact_label(self, label, fallback="snapshot", limit=48):
        cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(label or fallback).strip())
        cleaned = cleaned.strip("_") or fallback
        return cleaned[:limit]

    def _summarize_parse_candidates(self, parsed, trait):
        labels = STAT_LABELS.get(trait, [])
        items = []
        for item in (parsed or [])[:8]:
            values = item.get("values") or []
            items.append(
                {
                    "engine": item.get("engine", ""),
                    "quality": item.get("quality", 0),
                    "coherence": item.get("coherence", 0),
                    "score": item.get("score", 0),
                    "usable": bool(item.get("usable", True)),
                    "rejection_reason": item.get("fragment_reason", ""),
                    "marker": bool(item.get("has_marker", False)),
                    "raw_text": self._compact_debug_text(item.get("raw_text", ""), 500),
                    "normalized_text": self._compact_debug_text(item.get("text", ""), 500),
                    "values": dict(zip(labels, values)),
                    "parse_errors": list((item.get("debug") or {}).get("parse_errors") or []),
                    "parse_warnings": list((item.get("debug") or {}).get("parse_warnings") or []),
                }
            )
        return items

    def _record_ocr_candidate_debug(self, result, selection_reason):
        trait = (result or {}).get("trait")
        candidates = self._summarize_parse_candidates((result or {}).get("parsed") or [], trait)
        self.last_ocr_candidate_debug = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "trait": trait,
            "source": (result or {}).get("source_name", "none"),
            "selection_reason": selection_reason,
            "has_marker": bool((result or {}).get("has_marker", False)),
            "merged_values": ((result or {}).get("merged_debug") or {}).get("assigned_values", {}),
            "parse_errors": ((result or {}).get("merged_debug") or {}).get("parse_errors", []),
            "parse_warnings": ((result or {}).get("merged_debug") or {}).get("parse_warnings", []),
            "candidates": candidates,
        }
        self.record_decision_chain(
            subsystem="OCR",
            ocr_source=self.last_ocr_candidate_debug["source"],
            ocr_selection_reason=selection_reason,
            ocr_trait=display_trait(trait) if trait else "none",
            ocr_candidate_count=len(candidates),
        )

    def record_decision_chain(self, **updates):
        chain = dict(self.last_decision_chain or {})
        chain.update(
            {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "app_version": APP_VERSION,
                "last_event": self.last_important_event,
                "last_trait": display_trait(self.last_trait_seen) if self.last_trait_seen else "unknown",
                "recoveries": self.session_recovery_count,
                "recovery_failures": self.recovery_failures,
                "last_recovery_reason": self.last_recovery_reason,
                "popup_state": self.last_popup_state,
                "shard_state": self.last_shard_ocr_state,
                "power_shard_state": self.last_power_shard_ocr_state,
            }
        )
        chain.update(updates)
        self.last_decision_chain = chain

    def _debug_config_summary(self):
        keys = (
            "AUTO_CHECKBOX",
            "AUTO_LEFT_NUDGE",
            "STATS_REGION",
            "POPUP_REGION",
            "PROTECTED_REGION",
            "PASSIVE_SHARD_REGION",
            "POWER_SHARD_REGION",
            "REQUIRE_CURRENT_SPEC",
            "STUCK_TIMEOUT",
            "MAX_RECOVERY_ATTEMPTS",
            "PASSIVE_SHARD_LOW_THRESHOLD",
            "PASSIVE_SHARD_VERY_LOW_THRESHOLD",
            "PASSIVE_SHARD_CRITICAL_THRESHOLD",
            "PASSIVE_SHARD_EMPTY_THRESHOLD",
            "STOP_ON_EMPTY_PASSIVE_SHARDS",
            "POWER_SHARD_ALERTS",
            "POWER_SHARD_REPORT_INTERVAL",
            "POWER_SHARD_LOW_THRESHOLD",
            "POWER_SHARD_VERY_LOW_THRESHOLD",
            "POWER_SHARD_CRITICAL_THRESHOLD",
            "POWER_SHARD_EMPTY_THRESHOLD",
            "POWER_SHARD_ALERT_COOLDOWN",
            "STOP_ON_EMPTY_POWER_SHARDS",
        )
        return {
            "app": APP_DISPLAY_NAME,
            "active_targets": self._active_target_summary(limit=6),
            "enabled_specs": sorted(self.enabled_specs),
            "settings": {key: self.cfg.get(key) for key in keys},
        }

    def _prune_diagnostic_snapshots(self):
        try:
            keep = int(self.cfg.get("DEBUG_SNAPSHOT_RETENTION_COUNT", 12))
        except Exception:
            keep = 12
        if keep <= 0 or not DIAGNOSTIC_DIR.exists():
            return
        folders = sorted(
            [path for path in DIAGNOSTIC_DIR.iterdir() if path.is_dir()],
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        for path in folders[keep:]:
            try:
                for child in sorted(path.rglob("*"), key=lambda item: len(item.parts), reverse=True):
                    if child.is_file():
                        child.unlink()
                    elif child.is_dir():
                        child.rmdir()
                path.rmdir()
            except Exception:
                pass

    def _maybe_auto_capture_debug_snapshot(self, event_type, extra=None):
        if not self.cfg.get("AUTO_CAPTURE_DEBUG_SNAPSHOTS", False):
            return ""
        flag = {
            "macro_stop": "DEBUG_SNAPSHOT_ON_MACRO_STOP",
            "popup_stuck": "DEBUG_SNAPSHOT_ON_POPUP_STUCK",
            "recovery_failure": "DEBUG_SNAPSHOT_ON_RECOVERY_FAILURE",
        }.get(event_type)
        if flag and not self.cfg.get(flag, True):
            return ""
        try:
            return self.capture_diagnostic_snapshot(event_type, extra=extra)
        except Exception as e:
            self.log(f"Diagnostic snapshot failed | event={event_type} | {e}")
            return ""

    def capture_diagnostic_snapshot(self, event_type="manual", extra=None):
        DIAGNOSTIC_DIR.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe_event = self._safe_artifact_label(event_type, "manual")
        trait_label = self._safe_artifact_label(self.last_trait_seen or "unknown", "unknown", limit=24)
        base_name = f"{ARTIFACT_VERSION_PREFIX}_{stamp}_{safe_event}_{trait_label}"
        folder = DIAGNOSTIC_DIR / base_name
        suffix = 2
        while folder.exists():
            folder = DIAGNOSTIC_DIR / f"{base_name}_{suffix}"
            suffix += 1
        folder.mkdir(parents=True, exist_ok=False)

        screenshot_error = ""
        if pyautogui is not None:
            try:
                pyautogui.screenshot().save(folder / "full_screenshot.png")
                pyautogui.screenshot(region=tuple(self.cfg["STATS_REGION"])).save(folder / "stats_region.png")
                if self.passive_shard_region_enabled():
                    pyautogui.screenshot(region=tuple(self.cfg["PASSIVE_SHARD_REGION"])).save(
                        folder / "passive_shard_region.png"
                    )
                if self.power_shard_region_enabled():
                    pyautogui.screenshot(region=tuple(self.cfg["POWER_SHARD_REGION"])).save(
                        folder / "power_shard_region.png"
                    )
            except Exception as e:
                screenshot_error = str(e)
        else:
            screenshot_error = "pyautogui unavailable"

        auto_checkbox_snapshot = dict(self.last_auto_checkbox_state or {})
        try:
            if pyautogui is not None and Image is not None:
                auto_region = self.auto_checkbox_region()
                auto_img = pyautogui.screenshot(region=auto_region).convert("RGB")
                auto_img.save(folder / "auto_checkbox_region.png")
                auto_state, auto_details = self._classify_auto_checkbox_image(auto_img)
                auto_checkbox_snapshot = {
                    "state": auto_state,
                    "reason": auto_details.get("reason", ""),
                    "raw_point": tuple(self.cfg["AUTO_CHECKBOX"]),
                    "left_nudge": int(self.cfg.get("AUTO_LEFT_NUDGE", 0)),
                    "click_point": self.auto_checkbox_click_point(),
                    "region": auto_region,
                    "metrics": {"full": auto_details.get("full", {}), "inner": auto_details.get("inner", {})},
                    "image": "auto_checkbox_region.png",
                }
        except Exception as e:
            auto_checkbox_snapshot["capture_error"] = str(e)

        ocr_snapshot = dict(self.last_ocr_candidate_debug or {})
        try:
            if pyautogui is not None and pytesseract is not None:
                candidates = self.get_stats_ocr_candidates(full=True)
                parsed = self._parse_stat_ocr_candidates(candidates, bad_panel_words=[])
                ocr_snapshot = dict(self.last_ocr_candidate_debug or ocr_snapshot)
                ocr_snapshot["manual_snapshot_parse"] = {
                    "trait": parsed.get("trait"),
                    "source": parsed.get("source_name"),
                    "has_marker": parsed.get("has_marker"),
                    "merged_values": (parsed.get("merged_debug") or {}).get("assigned_values", {}),
                }
        except Exception as e:
            ocr_snapshot["capture_error"] = str(e)

        shard_snapshot = dict(self.last_shard_ocr_state or {})
        try:
            if pyautogui is not None and pytesseract is not None and self.passive_shard_region_enabled():
                shard_result = self.passive_shard_ocr_attempts(region=tuple(self.cfg["PASSIVE_SHARD_REGION"]))
                shard_snapshot = {
                    "region": shard_result.get("region"),
                    "ocr_region": shard_result.get("ocr_region"),
                    "attempts": shard_result.get("attempts", []),
                    "previous_valid": self.last_passive_shards,
                }
        except Exception as e:
            shard_snapshot["capture_error"] = str(e)

        power_shard_snapshot = dict(self.last_power_shard_ocr_state or {})
        try:
            if pyautogui is not None and pytesseract is not None and self.power_shard_region_enabled():
                power_shard_result = self.power_shard_ocr_attempts(region=tuple(self.cfg["POWER_SHARD_REGION"]))
                power_shard_snapshot = {
                    "region": power_shard_result.get("region"),
                    "ocr_region": power_shard_result.get("ocr_region"),
                    "attempts": power_shard_result.get("attempts", []),
                    "previous_valid": self.last_power_shards,
                }
        except Exception as e:
            power_shard_snapshot["capture_error"] = str(e)

        popup_snapshot = dict(self.last_popup_state or {})
        try:
            if pyautogui is not None and pytesseract is not None:
                popup_snapshot["active_now"] = self.popup_active(log=True, context=f"diagnostic {safe_event}")
        except Exception as e:
            popup_snapshot["capture_error"] = str(e)

        summary = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "event_type": event_type,
            "app": APP_DISPLAY_NAME,
            "version": APP_VERSION,
            "folder": str(folder),
            "last_decision_chain": self.last_decision_chain,
            "ocr": ocr_snapshot,
            "classification": {
                "last_trait": display_trait(self.last_trait_seen) if self.last_trait_seen else "unknown",
                "last_text": self._compact_debug_text(self.last_text, 800),
                "last_event": self.last_important_event,
            },
            "auto_checkbox": auto_checkbox_snapshot,
            "auto_checkbox_session": self.auto_checkbox_session_summary(),
            "popup": popup_snapshot,
            "recovery": {
                "failures": self.recovery_failures,
                "session_recoveries": self.session_recovery_count,
                "last_reason": self.last_recovery_reason,
                "last_change_age_seconds": round(time.time() - self.last_change, 2),
            },
            "shards": shard_snapshot,
            "power_shards": power_shard_snapshot,
            "timings": list(self.recent_timing_events[-40:]),
            "verification_cache": dict(self.last_verification_cache_stats or {}),
            "route_budget_timings": list(self.recent_route_budget_events[-20:]),
            "route_snapshots": {
                "startup": dict(self.last_startup_route_snapshot or {}),
                "recovery": dict(self.last_recovery_route_snapshot or {}),
            },
            "config": self._debug_config_summary(),
            "extra": extra or {},
            "screenshot_error": screenshot_error,
        }
        (folder / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
        (folder / "ocr_candidates.json").write_text(
            json.dumps(ocr_snapshot, indent=2, ensure_ascii=True, default=str),
            encoding="utf-8",
        )
        (folder / "shards.json").write_text(
            json.dumps(shard_snapshot, indent=2, ensure_ascii=True, default=str),
            encoding="utf-8",
        )
        (folder / "power_shards.json").write_text(
            json.dumps(power_shard_snapshot, indent=2, ensure_ascii=True, default=str),
            encoding="utf-8",
        )
        self._prune_diagnostic_snapshots()
        self.log(f"Diagnostic snapshot saved | event={event_type} | path={folder}")
        return str(folder)

    def _log_parse_debug(self, source_name, debug):
        if not self.cfg.get("OCR_DEBUG_VERBOSE", True) or not debug:
            return

        raw = self._compact_debug_text(debug.get("raw_text", ""))
        normalized = self._compact_debug_text(debug.get("normalized_text", ""))
        detected = debug.get("detected_labels") or []
        assigned = debug.get("assigned_values") or {}
        numbers = debug.get("extracted_numbers") or []
        errors = debug.get("parse_errors") or []
        warnings = debug.get("parse_warnings") or []

        self.log(f"OCR raw ({source_name}) | {raw or '<empty>'}")
        self.log(f"OCR cleaned ({source_name}) | {normalized or '<empty>'}")
        self.log(f"OCR detected labels ({source_name}) | {', '.join(detected) if detected else 'none'}")
        self.log(f"OCR extracted numbers ({source_name}) | {numbers if numbers else 'none'}")
        self.log(f"OCR assigned values ({source_name}) | {assigned}")
        if warnings:
            self.log(f"OCR parse warnings ({source_name}) | {' ; '.join(warnings)}")
        if errors:
            self.log(f"OCR parse errors ({source_name}) | {' ; '.join(errors)}")

    def _prune_ocr_debug_crops(self):
        max_files = int(self.cfg.get("OCR_DEBUG_MAX_FILES", 80))
        if max_files <= 0:
            return
        files = sorted(
            OCR_DEBUG_DIR.glob("*"),
            key=lambda path: path.stat().st_mtime if path.exists() else 0,
            reverse=True,
        )
        for path in files[max_files * 2 :]:
            try:
                if path.is_file():
                    path.unlink()
            except Exception:
                pass

    def clean_debug_artifacts(self):
        cleared = {
            "ocr_debug_files": 0,
            "ocr_debug_logs": 0,
            "debug_screenshots": 0,
        }
        for path in list(OCR_DEBUG_DIR.glob("*")) if OCR_DEBUG_DIR.exists() else []:
            try:
                if path.is_file():
                    path.unlink()
                    cleared["ocr_debug_files"] += 1
            except Exception:
                pass
        for pattern in ("aelrith_forge_v*_ocr_debug.jsonl", "aelrith_forge_ocr_debug.jsonl"):
            for path in OCR_DEBUG_DIR.glob(pattern) if OCR_DEBUG_DIR.exists() else []:
                try:
                    if path.is_file():
                        path.unlink()
                        cleared["ocr_debug_logs"] += 1
                except Exception:
                    pass
            for path in LOG_DIR.glob(pattern) if LOG_DIR.exists() else []:
                try:
                    if path.is_file():
                        path.unlink()
                        cleared["ocr_debug_logs"] += 1
                except Exception:
                    pass
        debug_capture_labels = (
            "*_webhook_test.png",
            "*_popup_stuck.png",
            "*_macro_stopped.png",
            "*_webhook_alert.png",
            "*_capture.png",
            "*_debug*.png",
            "*_preview*.png",
        )
        for pattern in debug_capture_labels:
            for path in CAPTURE_DIR.glob(pattern) if CAPTURE_DIR.exists() else []:
                try:
                    if path.is_file():
                        path.unlink()
                        cleared["debug_screenshots"] += 1
                except Exception:
                    pass
        for pattern in ("*_debug*.png", "*_preview*.png", "debug_*.png", "preview_*.png"):
            for path in LOG_DIR.glob(pattern):
                try:
                    if path.is_file():
                        path.unlink()
                        cleared["debug_screenshots"] += 1
                except Exception:
                    pass
        return cleared

    def save_ocr_debug_crop(self, trait, reason, source_text="", parse_debug=None):
        if not self.cfg.get("OCR_DEBUG_CAPTURE_ON_FAIL", True):
            return ""
        if pyautogui is None:
            self.log("OCR debug crop skipped because pyautogui is unavailable.")
            return ""

        now = time.time()
        if now - self._last_debug_capture < 3.0:
            return ""

        try:
            OCR_DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            safe_trait = re.sub(r"[^a-zA-Z0-9_-]+", "_", trait or "unknown")
            safe_reason = re.sub(r"[^a-zA-Z0-9_-]+", "_", reason or "parse_fail")[:40]
            base = f"{ARTIFACT_VERSION_PREFIX}_{time.strftime('%Y%m%d_%H%M%S')}_{safe_trait}_{safe_reason}"
            image_path = OCR_DEBUG_DIR / f"{base}.png"
            meta_path = OCR_DEBUG_DIR / f"{base}.json"

            pyautogui.screenshot(region=tuple(self.cfg["STATS_REGION"])).save(image_path)
            metadata = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "trait": trait,
                "reason": reason,
                "source_text": source_text,
                "debug": parse_debug or {},
            }
            meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            self._last_debug_capture = now
            self._prune_ocr_debug_crops()
            self.log(f"OCR debug crop saved: {image_path}")
            self._write_ocr_debug_event(
                "ocr_debug_crop",
                {
                    "trait": trait,
                    "reason": reason,
                    "image_path": str(image_path),
                    "meta_path": str(meta_path),
                    "source_text": source_text,
                    "debug": parse_debug or {},
                },
            )
            return str(image_path)
        except Exception as e:
            self.log(f"OCR debug crop failed: {e}")
            return ""

    def evaluate_trait_with_values(self, trait, labeled_values, text, source_name="merged", parse_debug=None):
        original_trait = trait
        trait = canonical_spec_trait(trait)
        if trait not in SUPPORTED_SPEC_TRAITS:
            self.log(
                "unsupported_trait_autoskip | "
                f"trait={display_trait(original_trait) if original_trait else 'unknown'} | source={source_name}"
            )
            return self.evaluate_rollable_non_target_trait(
                "non_target",
                text,
                source_name=source_name,
                parse_debug=parse_debug,
            )
        actual_summary = self.build_actual_roll_summary(trait, [], labeled_values)

        if trait not in self.enabled_specs:
            self.log(f"SKIP {trait.upper()} | Spec disabled")
            self.record_decision_chain(
                subsystem="Classification",
                classification="DISABLED",
                classification_reason="Spec disabled",
                current_trait=display_trait(trait),
                parsed_values=dict(zip(STAT_LABELS.get(trait, []), labeled_values or [])),
                summary=actual_summary,
            )
            return "DISABLED", trait, actual_summary, text, ["Spec disabled"], False

        matched = []
        for idx, (low, high) in enumerate(self.rules[trait]):
            labeled_val = labeled_values[idx] if idx < len(labeled_values) else None
            ok = labeled_val is not None and in_range([labeled_val], low, high)
            matched.append((low, high, ok))

        target_summary, missing = self.summarize_check(trait, [], matched, labeled_values=labeled_values)
        parse_errors = (parse_debug or {}).get("parse_errors") or []
        if parse_errors:
            missing.extend(f"Parsing error: {error}" for error in parse_errors)
        score = self.score_roll(trait, labeled_values, matched)
        assigned = (parse_debug or {}).get("assigned_values") or {}
        self.log(f"OCR threshold comparison ({source_name}) | assigned={assigned} | targets={self.rules[trait]}")
        self.log(f"Found {trait.upper()} ({source_name}) | Score {score:.2f} | {target_summary}")

        if all(ok for _, _, ok in matched):
            self.log(f"KEEP {trait.upper()} | {actual_summary}")
            self.record_decision_chain(
                subsystem="Classification",
                classification="GOD",
                classification_reason="all configured targets met",
                current_trait=display_trait(trait),
                parsed_values=assigned or dict(zip(STAT_LABELS.get(trait, []), labeled_values or [])),
                summary=actual_summary,
                score=score,
            )
            return "GOD", trait, actual_summary, text, missing, False

        if any("not found" in item.lower() for item in missing) or parse_errors:
            reason = "parse_error" if parse_errors else "not_found"
            self.save_ocr_debug_crop(trait, reason, text, parse_debug)

        near = self.is_near_miss(trait, [v for v in labeled_values if v is not None], matched)
        high_value = score >= float(self.cfg.get("HIGH_VALUE_STOP_SCORE", 99.5))
        if near:
            self.log(f"Near miss detected | {trait.upper()} | Score {score:.2f} | {actual_summary}")
        if high_value:
            self.log(f"High-value early stop | {trait.upper()} | Score {score:.2f}")
            self.record_decision_chain(
                subsystem="Classification",
                classification="HIGH_VALUE",
                classification_reason=f"score {score:.2f} >= high-value threshold",
                current_trait=display_trait(trait),
                parsed_values=assigned or dict(zip(STAT_LABELS.get(trait, []), labeled_values or [])),
                summary=actual_summary,
                missing=list(missing),
                score=score,
            )
            return "HIGH_VALUE", trait, actual_summary, text, [f"Score {score:.2f}"] + missing, True

        self.log(f"SKIP {trait.upper()} | {' ; '.join(missing)}")
        self.record_decision_chain(
            subsystem="Classification",
            classification="BAD",
            classification_reason="configured targets not met",
            current_trait=display_trait(trait),
            parsed_values=assigned or dict(zip(STAT_LABELS.get(trait, []), labeled_values or [])),
            summary=actual_summary,
            missing=list(missing),
            score=score,
            near_miss=bool(near),
        )
        return "BAD", trait, actual_summary, text, missing, near

    def evaluate_rollable_non_target_trait(self, trait, text, source_name="merged", parse_debug=None):
        unsupported_hint = (parse_debug or {}).get("unsupported_trait") or self._unsupported_trait_hint_from_text(text)
        summary = "Unsupported/filler trait is safe to autoskip"
        if unsupported_hint and unsupported_hint != "non_target":
            summary = f"Unsupported/filler trait ({unsupported_hint}) is safe to autoskip"
        if not (parse_debug or {}).get("autoskip_logged"):
            self.log(
                "unsupported_trait_autoskip | "
                f"trait={unsupported_hint or display_trait(trait)} | source={source_name} | safe to reroll"
            )
        self.record_decision_chain(
            subsystem="Classification",
            classification="NON_TARGET",
            classification_reason="unsupported_trait_autoskip",
            current_trait="Non-target Roll",
            parsed_values=(parse_debug or {}).get("assigned_values", {}),
            summary=summary,
        )
        return "NON_TARGET", "non_target", summary, text, ["Unsupported trait autoskip"], False

    def _candidate_parse_quality(self, trait, text, values, debug):
        found = sum(1 for value in values if value is not None)
        detected = len(debug.get("detected_labels") or [])
        numbers = len(debug.get("extracted_numbers") or [])
        errors = len(debug.get("parse_errors") or [])
        marker = 1 if self.has_current_spec_marker(text) else 0
        decimals = len(re.findall(r"\d+\.\d+", text or ""))
        complete_bonus = 12 if found >= len(STAT_LABELS.get(trait, [])) else 0
        return (found * 20) + (detected * 4) + numbers + (marker * 8) + decimals + complete_bonus - (errors * 12)

    def _rampage_structure_details(self, values, debug):
        values = list(values or [])
        field_count = sum(value is not None for value in values)
        combo_present = len(values) > 0 and values[0] is not None
        ordered_fields = {
            segment.split(":", 1)[0]
            for segment in debug.get("ordered_segments") or []
            if isinstance(segment, str) and ":" in segment and segment.split(":", 1)[1].strip()
        }
        ordered_count = len(ordered_fields)
        usable = combo_present and field_count >= 2
        reasons = []
        if field_count <= 1:
            reasons.append(f"fields={field_count}")
        if not combo_present:
            reasons.append("missing Combo Ramp")
        if ordered_count < 2:
            reasons.append(f"ordered_fields={ordered_count}")
        return {
            "usable": usable,
            "field_count": field_count,
            "combo_present": combo_present,
            "ordered_count": ordered_count,
            "reason": " ".join(reasons) if reasons else "usable",
        }

    def _candidate_parse_coherence(self, trait, values, debug):
        values = list(values or [])
        found = sum(value is not None for value in values)
        needed = len(STAT_LABELS.get(trait, []))
        errors = len(debug.get("parse_errors") or [])
        warnings = len(debug.get("parse_warnings") or [])
        ordered_hits = sum(
            1
            for segment in debug.get("ordered_segments") or []
            if isinstance(segment, str) and ":" in segment and segment.split(":", 1)[1].strip()
        )
        score = found * 18
        if needed and found >= needed:
            score += 24
        if not errors:
            score += 10
        score += ordered_hits * 8
        score -= errors * 24
        score -= warnings * 4

        if trait == "rampage" and len(values) >= 4:
            structure = self._rampage_structure_details(values, debug)
            if not structure["usable"]:
                score -= 85
            if not structure["combo_present"]:
                score -= 35
            if structure["field_count"] <= 1:
                score -= 35
            score += structure["ordered_count"] * 10
            damage = values[1]
            crit_damage = values[3]
            if damage is not None and crit_damage is not None and abs(damage - crit_damage) < 0.001:
                score -= 80
            if damage is not None and crit_damage is not None and damage < 12 and crit_damage >= 7:
                score -= 10
        return score

    def _structured_markerless_read_details(self, parsed):
        trait = (parsed or {}).get("trait")
        values = list((parsed or {}).get("merged_values") or [])
        labels = STAT_LABELS.get(trait, [])
        assigned = ((parsed or {}).get("merged_debug") or {}).get("assigned_values") or {}
        parse_errors = ((parsed or {}).get("merged_debug") or {}).get("parse_errors") or []
        candidates = (parsed or {}).get("parsed") or []
        best_quality = max((item.get("quality", 0) for item in candidates), default=0)
        value_count = sum(value is not None for value in values)
        label_count = sum(1 for label in labels if assigned.get(label) is not None)
        needed = len(self.rules.get(trait, [])) or len(labels)
        min_structured = 2 if needed <= 3 else 3
        threshold = float(self.cfg.get("CURRENT_SPEC_FALLBACK_MIN_QUALITY", 70))
        missing_labels = [label for index, label in enumerate(labels) if index >= len(values) or values[index] is None]
        accepted = (
            bool(trait)
            and value_count >= min_structured
            and label_count >= min_structured
            and best_quality >= threshold
            and not parse_errors
        )
        reasons = []
        if not trait:
            reasons.append("trait missing")
        if value_count < min_structured:
            reasons.append(f"values={value_count} < {min_structured}")
        if label_count < min_structured:
            reasons.append(f"labels={label_count} < {min_structured}")
        if best_quality < threshold:
            reasons.append(f"quality={best_quality:g} < {threshold:g}")
        if parse_errors:
            reasons.append("parse errors present")
        return {
            "accepted": accepted,
            "trait": trait,
            "value_count": value_count,
            "label_count": label_count,
            "quality": best_quality,
            "threshold": threshold,
            "missing_labels": missing_labels,
            "reason": "; ".join(reasons) if reasons else "strong structured read",
        }

    def _parse_stat_ocr_candidates(self, candidates, bad_panel_words):
        unpacked = [self._unpack_ocr_candidate(candidate) for candidate in candidates]
        last_text = unpacked[0][1] if unpacked else ""

        usable = []
        for engine, text, raw_text in unpacked:
            if self.cfg.get("OCR_DEBUG_VERBOSE", True):
                self.log(f"OCR raw ({engine}) | {self._compact_debug_text(raw_text) or '<empty>'}")
                self.log(f"OCR cleaned ({engine}) | {self._compact_debug_text(text) or '<empty>'}")
            if text and not any(word in text for word in bad_panel_words):
                usable.append((engine, text, raw_text))

        trait = None
        for _engine, text, raw_text in usable:
            trait = detect_trait(text) or detect_trait(raw_text)
            if trait:
                break

        if not trait:
            target_structure = self._target_stat_structure_result_from_candidates(usable, last_text)
            if target_structure:
                return target_structure
            rollable_non_target = None
            rollable_source = None
            for engine, text, raw_text in usable:
                rollable_non_target = (
                    detect_rollable_non_target_trait(text)
                    or detect_rollable_non_target_trait(raw_text)
                    or self._generic_rollable_non_target_from_text(text)
                    or self._generic_rollable_non_target_from_text(raw_text)
                )
                if rollable_non_target:
                    rollable_source = (engine, text, raw_text)
                    break
            if rollable_non_target and rollable_source:
                engine, text, raw_text = rollable_source
                has_marker = self.has_current_spec_marker(text) or self.has_current_spec_marker(raw_text)
                unsupported_hint = (
                    self._unsupported_trait_hint_from_text(text)
                    or self._unsupported_trait_hint_from_text(raw_text)
                    or "non_target"
                )
                result = {
                    "trait": rollable_non_target,
                    "last_text": last_text,
                    "parsed": [],
                    "merged_values": [],
                    "merged_debug": {
                        "assigned_values": {},
                        "parse_errors": [],
                        "parse_warnings": [],
                        "rollability": "non_target",
                        "unsupported_trait": unsupported_hint,
                    },
                    "source_text": text,
                    "source_name": engine,
                    "has_marker": has_marker,
                    "rollable_non_target": True,
                    "best_quality": 100 if has_marker else 70,
                }
                self._record_ocr_candidate_debug(result, "rollable_non_target_trait")
                return result
            for engine, text, _raw_text in unpacked:
                if any(word in text for word in bad_panel_words):
                    self.log(f"Ignored OCR from mythic info panel ({engine})")
            self._write_ocr_debug_event(
                "ocr_parse",
                {
                    "trait": None,
                    "reason": "trait_not_detected",
                    "last_text": last_text,
                    "candidates": [
                        {
                            "engine": engine,
                            "raw": raw_text,
                            "cleaned": text,
                            "ignored_bad_panel": any(word in text for word in bad_panel_words),
                        }
                        for engine, text, raw_text in unpacked
                    ],
                },
            )
            result = {
                "trait": None,
                "last_text": last_text,
                "parsed": [],
                "merged_values": [],
                "merged_debug": {},
                "source_text": last_text,
                "source_name": "none",
                "has_marker": False,
            }
            self._record_ocr_candidate_debug(result, "trait_not_detected")
            return result

        parsed = []
        for engine, text, raw_text in usable:
            values, debug = self.extract_labeled_values(trait, raw_text or text, return_debug=True)
            quality = self._candidate_parse_quality(trait, text, values, debug)
            coherence = self._candidate_parse_coherence(trait, values, debug)
            structure = self._rampage_structure_details(values, debug) if trait == "rampage" else {"usable": True, "reason": "usable"}
            if trait == "rampage" and not structure["usable"] and any(value is not None for value in values):
                self._log_fragment_rejection(engine, structure, trait, values)
            parsed.append(
                {
                    "engine": engine,
                    "text": text,
                    "raw_text": raw_text,
                    "values": values,
                    "debug": debug,
                    "quality": quality,
                    "coherence": coherence,
                    "score": quality + coherence,
                    "usable": bool(structure["usable"]),
                    "fragment_reason": structure["reason"],
                    "has_marker": self.has_current_spec_marker(text) or self.has_current_spec_marker(raw_text),
                }
            )
            self._log_parse_debug(engine, debug)

        if not parsed:
            result = {
                "trait": trait,
                "last_text": last_text,
                "parsed": [],
                "merged_values": [],
                "merged_debug": {},
                "source_text": last_text,
                "source_name": "none",
                "has_marker": False,
            }
            self._record_ocr_candidate_debug(result, "no_usable_candidates")
            return result

        usable_parsed = [item for item in parsed if item.get("usable", True)]
        if not usable_parsed:
            best_fragment = max(parsed, key=lambda item: (item["score"], item["quality"]))
            rollable_non_target = (
                detect_rollable_non_target_trait(best_fragment["text"])
                or detect_rollable_non_target_trait(best_fragment["raw_text"])
                or self._generic_rollable_non_target_from_text(best_fragment["text"])
                or self._generic_rollable_non_target_from_text(best_fragment["raw_text"])
            )
            if rollable_non_target and rollable_non_target != trait:
                has_marker = self.has_current_spec_marker(best_fragment["text"]) or self.has_current_spec_marker(best_fragment["raw_text"])
                unsupported_hint = (
                    self._unsupported_trait_hint_from_text(best_fragment["text"])
                    or self._unsupported_trait_hint_from_text(best_fragment["raw_text"])
                    or "non_target"
                )
                result = {
                    "trait": rollable_non_target,
                    "last_text": best_fragment["text"] or last_text,
                    "parsed": parsed,
                    "merged_values": [],
                    "merged_debug": {
                        "assigned_values": {},
                        "parse_errors": [],
                        "parse_warnings": [],
                        "rollability": "non_target",
                        "unsupported_trait": unsupported_hint,
                    },
                    "source_text": best_fragment["text"],
                    "source_name": best_fragment["engine"],
                    "has_marker": has_marker,
                    "rollable_non_target": True,
                    "best_quality": best_fragment["quality"],
                }
                self._record_ocr_candidate_debug(result, "fragment_resolved_as_rollable_non_target")
                return result
            self._write_ocr_debug_event(
                "ocr_parse",
                {
                    "trait": trait,
                    "reason": "fragmentary_rampage_read",
                    "last_text": last_text,
                    "parsed_candidates": [
                        {
                            "engine": item["engine"],
                            "quality": item["quality"],
                            "coherence": item["coherence"],
                            "score": item["score"],
                            "usable": item["usable"],
                            "fragment_reason": item["fragment_reason"],
                            "values": dict(zip(STAT_LABELS.get(trait, []), item["values"])),
                        }
                        for item in parsed
                    ],
                },
            )
            result = {
                "trait": None,
                "last_text": best_fragment["text"] or last_text,
                "parsed": parsed,
                "merged_values": [],
                "merged_debug": {},
                "source_text": best_fragment["text"],
                "source_name": "fragment",
                "has_marker": False,
            }
            self._record_ocr_candidate_debug(result, "fragmentary_rampage_read")
            return result

        parsed.sort(key=lambda item: (item.get("usable", True), item["score"], item["quality"]), reverse=True)
        usable_parsed.sort(key=lambda item: (item["score"], item["quality"]), reverse=True)
        best = usable_parsed[0]
        merged_values = list(best["values"])
        for item in parsed[1:]:
            if item.get("usable", True) and item["coherence"] >= best["coherence"] - 12:
                merged_values = self._merge_extracted_values(merged_values, item["values"])

        merged_debug = {
            "raw_text": best["raw_text"],
            "normalized_text": best["text"],
            "detected_labels": [],
            "assigned_values": dict(zip(STAT_LABELS.get(trait, []), merged_values)),
            "extracted_numbers": [],
            "parse_errors": [],
            "parse_warnings": [],
            "chosen_source": best["engine"],
        }
        for item in parsed:
            debug = item["debug"]
            merged_debug["detected_labels"].extend(debug.get("detected_labels") or [])
            merged_debug["extracted_numbers"].extend(debug.get("extracted_numbers") or [])
            merged_debug["parse_errors"].extend(debug.get("parse_errors") or [])
            merged_debug["parse_warnings"].extend(debug.get("parse_warnings") or [])

        fatal_errors = []
        for error in merged_debug["parse_errors"]:
            label = error.split(":", 1)[0]
            if merged_debug["assigned_values"].get(label) is not None:
                merged_debug["parse_warnings"].append(error)
            else:
                fatal_errors.append(error)
        merged_debug["parse_errors"] = fatal_errors

        self.log(
            "OCR chosen parse | "
            f"source={best['engine']} | "
            f"quality={best['quality']} | "
            f"coherence={best['coherence']} | "
            f"score={best['score']} | "
            f"trait={trait} | "
            f"labels={sum(value is not None for value in merged_values)} | "
            f"marker={'yes' if any(item['has_marker'] for item in parsed) else 'no'} | "
            f"values={merged_debug['assigned_values']}"
        )
        self._write_ocr_debug_event(
            "ocr_parse",
            {
                "trait": trait,
                "chosen_source": best["engine"],
                "chosen_score": best["score"],
                "chosen_coherence": best["coherence"],
                "merged_values": merged_debug["assigned_values"],
                "parse_errors": merged_debug["parse_errors"],
                "parse_warnings": merged_debug["parse_warnings"],
                "parsed_candidates": [
                    {
                        "engine": item["engine"],
                        "quality": item["quality"],
                        "coherence": item["coherence"],
                        "score": item["score"],
                        "usable": item["usable"],
                        "fragment_reason": item["fragment_reason"],
                        "has_marker": item["has_marker"],
                        "raw": item["raw_text"],
                        "cleaned": item["text"],
                        "values": dict(zip(STAT_LABELS.get(trait, []), item["values"])),
                        "detected_labels": item["debug"].get("detected_labels") or [],
                        "extracted_numbers": item["debug"].get("extracted_numbers") or [],
                        "parse_errors": item["debug"].get("parse_errors") or [],
                        "parse_warnings": item["debug"].get("parse_warnings") or [],
                    }
                    for item in parsed
                ],
            },
        )

        result = {
            "trait": trait,
            "last_text": last_text,
            "parsed": parsed,
            "merged_values": merged_values,
            "merged_debug": merged_debug,
            "source_text": best["text"],
            "source_name": best["engine"],
            "has_marker": any(item["has_marker"] for item in parsed),
            "best_quality": best["quality"],
        }
        self._record_ocr_candidate_debug(result, "selected_best_coherence_score")
        return result

    def _parsed_value_count(self, parsed):
        return sum(value is not None for value in ((parsed or {}).get("merged_values") or []))

    def _partial_target_trait_hint(self, parsed):
        trait = (parsed or {}).get("trait")
        if trait and self.is_target_trait(trait):
            return trait
        for item in (parsed or {}).get("parsed") or []:
            hint = detect_trait(item.get("text", "")) or detect_trait(item.get("raw_text", ""))
            if hint and self.is_target_trait(hint) and any(value is not None for value in item.get("values") or []):
                return hint
        return None

    def _confirm_partial_target_read(self, parsed, bad_panel_words):
        trait = self._partial_target_trait_hint(parsed)
        if not trait:
            return parsed
        needed = len(STAT_LABELS.get(trait, []))
        best = parsed
        best_count = self._parsed_value_count(best)
        if needed and best_count >= needed:
            return parsed

        attempts = max(0, int(self.cfg.get("PARTIAL_TARGET_CONFIRM_ATTEMPTS", 2)))
        if attempts <= 0:
            return parsed
        delay = max(0.0, float(self.cfg.get("PARTIAL_TARGET_CONFIRM_DELAY", 0.08)))
        self.log(
            "Partial target mythical candidate detected | "
            f"trait={display_trait(trait)} labels={best_count}/{needed or '?'}; "
            f"confirm_attempts={attempts}"
        )
        changed_target_seen = False
        for attempt in range(1, attempts + 1):
            if self._stop_requested("partial target confirm"):
                return best
            if delay and not self._interruptible_sleep(delay, "partial target confirm delay"):
                return best
            try:
                confirm_candidates = self.get_stats_ocr_candidates()
            except Exception as e:
                self.log(f"Partial target confirm attempt {attempt}/{attempts} failed to read OCR | {e}")
                continue
            confirm = self._parse_stat_ocr_candidates(confirm_candidates, bad_panel_words)
            confirm_trait = self._partial_target_trait_hint(confirm)
            confirm_count = self._parsed_value_count(confirm)
            self.log(
                "Partial target confirm attempt "
                f"{attempt}/{attempts} | trait={display_trait(confirm_trait) if confirm_trait else 'none'} "
                f"labels={confirm_count}/{len(STAT_LABELS.get(confirm_trait, [])) if confirm_trait else '?'}"
            )
            if confirm_trait != trait:
                if confirm_trait and confirm_count > 0:
                    changed_target_seen = True
                    self.log(
                        "partial target changed during confirm | "
                        f"original={display_trait(trait)} labels={best_count}/{needed or '?'} | "
                        f"new={display_trait(confirm_trait)} "
                        f"labels={confirm_count}/{len(STAT_LABELS.get(confirm_trait, [])) or '?'}"
                    )
                continue
            if confirm_count > best_count:
                best = confirm
                best_count = confirm_count
            if confirm.get("trait") == trait and needed and confirm_count >= needed:
                self.log(
                    "Partial target mythical stabilized | "
                    f"trait={display_trait(trait)} labels={confirm_count}/{needed}"
                )
                return confirm

        if best is not parsed and best_count > self._parsed_value_count(parsed):
            self.log(
                "Partial target mythical improved during confirm window | "
                f"trait={display_trait(trait)} labels={best_count}/{needed or '?'}"
            )
            return best
        if changed_target_seen:
            self.log(
                "Partial target changed during confirm; keeping original rejection path | "
                f"trait={display_trait(trait)} labels={best_count}/{needed or '?'}"
            )
            return best
        self.log(
            "Partial target mythical did not stabilize; keeping original rejection path | "
            f"trait={display_trait(trait)} labels={best_count}/{needed or '?'}"
        )
        return best

    def _parsed_needs_fallback(self, parsed):
        if (parsed or {}).get("rollable_non_target"):
            return False
        trait = (parsed or {}).get("trait")
        if not trait:
            return True
        values = (parsed or {}).get("merged_values") or []
        needed = len(STAT_LABELS.get(trait, []))
        found = sum(value is not None for value in values)
        return found < needed

    def _target_stat_structure_result_from_candidates(self, usable, last_text):
        best = None
        for engine, text, raw_text in usable:
            combined = "\n".join(part for part in (text, raw_text) if str(part or "").strip())
            cleaned = normalize_text(combined)
            if not self.has_current_spec_marker(cleaned):
                continue
            if detect_trait(cleaned):
                continue
            if "combo" not in cleaned and "comboramp" not in cleaned:
                continue
            values, debug = self.extract_labeled_values("rampage", combined, return_debug=True)
            structure = self._rampage_structure_details(values, debug)
            value_count = sum(value is not None for value in values)
            if not (structure.get("usable") and structure.get("combo_present") and value_count >= 3):
                continue
            quality = self._candidate_parse_quality("rampage", text, values, debug)
            coherence = self._candidate_parse_coherence("rampage", values, debug)
            candidate = {
                "engine": engine,
                "text": text,
                "raw_text": raw_text,
                "values": values,
                "debug": debug,
                "quality": quality,
                "coherence": coherence,
                "score": quality + coherence,
                "usable": True,
                "fragment_reason": structure.get("reason", "usable"),
                "has_marker": True,
            }
            if best is None or (candidate["score"], candidate["quality"]) > (best["score"], best["quality"]):
                best = candidate
        if not best:
            return None
        values = list(best["values"])
        merged_debug = {
            "raw_text": best["raw_text"],
            "normalized_text": best["text"],
            "detected_labels": list(best["debug"].get("detected_labels") or []),
            "assigned_values": dict(zip(STAT_LABELS["rampage"], values)),
            "extracted_numbers": list(best["debug"].get("extracted_numbers") or []),
            "parse_errors": list(best["debug"].get("parse_errors") or []),
            "parse_warnings": list(best["debug"].get("parse_warnings") or []),
            "chosen_source": best["engine"],
            "trait_inferred_from": "rampage_stat_structure",
        }
        result = {
            "trait": "rampage",
            "last_text": last_text,
            "parsed": [best],
            "merged_values": values,
            "merged_debug": merged_debug,
            "source_text": best["text"],
            "source_name": f"{best['engine']}:inferred_rampage_structure",
            "has_marker": True,
            "best_quality": best["quality"],
        }
        self.log(
            "Possible target mythical stat structure detected | "
            f"trait=Rampage | source={best['engine']} | labels={sum(value is not None for value in values)}/4"
        )
        self._record_ocr_candidate_debug(result, "inferred_rampage_stat_structure")
        return result

    def _stat_only_non_target_result_from_parsed(self, parsed, source_name="spec_fast_loop"):
        text = str((parsed or {}).get("last_text") or (parsed or {}).get("source_text") or "")
        cleaned = normalize_text(text)
        if not cleaned:
            return None
        if detect_trait(cleaned):
            return None
        if not (self.has_current_spec_marker(cleaned) and self._has_activity_stat_signal(cleaned)):
            return None
        unsupported_hint = self._unsupported_trait_hint_from_text(cleaned) or "stat_only"
        self.log(
            "unsupported_trait_autoskip | "
            f"trait={unsupported_hint} | source={source_name} | marker=yes"
        )
        result = {
            "trait": "non_target",
            "last_text": text,
            "parsed": [],
            "merged_values": [],
            "merged_debug": {
                "assigned_values": {},
                "parse_errors": [],
                "parse_warnings": [],
                "rollability": "non_target",
                "unsupported_trait": unsupported_hint,
                "autoskip_logged": True,
            },
            "source_text": text,
            "source_name": source_name,
            "has_marker": True,
            "rollable_non_target": True,
            "best_quality": 60,
        }
        self._record_ocr_candidate_debug(result, "stat_only_non_target_fast_loop")
        return result

    def _non_target_cache_key(self, candidates):
        try:
            first = candidates[0] if candidates else None
            if not first:
                return None
            _engine, text, _raw_text = self._unpack_ocr_candidate(first)
            region = tuple(self.cfg["STATS_REGION"])
            signature = getattr(self, "_last_stats_ocr_signature", None)
            if signature is None:
                return None
            return (region, signature, normalize_text(text))
        except Exception:
            return None

    def _cached_non_target_result(self, candidates):
        key = self._non_target_cache_key(candidates)
        if not key:
            return None
        cached = self._last_non_target_decision_cache or {}
        if cached.get("key") != key:
            return None
        if time.time() - float(cached.get("time", 0.0)) > 2.0:
            return None
        result = cached.get("result")
        if not result:
            return None
        self.log("Specs fast-loop cached_non_target | fallback=skipped")
        self._record_ocr_candidate_debug(result, "cached_non_target")
        return result

    def _store_non_target_cache(self, candidates, parsed):
        if not (parsed or {}).get("rollable_non_target"):
            return
        key = self._non_target_cache_key(candidates)
        if not key:
            return
        self._last_non_target_decision_cache = {
            "key": key,
            "time": time.time(),
            "result": dict(parsed),
        }

    def _power_candidate_quality(self, power_key, values, text, passive=None):
        found = sum(value is not None for value in values.values())
        marker = 1 if self.has_current_spec_marker(text) else 0
        numbers = len(re.findall(r"\d+(?:\.\d+)?", text or ""))
        passive_bonus = 8 if passive and passive.get("detected") else 0
        return (found * 24) + (marker * 10) + numbers + passive_bonus + (15 if power_key else 0)

    def _parse_power_candidates(self, candidates):
        unpacked = [self._unpack_ocr_candidate(candidate) for candidate in candidates]
        usable = [(engine, text, raw_text) for engine, text, raw_text in unpacked if text and text.strip()]
        best_supported = None
        fallback_text = ""
        for engine, text, raw_text in usable:
            combined = f"{text}\n{raw_text}"
            parsed = parse_power_roll_text(combined)
            if not parsed:
                if not fallback_text and (self.has_current_spec_marker(combined) or len(re.findall(r"[a-zA-Z]", combined)) >= 8):
                    fallback_text = combined
                continue
            power_key = parsed["power"]
            values = parsed["values"]
            passive = parsed.get("passive")
            quality = self._power_candidate_quality(power_key, values, combined, passive)
            candidate = {
                "engine": engine,
                "power": power_key,
                "power_name": parsed.get("power_name"),
                "text": combined,
                "values": values,
                "parsed_stats": parsed.get("parsed_stats", values),
                "passive": passive,
                "passive_family": parsed.get("passive_family"),
                "passive_family_key": parsed.get("passive_family_key"),
                "passive_value": parsed.get("passive_value"),
                "passive_duration": parsed.get("passive_duration"),
                "passive_duration_seconds": parsed.get("passive_duration_seconds"),
                "passive_detected": parsed.get("passive_detected"),
                "passive_fragment": parsed.get("passive_fragment"),
                "passive_numeric_range": parsed.get("passive_numeric_range"),
                "passive_notes": parsed.get("passive_notes"),
                "quality": quality,
            }
            if best_supported is None or candidate["quality"] > best_supported["quality"]:
                best_supported = candidate
        return best_supported, fallback_text

    def _power_assigned_values(self, power_key, values, passive=None):
        assigned = {stat.label: values.get(stat.key) for stat in SUPPORTED_POWER_DEFINITIONS[power_key].stats}
        if passive and passive.get("detected"):
            assigned["Passive"] = passive.get("family_label") or passive.get("family_key")
            if passive.get("value") is not None:
                assigned["Passive Value"] = passive.get("value")
            if passive.get("duration_seconds") is not None:
                assigned["Passive Duration"] = passive.get("duration_seconds")
            if passive.get("fragment"):
                assigned["Passive Fragment"] = passive.get("fragment")
        return assigned

    def evaluate_power_trait_with_values(self, power_key, values, text, source_name="merged", passive=None):
        summary = summarize_power_values(power_key, values, passive=passive)
        assigned = self._power_assigned_values(power_key, values, passive)
        quality = self._power_candidate_quality(power_key, values, text, passive)
        completeness = self._power_parse_completeness(power_key, values, passive)

        if power_key not in self.enabled_powers:
            self.log(
                f"AUTOSKIP Power | trait={power_display_name(power_key)} | "
                f"reason=autoskip_power_not_listed | source={source_name} | quality={quality}"
            )
            self.record_decision_chain(
                subsystem="Classification",
                classification="NON_TARGET",
                classification_reason="autoskip_power_not_listed",
                current_trait=power_display_name(power_key),
                parsed_values=assigned,
                summary="Power is not enabled in the listed Mythicals; letting Auto continue",
                power_candidate_source=source_name,
                power_candidate_quality=quality,
                power_parse_coherent=completeness["coherent"],
                power_required_values=completeness["required_values"],
            )
            return (
                "NON_TARGET",
                "non_target_power",
                "Power is not enabled in the listed Mythicals; letting Auto continue",
                text,
                ["Autoskip power"],
                False,
            )

        if not completeness["coherent"]:
            self.log(
                f"POWER BAD gate deferred | trait={power_display_name(power_key)} | source={source_name} | "
                f"quality={quality} | required={completeness['required_present']}/{completeness['required_total']} | "
                f"missing_required={', '.join(completeness['missing_required']) or 'none'}"
            )
            self.record_decision_chain(
                subsystem="Classification",
                classification="ROLLING",
                classification_reason="supported power parse incomplete; manual reroll deferred",
                current_trait=power_display_name(power_key),
                parsed_values=assigned,
                summary=summary,
                power_candidate_source=source_name,
                power_candidate_quality=quality,
                power_parse_coherent=False,
                power_required_values=completeness["required_values"],
                missing_required=list(completeness["missing_required"]),
            )
            return "ROLLING", None, "", text, [], False

        matched, missing = evaluate_power(power_key, values, self.power_rules, passive=passive)
        score = power_score(power_key, values, self.power_rules, passive=passive)
        self.log(
            f"OCR threshold comparison ({source_name}) | assigned={assigned} | "
            f"targets={self.power_rules[power_key]} | quality={quality} | "
            f"required={completeness['required_values']}"
        )
        self.log(f"Found {power_display_name(power_key).upper()} ({source_name}) | Score {score:.2f} | {summary}")

        if not missing:
            self.log(f"KEEP {power_display_name(power_key).upper()} | {summary}")
            self.record_decision_chain(
                subsystem="Classification",
                classification="GOD",
                classification_reason="all configured required power targets met",
                current_trait=power_display_name(power_key),
                parsed_values=assigned,
                summary=summary,
                score=score,
                power_candidate_source=source_name,
                power_candidate_quality=quality,
                power_parse_coherent=True,
                power_required_values=completeness["required_values"],
            )
            return "GOD", power_key, summary, text, list(missing), False

        near = power_near_miss(power_key, values, self.power_rules, passive=passive)
        high_value = score >= float(self.cfg.get("HIGH_VALUE_STOP_SCORE", 99.5))
        if near:
            self.log(f"Near miss detected | {power_display_name(power_key).upper()} | Score {score:.2f} | {summary}")
        if high_value:
            self.log(f"High-value early stop | {power_display_name(power_key).upper()} | Score {score:.2f}")
            self.record_decision_chain(
                subsystem="Classification",
                classification="HIGH_VALUE",
                classification_reason=f"score {score:.2f} >= high-value threshold",
                current_trait=power_display_name(power_key),
                parsed_values=assigned,
                summary=summary,
                missing=list(missing),
                score=score,
                power_candidate_source=source_name,
                power_candidate_quality=quality,
                power_parse_coherent=True,
                power_required_values=completeness["required_values"],
            )
            return "HIGH_VALUE", power_key, summary, text, [f"Score {score:.2f}"] + list(missing), True

        self.log(f"SKIP {power_display_name(power_key).upper()} | {' ; '.join(missing) if missing else 'Required targets not met'}")
        self.log(
            f"Power BAD configured miss | trait={power_display_name(power_key)} | "
            f"missing={' ; '.join(missing) if missing else 'Required targets not met'} | "
            f"source={source_name} | quality={quality} | required={completeness['required_values']}"
        )
        self.record_decision_chain(
            subsystem="Classification",
            classification="BAD",
            classification_reason="configured power targets not met",
            current_trait=power_display_name(power_key),
            parsed_values=assigned,
            summary=summary,
            missing=list(missing),
            score=score,
            near_miss=bool(near),
            power_candidate_source=source_name,
            power_candidate_quality=quality,
            power_parse_coherent=True,
            power_required_values=completeness["required_values"],
        )
        return "BAD", power_key, summary, text, list(missing), near

    def check_power_roll(self, allow_fallback=True, startup_fast=False):
        started = time.perf_counter()
        candidates = []
        fallback_text = ""
        primary_route = "startup_fast" if startup_fast else "fast_loop"
        fast_candidates = self.get_stats_ocr_candidates(
            startup_fast=startup_fast,
            fast_loop=not startup_fast,
        )
        candidates.extend(fast_candidates)
        parsed, fallback_text = self._parse_power_candidates(candidates)
        fallback_reason = ""

        if parsed:
            completeness = self._power_parse_completeness(
                parsed["power"],
                parsed["values"],
                parsed.get("passive"),
            )
            enabled_power = parsed["power"] in self.enabled_powers
            if completeness["coherent"] or not enabled_power or not allow_fallback:
                self._record_timing_event(
                    "check_roll",
                    time.perf_counter() - started,
                    domain="powers",
                    route=primary_route,
                    fallback="skipped",
                    power=parsed["power"],
                    coherent=bool(completeness["coherent"]),
                )
                return self.evaluate_power_trait_with_values(
                    parsed["power"],
                    parsed["values"],
                    parsed["text"],
                    source_name=parsed["engine"],
                    passive=parsed.get("passive"),
                )
            fallback_reason = "enabled_power_parse_incomplete"
        elif fallback_text:
            self.log(
                "AUTOSKIP Power | trait=unsupported_or_filler | reason=autoskip_power_not_listed | "
                f"source={primary_route}"
            )
            self.record_decision_chain(
                subsystem="Classification",
                classification="NON_TARGET",
                classification_reason="autoskip_power_not_listed",
                current_trait="Non-target Power",
                parsed_values={},
                summary="Unsupported or filler power observed; letting Auto continue",
            )
            self._record_timing_event(
                "check_roll",
                time.perf_counter() - started,
                domain="powers",
                route=primary_route,
                fallback="skipped",
                power="unsupported_or_filler",
            )
            return "NON_TARGET", "non_target_power", "Unsupported or filler power observed; letting Auto continue", fallback_text, ["Non-target power"], False
        else:
            fallback_reason = "fast_power_parse_missing"

        if allow_fallback:
            primary_candidates = []
            if not startup_fast:
                primary_candidates = self.get_stats_ocr_candidates(startup_fast=False)
                if primary_candidates:
                    candidates = candidates + primary_candidates
                    parsed, fallback_text = self._parse_power_candidates(candidates)
                    if parsed:
                        completeness = self._power_parse_completeness(
                            parsed["power"],
                            parsed["values"],
                            parsed.get("passive"),
                        )
                        enabled_power = parsed["power"] in self.enabled_powers
                        if completeness["coherent"] or not enabled_power:
                            self.log(
                                "Power OCR fast-loop promoted to primary route | "
                                f"reason={fallback_reason} | power={power_display_name(parsed['power'])} | "
                                f"coherent={completeness['coherent']}"
                            )
                            self._record_timing_event(
                                "check_roll",
                                time.perf_counter() - started,
                                domain="powers",
                                route="primary_after_fast",
                                fallback="skipped",
                                power=parsed["power"],
                                coherent=bool(completeness["coherent"]),
                            )
                            return self.evaluate_power_trait_with_values(
                                parsed["power"],
                                parsed["values"],
                                parsed["text"],
                                source_name=parsed["engine"],
                                passive=parsed.get("passive"),
                            )
                        fallback_reason = "primary_power_parse_incomplete"
            fallback_candidates = self.get_stats_ocr_candidates(fallback_only=True)
            if fallback_candidates:
                candidates = candidates + fallback_candidates
                parsed, fallback_text = self._parse_power_candidates(candidates)
                if parsed:
                    self.log(
                        "Power OCR fallback used | "
                        f"reason={fallback_reason or 'fast_parse_not_coherent'} | "
                        f"power={power_display_name(parsed['power'])}"
                    )

        if not parsed:
            if fallback_text:
                self.log("AUTOSKIP Power | trait=unsupported_or_filler | reason=autoskip_power_not_listed | source=ocr_fallback")
                self.record_decision_chain(
                    subsystem="Classification",
                    classification="NON_TARGET",
                    classification_reason="autoskip_power_not_listed",
                    current_trait="Non-target Power",
                    parsed_values={},
                    summary="Unsupported or filler power observed; letting Auto continue",
                )
                self._record_timing_event(
                    "check_roll",
                    time.perf_counter() - started,
                    domain="powers",
                    route="fallback",
                    fallback="used",
                    power="unsupported_or_filler",
                )
                return "NON_TARGET", "non_target_power", "Unsupported or filler power observed; letting Auto continue", fallback_text, ["Non-target power"], False
            self.record_decision_chain(
                subsystem="Classification",
                classification="ROLLING",
                classification_reason="supported power not detected from OCR",
                current_trait="none",
                parsed_values={},
            )
            self._record_timing_event(
                "check_roll",
                time.perf_counter() - started,
                domain="powers",
                route="fallback" if allow_fallback else primary_route,
                fallback="used" if allow_fallback else "disabled",
                power="none",
            )
            return "ROLLING", None, "", "", [], False

        self._record_timing_event(
            "check_roll",
            time.perf_counter() - started,
            domain="powers",
            route="fallback" if allow_fallback else primary_route,
            fallback="used" if allow_fallback else "disabled",
            power=parsed["power"],
        )
        return self.evaluate_power_trait_with_values(
            parsed["power"],
            parsed["values"],
            parsed["text"],
            source_name=parsed["engine"],
            passive=parsed.get("passive"),
        )

    def _evaluate_spec_parsed_roll(self, parsed):
        trait = parsed["trait"]
        last_text = parsed["last_text"]
        if not trait:
            self.record_decision_chain(
                subsystem="Classification",
                classification="ROLLING",
                classification_reason="trait not detected or OCR fragment rejected",
                current_trait="none",
                parsed_values={},
            )
            return "ROLLING", None, "", last_text, [], False

        merged_vals = parsed["merged_values"]
        merged_confident = sum(v is not None for v in merged_vals)

        if self.cfg.get("REQUIRE_CURRENT_SPEC", True):
            marker_found = bool(parsed["has_marker"])
            if not marker_found:
                marker_found, marker_text = self.read_current_spec_marker()
                if marker_found:
                    parsed["has_marker"] = True
                    parsed["merged_debug"]["marker_source"] = marker_text

            details = self._structured_markerless_read_details(parsed)
            self.log(
                "CURRENT SPEC gate | "
                f"trait={trait or 'none'} | "
                f"labels={details['label_count']} | "
                f"values={merged_confident} | "
                f"quality={details['quality']:g} | "
                f"marker={'yes' if parsed['has_marker'] else 'no'}"
            )
            if not parsed["has_marker"]:
                if details["accepted"]:
                    self.log(
                        "Marker missing but structured read accepted | "
                        f"trait={trait} labels={details['label_count']} quality={details['quality']:g}"
                    )
                    if details["missing_labels"]:
                        self.log(f"Partial structured read accepted | missing={', '.join(details['missing_labels'])}")
                else:
                    self.log(
                        "Marker missing and structured read rejected | "
                        f"trait={trait} labels={details['label_count']} quality={details['quality']:g} | "
                        f"{details['reason']}"
                    )
                    self.log("Ignored OCR because CURRENT SPEC was not detected")
                    self.record_decision_chain(
                        subsystem="Classification",
                        classification="ROLLING",
                        classification_reason=f"marker missing and insufficient structure: {details['reason']}",
                        current_trait=display_trait(trait),
                        parsed_values=parsed["merged_debug"].get("assigned_values", {}),
                    )
                    return "ROLLING", None, "", last_text, [], False

        if parsed.get("rollable_non_target") or not self.is_target_trait(trait):
            return self.evaluate_rollable_non_target_trait(
                trait,
                parsed["source_text"],
                source_name=parsed["source_name"],
                parse_debug=parsed["merged_debug"],
            )

        target_details = self._structured_markerless_read_details(parsed)
        if not target_details["accepted"]:
            self.log(
                "Weak target trait OCR rejected before mythical/manual classification | "
                f"trait={trait} labels={target_details['label_count']} values={target_details['value_count']} "
                f"quality={target_details['quality']:g} | {target_details['reason']}"
            )
            self.record_decision_chain(
                subsystem="Classification",
                classification="ROLLING",
                classification_reason=f"weak target OCR rejected before classification: {target_details['reason']}",
                current_trait=display_trait(trait),
                parsed_values=parsed["merged_debug"].get("assigned_values", {}),
            )
            return "ROLLING", None, "", last_text, [], False

        return self.evaluate_trait_with_values(
            trait,
            merged_vals,
            parsed["source_text"],
            source_name=parsed["source_name"],
            parse_debug=parsed["merged_debug"],
        )

    def check_roll(self, allow_fallback=True, startup_fast=False):
        if self.roll_domain == "powers":
            return self.check_power_roll(allow_fallback=allow_fallback, startup_fast=startup_fast)
        started = time.perf_counter()

        bad_panel_words = [
            "mythical 0.2",
            "fortune chosen > 17.5",
            "executioner > 30",
            "rampage > 15",
            "the more times you do dmg",
            "resets after 5s",
        ]

        route = "startup_fast" if startup_fast else "spec_fast_loop"
        fallback_used = False
        candidates = self.get_stats_ocr_candidates(startup_fast=startup_fast, fast_loop=not startup_fast)
        cached = self._cached_non_target_result(candidates)
        if cached:
            self._record_timing_event(
                "check_roll",
                time.perf_counter() - started,
                domain="specs",
                route="cached_non_target",
                fallback="skipped",
            )
            return self._evaluate_spec_parsed_roll(cached)

        parsed = self._parse_stat_ocr_candidates(candidates, bad_panel_words)
        if not parsed.get("trait"):
            stat_only = self._stat_only_non_target_result_from_parsed(parsed, source_name=route)
            if stat_only:
                self._store_non_target_cache(candidates, stat_only)
                self._record_timing_event(
                    "check_roll",
                    time.perf_counter() - started,
                    domain="specs",
                    route=route,
                    fallback="skipped",
                    classification="NON_TARGET",
                )
                return self._evaluate_spec_parsed_roll(stat_only)

        if parsed.get("rollable_non_target"):
            self._store_non_target_cache(candidates, parsed)
            self._record_timing_event(
                "check_roll",
                time.perf_counter() - started,
                domain="specs",
                route=route,
                fallback="skipped",
                classification="NON_TARGET",
            )
            return self._evaluate_spec_parsed_roll(parsed)

        if parsed.get("trait") and not self._parsed_needs_fallback(parsed):
            self._record_timing_event(
                "check_roll",
                time.perf_counter() - started,
                domain="specs",
                route=route,
                fallback="skipped",
                trait=parsed.get("trait"),
            )
            return self._evaluate_spec_parsed_roll(parsed)

        if allow_fallback and self._parsed_needs_fallback(parsed):
            primary_candidates = []
            if not startup_fast:
                primary_candidates = self.get_stats_ocr_candidates(startup_fast=False)
                if primary_candidates:
                    candidates = candidates + primary_candidates
                    parsed = self._parse_stat_ocr_candidates(candidates, bad_panel_words)
                    if parsed.get("rollable_non_target"):
                        self._store_non_target_cache(candidates, parsed)
                        self._record_timing_event(
                            "check_roll",
                            time.perf_counter() - started,
                            domain="specs",
                            route="primary_after_fast",
                            fallback="skipped",
                            classification="NON_TARGET",
                        )
                        return self._evaluate_spec_parsed_roll(parsed)
                    if parsed.get("trait") and not self._parsed_needs_fallback(parsed):
                        self.log(
                            "Specs OCR fast-loop promoted to primary route | "
                            f"trait={display_trait(parsed.get('trait'))}"
                        )
                        self._record_timing_event(
                            "check_roll",
                            time.perf_counter() - started,
                            domain="specs",
                            route="primary_after_fast",
                            fallback="skipped",
                            trait=parsed.get("trait"),
                        )
                        return self._evaluate_spec_parsed_roll(parsed)
            if self._parsed_needs_fallback(parsed):
                fallback_candidates = self.get_stats_ocr_candidates(fallback_only=True)
                if fallback_candidates:
                    fallback_used = True
                    candidates = candidates + fallback_candidates
                    parsed = self._parse_stat_ocr_candidates(candidates, bad_panel_words)
                    self.log(
                        "Specs OCR fallback used | "
                        f"trait={display_trait(parsed.get('trait')) if parsed.get('trait') else 'none'}"
                    )
        if self._parsed_needs_fallback(parsed):
            parsed = self._confirm_partial_target_read(parsed, bad_panel_words)
        if parsed.get("rollable_non_target"):
            self._store_non_target_cache(candidates, parsed)
        self._record_timing_event(
            "check_roll",
            time.perf_counter() - started,
            domain="specs",
            route="fallback" if fallback_used else route,
            fallback="used" if fallback_used else "skipped",
            trait=parsed.get("trait") or "none",
        )
        return self._evaluate_spec_parsed_roll(parsed)

    def passive_shard_region_enabled(self):
        region = self.cfg.get("PASSIVE_SHARD_REGION") or (0, 0, 0, 0)
        try:
            return len(region) == 4 and int(region[2]) > 0 and int(region[3]) > 0
        except Exception:
            return False

    def extract_passive_shards(self, text):
        value, _normalized = parse_passive_shard_count(text, self.last_passive_shards)
        return value

    def _passive_shard_bucket(self, count):
        if count is None:
            return "unknown"
        empty = int(self.cfg.get("PASSIVE_SHARD_EMPTY_THRESHOLD", 0))
        critical = int(self.cfg.get("PASSIVE_SHARD_CRITICAL_THRESHOLD", 1000))
        very_low = int(self.cfg.get("PASSIVE_SHARD_VERY_LOW_THRESHOLD", 5000))
        low = int(self.cfg.get("PASSIVE_SHARD_LOW_THRESHOLD", 10000))
        if count <= empty:
            return "empty"
        if count <= critical:
            return "critical"
        if count <= very_low:
            return "very_low"
        if count <= low:
            return "low"
        return "normal"

    def _passive_bucket_rank(self, bucket):
        return {
            "unknown": -1,
            "normal": 0,
            "low": 1,
            "very_low": 2,
            "critical": 3,
            "empty": 4,
        }.get(bucket, -1)

    def _update_passive_shard_session(self, count):
        if count is None:
            return
        if self.session_start_passive_shards is None:
            self.session_start_passive_shards = count
            self.log(f"Passive shard session start | value={format_shard_count(count)}")
        self.session_latest_passive_shards = count

    def passive_shard_usage_summary(self):
        start = self.session_start_passive_shards
        current = self.session_latest_passive_shards
        if start is None or current is None:
            return "Shard usage: unknown"
        consumed = max(0, int(start) - int(current))
        hours = (time.time() - self.session_started_at) / 3600.0 if self.session_started_at else 0.0
        rate = consumed / hours if hours > 0.01 else 0.0
        return (
            "Shard usage: "
            f"start={format_shard_count(start)}, "
            f"current={format_shard_count(current)}, "
            f"consumed={format_shard_count(consumed)}, "
            f"burn_rate={format_shard_count(int(rate))}/hr"
        )

    def _passive_shard_zero_evidence(self, attempt, attempts=None):
        parsed = attempt.get("parsed")
        try:
            parsed = int(parsed)
        except Exception:
            return False, "not zero"
        if parsed != 0:
            return True, "nonzero"

        raw = str(attempt.get("raw") or "")
        normalized = str(attempt.get("normalized") or "")
        raw_clean = normalize_ocr_text(raw).replace(" ", "")
        raw_lower = normalize_ocr_text(raw)
        explicit_zero = bool(re.search(r"\b0(?:\.0+)?\b", normalized))
        separated_zero_with_shards = bool(
            re.search(r"(?:(?:passive|power)\s*shards?|shards?)\s*[:=]?\s*0(?:\.0+)?\b", raw_lower)
            or re.search(r"\b0(?:\.0+)?\s+(?:(?:passive|power)\s*)?shards?\b", raw_lower)
            or re.fullmatch(r"\s*0(?:\.0+)?\s*", raw_lower)
        )
        garbage_like = raw_clean in {"opassiveshards", "0passiveshards", "passiveshards", "opowershards", "0powershards", "powershards"} or (
            normalized == "0" and not separated_zero_with_shards
        )
        if garbage_like or not explicit_zero:
            return False, "suspicious zero from weak OCR"

        if separated_zero_with_shards:
            return True, "strong explicit zero"

        if self.last_passive_shards is not None and self.last_passive_shards <= max(5, int(self.cfg.get("PASSIVE_SHARD_EMPTY_THRESHOLD", 0)) + 5):
            return True, "zero consistent with prior near-empty value"

        consistent = 0
        for item in attempts or []:
            try:
                if int(item.get("parsed")) == 0 and re.search(r"\b0(?:\.0+)?\b", str(item.get("normalized") or "")):
                    other_raw = normalize_ocr_text(item.get("raw") or "")
                    if (
                        re.search(r"(?:(?:passive|power)\s*shards?|shards?)\s*[:=]?\s*0(?:\.0+)?\b", other_raw)
                        or re.search(r"\b0(?:\.0+)?\s+(?:(?:passive|power)\s*)?shards?\b", other_raw)
                        or re.fullmatch(r"\s*0(?:\.0+)?\s*", other_raw)
                    ):
                        consistent += 1
            except Exception:
                continue
        if consistent >= 2:
            return True, "multiple strong zero attempts"

        return False, "suspicious zero lacks confirmation"

    def _passive_shard_alert_due(self, bucket, now=None):
        if bucket in ("unknown", "normal"):
            return False
        now = time.time() if now is None else now
        cooldown = max(60, int(self.cfg.get("PASSIVE_SHARD_ALERT_COOLDOWN", 1800)))
        previous = self.last_passive_shard_bucket
        if self._passive_bucket_rank(bucket) > self._passive_bucket_rank(previous):
            return True
        last = self.last_passive_shard_bucket_alert.get(bucket, 0.0)
        return now - last >= cooldown

    def _emit_passive_shard_threshold_alert(self, count, bucket):
        if bucket in ("unknown", "normal"):
            self.last_passive_shard_bucket = bucket
            return False
        now = time.time()
        if not self._passive_shard_alert_due(bucket, now):
            self.log(f"Passive shard {bucket} alert suppressed by cooldown | value={compact_shard_count(count)}")
            self.last_passive_shard_bucket = bucket
            return False

        label = {
            "low": "low",
            "very_low": "very low",
            "critical": "critically low",
            "empty": "empty",
        }.get(bucket, bucket)
        self.log(f"Passive shards {label} | value={compact_shard_count(count)}")
        self.last_important_event = f"Passive shards {label}: {compact_shard_count(count)}"
        title = "Passive Shards Empty" if bucket == "empty" else f"Passive Shards {label.title()}"
        body = self._discord_message(
            title,
            fields=[
                ("Status", label),
                ("Value", format_shard_count(count)),
                ("Session", self.passive_shard_usage_summary()),
                ("Uptime", self._format_uptime()),
            ],
        )
        self.send_webhook_alert(
            f"passive_shards_{bucket}",
            title,
            body,
            critical=bucket in ("critical", "empty"),
            dedup=True,
        )
        self.last_passive_shard_bucket_alert[bucket] = now
        self.last_passive_shard_bucket = bucket
        return True

    def passive_shards_empty_confirmed(self, count):
        if count is None:
            if self._empty_check_active:
                self.log("Passive shard empty condition not confirmed after low/suspicious evidence")
            return False
        empty = int(self.cfg.get("PASSIVE_SHARD_EMPTY_THRESHOLD", 0))
        if count <= empty:
            chosen = (self.last_shard_ocr_state or {}).get("chosen") or {}
            if chosen:
                strong, reason = self._passive_shard_zero_evidence(chosen, (self.last_shard_ocr_state or {}).get("attempts") or [])
                if strong:
                    self.log(f"Passive shard empty confirmed from strong evidence | {reason}")
                    return True
                self.log(f"Passive shard empty condition not confirmed after low/suspicious evidence | keeping previous valid value | {reason}")
                return False
            self.log("Passive shard empty condition not confirmed after low/suspicious evidence | no OCR evidence available")
            return False
        confirmed = False
        if not confirmed and self._empty_check_active:
            self.log("Passive shard empty condition not confirmed after low/suspicious evidence")
        return confirmed

    def should_check_passive_shards_empty(self, count):
        self._empty_check_active = False
        if not self.cfg.get("STOP_ON_EMPTY_PASSIVE_SHARDS", True):
            return False
        empty = int(self.cfg.get("PASSIVE_SHARD_EMPTY_THRESHOLD", 0))
        critical = int(self.cfg.get("PASSIVE_SHARD_CRITICAL_THRESHOLD", 1000))
        low = int(self.cfg.get("PASSIVE_SHARD_LOW_THRESHOLD", 10000))
        near_threshold = max(empty, critical, low)
        trusted = self.last_passive_shards if self.last_passive_shards is not None else self.session_latest_passive_shards
        chosen = (self.last_shard_ocr_state or {}).get("chosen") or {}
        chosen_value = chosen.get("parsed")
        try:
            chosen_value = int(chosen_value) if chosen_value is not None else None
        except Exception:
            chosen_value = None
        suspicious_zero = chosen_value == 0 or "suspicious zero" in str(chosen.get("reason") or "").lower()

        if count is not None and count <= near_threshold:
            self._empty_check_active = True
            self.log(f"Passive shard empty check triggered | latest value={count}")
            return True
        if trusted is not None and trusted > near_threshold and (count is None or count > near_threshold):
            now = time.time()
            if now - self._last_empty_check_skip_log >= 60.0:
                self.log(f"Passive shard empty check skipped | healthy trusted value={trusted}")
                self._last_empty_check_skip_log = now
            return False
        if chosen_value is not None and chosen_value <= near_threshold:
            self._empty_check_active = True
            self.log("Passive shard empty check triggered | suspicious low OCR candidate")
            return True
        if suspicious_zero:
            self._empty_check_active = True
            self.log("Passive shard empty check triggered | suspicious zero OCR candidate")
            return True
        if trusted is None and count is None:
            return False
        return count is not None

    def _expanded_region(self, region, padding=4):
        x, y, width, height = [int(part) for part in region]
        padding = max(0, int(padding))
        x2 = max(0, x - padding)
        y2 = max(0, y - padding)
        return (x2, y2, width + (x - x2) + padding, height + (y - y2) + padding)

    def _shard_image_variants(self, img):
        _require_module("Pillow", ImageEnhance)
        variants = [("raw", img)]
        gray = self._upscale_for_tesseract(img.convert("L"), 3)
        contrast = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(2.0)
        threshold = contrast.point(lambda px: 255 if px > 140 else 0)
        variants.extend(
            [
                ("gray", gray),
                ("contrast", contrast),
                ("threshold", threshold),
            ]
        )
        return variants

    def _passive_shard_image_variants(self, img):
        return self._shard_image_variants(img)

    def passive_shard_ocr_attempts(self, image=None, region=None):
        _require_module("pyautogui", pyautogui)
        _require_module("pytesseract", pytesseract)
        region = tuple(region or self.cfg["PASSIVE_SHARD_REGION"])
        ocr_region = self._expanded_region(region, padding=4)
        img = image if image is not None else pyautogui.screenshot(region=ocr_region)
        attempts = []
        for mode, variant in self._shard_image_variants(img):
            for psm in (7, 6):
                try:
                    raw = self._ocr_tesseract_image(variant, psm)
                except Exception as e:
                    raw = f"<error: {e}>"
                parsed, normalized, candidate_type = _parse_passive_shard_count_detail(
                    "" if raw.startswith("<error:") else raw,
                    self.last_passive_shards,
                    infer_missing_suffix=True,
                )
                if candidate_type == "malformed_plain_count":
                    reason = "rejected malformed plain shard count"
                elif not normalized:
                    reason = "no normalized digits"
                elif parsed is None:
                    reason = "no valid shard count"
                else:
                    reason = "parsed"
                attempts.append(
                    {
                        "mode": mode,
                        "psm": psm,
                        "raw": raw,
                        "normalized": normalized,
                        "parsed": parsed,
                        "formatted": format_shard_count(parsed) if parsed is not None else "not found",
                        "reason": reason,
                        "candidate_type": candidate_type,
                    }
                )
        return {
            "region": region,
            "ocr_region": ocr_region,
            "image": img,
            "processed_image": preprocess_ocr_image(img, scale=3, threshold=True),
            "attempts": attempts,
        }

    def _best_passive_shard_attempt(self, attempts):
        valid = [attempt for attempt in attempts if attempt.get("parsed") is not None]
        if not valid:
            return None
        stable = []
        for attempt in valid:
            parsed = int(attempt["parsed"])
            normalized = str(attempt.get("normalized") or "")
            raw = str(attempt.get("raw") or "")
            if parsed < 0:
                attempt["reason"] = "rejected garbage: negative"
                continue
            if parsed > 100_000_000:
                attempt["reason"] = "rejected garbage: implausibly high"
                continue
            if not re.search(r"\d", normalized):
                attempt["reason"] = "rejected garbage: no digits"
                continue
            if parsed == 0:
                strong_zero, zero_reason = self._passive_shard_zero_evidence(attempt, valid)
                if not strong_zero:
                    attempt["reason"] = f"suspicious zero rejected: {zero_reason}"
                    continue
                attempt["reason"] = zero_reason
            if parsed <= 9 and not re.search(r"\b\d(?:\.0+)?\b", normalized):
                attempt["reason"] = "rejected garbage: malformed tiny value"
                continue
            attempt["parsed"] = parsed
            attempt["formatted"] = format_shard_count(parsed)
            stable.append(attempt)
        valid = stable
        if not valid:
            return None
        if self.last_passive_shards is not None:
            return min(valid, key=lambda item: abs(int(item["parsed"]) - int(self.last_passive_shards)))
        priority = {"threshold": 0, "contrast": 1, "gray": 2, "raw": 3}
        return min(valid, key=lambda item: (priority.get(item.get("mode"), 9), item.get("psm", 9), -int(item["parsed"])))

    def _passive_shard_offtarget_reason(self, attempts):
        if self.roll_domain != "powers":
            return ""
        raw_text = " ".join(str(attempt.get("raw") or "") for attempt in attempts or [])
        normalized = normalize_text(raw_text)
        if not normalized or re.search(r"\d", normalized):
            return ""
        roll_tokens = (
            "mythi",
            "mythic",
            "non target",
            "non-target",
            "power",
            "damage",
            "crit",
            "luck",
            "colossus",
            "cursebrand",
            "subjugator",
        )
        if any(token in normalized for token in roll_tokens):
            return "off_target_roll_text"
        return ""

    def read_passive_shards(self):
        if not self.passive_shard_region_enabled():
            if not self._passive_shard_region_warned:
                self.log("Passive shard region not set; shard reports are paused.")
                self._passive_shard_region_warned = True
            return None

        region = tuple(self.cfg["PASSIVE_SHARD_REGION"])
        now = time.time()
        if self.roll_domain == "powers" and now < float(self._passive_shard_backoff_until or 0.0):
            remaining = int(max(0.0, float(self._passive_shard_backoff_until or 0.0) - now))
            self._log_with_cooldown(
                "passive_shard_backoff_active",
                "Passive shard OCR skipped during Powers mode backoff | "
                f"reason={self._passive_shard_backoff_reason or 'recent failure'} | "
                f"remaining={remaining}s | keeping={format_shard_count(self.last_passive_shards) if self.last_passive_shards is not None else 'unknown'}",
                cooldown=10.0,
            )
            return self.last_passive_shards

        try:
            result = self.passive_shard_ocr_attempts(region=region)
        except Exception as e:
            self.log(f"Passive shard OCR failed | region={region} | error={e}")
            return None

        attempts = result["attempts"]
        self.log(f"Passive shard OCR region | configured={region} | used={result['ocr_region']}")
        best = self._best_passive_shard_attempt(attempts)
        for attempt in attempts:
            self.log(
                "Passive shard OCR | "
                f"mode={attempt['mode']} psm={attempt['psm']} | "
                f"raw={self._compact_debug_text(attempt['raw']) or '<empty>'} | "
                f"normalized={attempt['normalized'] or '<empty>'} | "
                f"parsed={attempt['formatted']} | candidate={attempt.get('candidate_type', 'none')} | "
                f"reason={attempt['reason']}"
            )

        self._write_ocr_debug_event(
            "passive_shard_ocr",
            {
                "region": list(region),
                "ocr_region": list(result["ocr_region"]),
                "attempts": attempts,
                "chosen": best,
                "previous_value": self.last_passive_shards,
                "infer_missing_suffix": True,
            },
        )
        self.last_shard_ocr_state = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "region": region,
            "ocr_region": result["ocr_region"],
            "chosen": best,
            "attempts": attempts,
            "previous_valid": self.last_passive_shards,
        }
        self.record_decision_chain(
            subsystem="Shards",
            shard_result=best.get("formatted") if best else "not found",
            shard_reason=best.get("reason") if best else "no valid shard count",
        )
        if best is not None:
            count = int(best["parsed"])
            self._passive_shard_backoff_until = 0.0
            self._passive_shard_backoff_reason = ""
            self.log(
                "Passive shard OCR accepted | "
                f"raw={self._compact_debug_text(best.get('raw')) or '<empty>'} | "
                f"normalized={best.get('normalized') or '<empty>'} | "
                f"parsed={count} ({compact_shard_count(count)}) | "
                f"candidate={best.get('candidate_type', 'unknown')} | "
                f"source={best['mode']} psm={best['psm']}"
            )
            self.last_passive_shards = count
            self._update_passive_shard_session(count)
            return count

        reasons = ", ".join(sorted({attempt["reason"] for attempt in attempts})) or "no attempts"
        if "suspicious zero" in reasons:
            self.log("Passive shard OCR suspicious zero rejected")
        off_target_reason = self._passive_shard_offtarget_reason(attempts)
        if off_target_reason:
            cooldown = min(180.0, max(45.0, float(self.cfg.get("PASSIVE_SHARD_REPORT_INTERVAL", 600)) / 4.0))
            self._passive_shard_backoff_until = time.time() + cooldown
            self._passive_shard_backoff_reason = off_target_reason
            self._log_with_cooldown(
                "passive_shard_offtarget_backoff",
                "Passive shard OCR appears pointed at roll text; backing off repeated reads | "
                f"reason={off_target_reason} | cooldown={int(cooldown)}s | region={region}",
                cooldown=10.0,
            )
        self.log(f"Passive shard OCR rejected as garbage or did not find a count | region={region} | reasons={reasons}")
        if self.last_passive_shards is not None:
            self.log(f"Passive shard OCR failed; keeping previous valid value {format_shard_count(self.last_passive_shards)}")
        return None

    def _webhook_url(self):
        return (self.cfg.get("WEBHOOK_URL", "") or "").strip()

    def _webhook_interval(self, key, default):
        try:
            return max(0, float(self.cfg.get(key, default)))
        except Exception:
            return float(default)

    def _format_uptime(self):
        if not self.session_started_at:
            return "0s"
        seconds = max(0, int(time.time() - self.session_started_at))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"

    def _active_target_summary(self, limit=4):
        if self.roll_domain == "powers":
            parts = []
            for key, definition in SUPPORTED_POWER_DEFINITIONS.items():
                if key not in self.enabled_powers:
                    continue
                configured = self.power_rules.get(key, [])
                targets = []
                for target, range_pair in zip(definition.rule_targets[:2], configured[:2]):
                    low = range_pair[0] if isinstance(range_pair, (list, tuple)) and range_pair else 0
                    targets.append(f"{target.label} >= {low:g}%")
                parts.append(f"{definition.name}: {', '.join(targets) if targets else 'enabled'}")
                if len(parts) >= limit:
                    break
            return "; ".join(parts) if parts else "No active targets"
        parts = []
        seen = set()
        for trait in ("fortune", "executioner", "rampage"):
            if trait == "fortune" and not ({"fortune", "chosen"} & self.enabled_specs):
                continue
            if trait != "fortune" and trait not in self.enabled_specs:
                continue
            display = display_trait(trait)
            if display in seen:
                continue
            seen.add(display)
            rules = self.rules.get(trait, [])
            stats = STAT_LABELS.get(trait, [])
            stat_bits = []
            for idx, rule in enumerate(rules[:2]):
                low = rule[0] if isinstance(rule, (list, tuple)) and rule else 0
                label = stats[idx] if idx < len(stats) else f"Stat {idx + 1}"
                stat_bits.append(f"{label} >= {low:g}%")
            parts.append(f"{display}: {', '.join(stat_bits)}")
            if len(parts) >= limit:
                break
        return "; ".join(parts) if parts else "No active targets"

    def _format_live_status(self, state="running", reason=""):
        passive_shard_text = (
            format_shard_count(self.session_latest_passive_shards)
            if self.session_latest_passive_shards is not None
            else "unknown"
        )
        power_shard_text = (
            format_shard_count(self.session_latest_power_shards)
            if self.session_latest_power_shards is not None
            else "unknown"
        )
        trait_text = display_trait(self.last_trait_seen) if self.last_trait_seen else "unknown"
        fields = [
            ("State", state),
            ("Uptime", self._format_uptime()),
            ("Recoveries", self.session_recovery_count),
            ("Last trait/spec", trait_text),
            ("Passive shards", passive_shard_text),
            ("Passive shard session", self.passive_shard_usage_summary()),
            ("Power shards", power_shard_text),
            ("Power shard session", self.power_shard_usage_summary()),
            ("Finds", f"God {self.session_god_rolls} | Near miss {self.session_near_misses}"),
            ("Targets", self._active_target_summary()),
            ("Last event", self.last_important_event),
        ]
        if reason:
            fields.append(("Reason", reason))
        fields.append(("Updated", time.strftime("%Y-%m-%d %H:%M:%S")))
        return self._discord_message("Live Run Status", fields)

    def _discord_message(self, title, fields=None, intro="", footer=""):
        lines = [f"{APP_DISPLAY_NAME} | {title}", "-" * 40]
        if intro:
            lines.extend([str(intro).strip(), ""])
        if fields:
            for key, value in fields:
                if value is None or value == "":
                    value = "unknown"
                value_text = str(value).strip()
                if "\n" in value_text:
                    lines.append(f"{key}:")
                    lines.extend(f"  {part}" for part in value_text.splitlines())
                else:
                    lines.append(f"{key}: {value_text}")
        if footer:
            if fields:
                lines.append("")
            lines.append(str(footer).strip())
        return "\n".join(lines).strip()

    def _format_near_miss_number(self, value):
        try:
            return f"{float(value):g}"
        except Exception:
            text = str(value or "").strip()
            return text or "?"

    def _format_near_miss_range(self, low, high):
        return f"{self._format_near_miss_number(low)}-{self._format_near_miss_number(high)}"

    def _parse_near_miss_detail(self, miss_text, distance=""):
        detail = {
            "label": str(miss_text or "Target").split(":", 1)[0].split("|", 1)[0].strip() or "Target",
            "rolled": "not read",
            "needed": "configured target",
            "gap": distance or "near target",
        }
        for piece in re.split(r"\s*\|\s*", str(miss_text or "")):
            match = re.match(
                r"\s*(?P<label>[^:]+):\s*(?P<rolled>not found|[-+]?\d+(?:\.\d+)?)\s*->\s*"
                r"(?P<low>[-+]?\d+(?:\.\d+)?)\s*-\s*(?P<high>[-+]?\d+(?:\.\d+)?)",
                piece,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            label = match.group("label").strip()
            rolled_text = match.group("rolled").strip()
            low = float(match.group("low"))
            high = float(match.group("high"))
            gap = "not read"
            if rolled_text.lower() != "not found":
                rolled = float(rolled_text)
                if rolled < low:
                    gap = f"-{low - rolled:g}"
                elif rolled > high:
                    gap = f"+{rolled - high:g}"
                else:
                    gap = "0"
            return {
                "label": label,
                "rolled": rolled_text,
                "needed": self._format_near_miss_range(low, high),
                "gap": gap,
            }
        return detail

    def _near_miss_row_lines(self, rows):
        clean_rows = [(str(label).strip(), self._format_near_miss_number(value)) for label, value in rows if str(label).strip()]
        if not clean_rows:
            return ["Result          not read"]
        label_width = max(14, *(len(label) for label, _value in clean_rows))
        return [f"{label:<{label_width}} {value:>5}" for label, value in clean_rows]

    def _near_miss_spec_rows(self, trait, summary):
        labels = STAT_LABELS.get(trait, [])
        values = self.extract_labeled_values(trait, summary) if labels else []
        rows = []
        for index, label in enumerate(labels):
            value = values[index] if index < len(values) else None
            rows.append((label, "?" if value is None else value))
        return rows

    def _near_miss_power_rows(self, summary):
        rows = []
        for part in re.split(r"\s*\|\s*", str(summary or "")):
            text = part.strip()
            if not text:
                continue
            match = re.match(
                r"(?P<label>.+?)\s+"
                r"(?P<value>not found|\?|[-+]?\d+(?:\.\d+)?(?:\s+[-+]?\d+(?:\.\d+)?s|s)?)$",
                text,
                flags=re.IGNORECASE,
            )
            if match:
                label = re.sub(r"\s*\(optional\)", "", match.group("label").strip(), flags=re.IGNORECASE)
                rows.append((label, match.group("value").strip()))
            else:
                rows.append((text, "?"))
        return rows

    def _near_miss_stat_rows(self, trait, summary):
        if trait in SUPPORTED_POWER_DEFINITIONS:
            return self._near_miss_power_rows(summary)
        return self._near_miss_spec_rows(trait, summary)

    def _roll_kind_label(self, trait):
        return "Power" if trait in SUPPORTED_POWER_DEFINITIONS else "Spec"

    def _roll_stat_bullets(self, trait, summary):
        rows = self._near_miss_stat_rows(trait, summary)
        bullets = []
        for label, value in rows:
            label_text = str(label or "").strip()
            if not label_text:
                continue
            bullets.append(f"- {label_text}: {self._format_near_miss_number(value)}")
        if bullets:
            return bullets
        summary_text = str(summary or "").strip()
        return [f"- Raw roll: {summary_text or 'not read'}"]

    def _discord_session_bullets(self):
        lines = [
            f"- Uptime: {self._format_uptime()}",
            f"- Time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        ]
        if self.session_latest_passive_shards is not None:
            lines.append(f"- Passive shards: {format_shard_count(self.session_latest_passive_shards)}")
        if self.session_latest_power_shards is not None:
            lines.append(f"- Power shards: {format_shard_count(self.session_latest_power_shards)}")
        return lines

    def _roll_markdown_message(self, title, trait, summary, what_happened, target_lines, ocr_text=""):
        kind = self._roll_kind_label(trait)
        trait_name = display_trait(trait)
        lines = [
            f"# {title}",
            "",
            "## What happened",
            str(what_happened).strip(),
            "",
            "## Roll",
            f"- Type: {kind}",
            f"- {'Power' if kind == 'Power' else 'Trait'}: {trait_name}",
        ]
        lines.extend(self._roll_stat_bullets(trait, summary))
        lines.extend(["", "## Target check"])
        lines.extend(str(line).strip() for line in target_lines if str(line).strip())
        lines.extend(["", "## Session"])
        lines.extend(self._discord_session_bullets())
        ocr_excerpt = self._compact_debug_text(ocr_text or summary, 220)
        if ocr_excerpt:
            lines.extend(["", "## OCR", f"`{ocr_excerpt}`"])
        return "\n".join(lines).strip()

    def _near_miss_discord_body(self, trait, summary, miss_text, distance):
        trait_name = display_trait(trait)
        kind = self._roll_kind_label(trait)
        miss = self._parse_near_miss_detail(miss_text, distance)
        return self._roll_markdown_message(
            f"Kon. Near Miss - {kind}",
            trait,
            summary,
            f"{trait_name} was close to the configured target, but it did not fully qualify.",
            [
                f"- Status: Skipped",
                f"- Missed stat: {miss['label']}",
                f"- Rolled: {self._format_near_miss_number(miss['rolled'])}",
                f"- Needed: {miss['needed']}",
                f"- Gap: {miss['gap']}",
            ],
            ocr_text=summary,
        )

    def _webhook_should_send(self, key, window=None):
        if not key:
            return True
        now = time.time()
        if window is None:
            window = self._webhook_interval("WEBHOOK_DEDUP_WINDOW", 90)
        last = self._webhook_dedup.get(key, 0.0)
        if window > 0 and now - last < window:
            self.log(f"Discord update suppressed by dedup | key={key}")
            return False
        self._webhook_dedup[key] = now
        return True

    def _post_discord_text(self, content, wait=False, use_ping=True):
        url = self._webhook_url()
        if not url:
            self.log("Webhook not set, skipping Discord update")
            return False, None
        if requests is None:
            self.log("requests is not installed, skipping Discord update")
            return False, None

        ping = (self.cfg.get("PLAYER_PING", "") or "").strip()
        if use_ping and ping and not content.startswith(ping):
            content = f"{ping}\n{content}"

        try:
            payload = {
                "content": content,
                "allowed_mentions": {"parse": ["users", "roles"]},
            }
            params = {"wait": "true"} if wait else None
            r = requests.post(
                url,
                json=payload,
                params=params,
                timeout=15,
            )
            if 200 <= r.status_code < 300:
                self.log("Discord update sent successfully")
                message_id = None
                if wait:
                    try:
                        data = r.json()
                        message_id = str(data.get("id") or "") or None
                    except Exception:
                        message_id = None
                return True, message_id
            self.log(f"Discord update failed: {r.status_code} | {r.text[:150]}")
            return False, None
        except Exception as e:
            self.log(f"Discord update error: {e}")
            return False, None

    def send_discord_message(self, content, dedup_key=None, dedup_window=None, use_ping=True):
        if dedup_key and not self._webhook_should_send(dedup_key, dedup_window):
            return False
        ok, _message_id = self._post_discord_text(content, use_ping=use_ping)
        return ok

    def _live_status_edit_url(self):
        if not self.live_status_message_id:
            return ""
        base = self._webhook_url().split("?", 1)[0].rstrip("/")
        if not base:
            return ""
        return f"{base}/messages/{self.live_status_message_id}"

    def _patch_live_status(self, content):
        if requests is None:
            return False
        url = self._live_status_edit_url()
        if not url:
            return False
        try:
            payload = {
                "content": content,
                "allowed_mentions": {"parse": ["users", "roles"]},
            }
            r = requests.patch(url, json=payload, timeout=15)
            if 200 <= r.status_code < 300:
                self.log("Discord live status updated")
                return True
            self.log(f"Discord live status update failed: {r.status_code} | {r.text[:150]}")
            return False
        except Exception as e:
            self.log(f"Discord live status update error: {e}")
            return False

    def start_live_status(self):
        if not self.cfg.get("WEBHOOK_LIVE_STATUS_ENABLED", True):
            return False
        content = self._format_live_status("running")
        ok, message_id = self._post_discord_text(content, wait=True, use_ping=False)
        if ok and message_id:
            self.live_status_message_id = message_id
            self.live_status_can_edit = True
            self.last_status_update = time.time()
            self.log("Discord live status message created")
            return True
        if ok:
            self.live_status_can_edit = False
            self.last_status_update = time.time()
            self.log("Discord live status snapshot sent; message editing unavailable")
            return True
        return False

    def maybe_update_live_status(self, state="running", force=False, reason=""):
        if not self.cfg.get("WEBHOOK_LIVE_STATUS_ENABLED", True):
            return False
        if not self._webhook_url():
            return False
        interval = self._webhook_interval("WEBHOOK_STATUS_UPDATE_INTERVAL", 120)
        now = time.time()
        if not force and now - self.last_status_update < interval:
            return False

        content = self._format_live_status(state, reason)
        if self.live_status_can_edit and self._patch_live_status(content):
            self.last_status_update = now
            return True

        ok = self.send_discord_message(
            content,
            dedup_key="live_status_snapshot",
            dedup_window=max(interval * 0.75, 30),
            use_ping=False,
        )
        if ok:
            self.last_status_update = now
            self.log("Discord live status snapshot sent")
        return ok

    def finish_live_status(self, reason="Stopped"):
        if self.terminal_stop_reason:
            reason = self.terminal_stop_reason
        self.last_important_event = reason
        self.log(
            f"Session stop summary | {reason} | "
            f"{self.passive_shard_usage_summary()} | {self.power_shard_usage_summary()}"
        )
        self.maybe_update_live_status("stopped", force=True, reason=reason)

    def _send_discord_file(self, content, image_path, dedup_key=None, dedup_window=None, use_ping=True):
        if dedup_key and not self._webhook_should_send(dedup_key, dedup_window):
            return False
        url = self._webhook_url()
        if not url:
            self.log("Webhook not set, skipping Discord send")
            return False
        if requests is None:
            self.log("requests is not installed, skipping Discord send")
            return False

        ping = (self.cfg.get("PLAYER_PING", "") or "").strip()
        if use_ping and ping and not content.startswith(ping):
            content = f"{ping}\n{content}"

        sent = False
        try:
            payload = {
                "content": content,
                "allowed_mentions": {"parse": ["users", "roles"]},
            }
            with open(image_path, "rb") as f:
                r = requests.post(
                    url,
                    data={"payload_json": json.dumps(payload)},
                    files={"file": (os.path.basename(image_path), f, "image/png")},
                    timeout=15,
                )

            if 200 <= r.status_code < 300:
                self.log("Discord webhook sent successfully")
                sent = True
                return True

            self.log(f"Discord webhook failed: {r.status_code} | {r.text[:150]}")
            return False
        except Exception as e:
            self.log(f"Discord webhook error: {e}")
            return False
        finally:
            if sent and self.cfg.get("DELETE_SCREENSHOTS_AFTER_WEBHOOK", True):
                self.delete_capture(image_path)

    def send_webhook_alert(
        self,
        event_key,
        title,
        body,
        critical=False,
        attach_screenshot=False,
        screenshot_label="webhook_alert",
        dedup=True,
        use_ping=True,
        raw_content=False,
    ):
        body_text = str(body)
        raw_markdown = bool(raw_content) or body_text.startswith("# Kon. Near Miss")
        content = body_text if body_text.startswith(APP_DISPLAY_NAME) or raw_markdown else self._discord_message(title, footer=body_text)
        dedup_key = event_key if dedup and not critical else None
        if dedup_key and not self._webhook_should_send(dedup_key):
            return False
        if attach_screenshot:
            try:
                shot = self.capture_screen(screenshot_label)
            except Exception as e:
                self.log(f"Discord failure screenshot capture failed: {e}")
                shot = ""
            if shot:
                return self._send_discord_file(content, shot, use_ping=use_ping)
        return self.send_discord_message(content, use_ping=use_ping)

    def alert_popup_stuck(self, reason):
        body = (
            f"Popup remains after repeated Yes clicks.\n"
            f"Reason: {reason}\n"
            f"Uptime: {self._format_uptime()}\n"
            f"Last trait/spec: {display_trait(self.last_trait_seen) if self.last_trait_seen else 'unknown'}"
        )
        attach = bool(self.cfg.get("WEBHOOK_FAILURE_SCREENSHOTS", True)) and bool(
            self.cfg.get("WEBHOOK_SCREENSHOT_ON_POPUP_STUCK", True)
        )
        self.last_important_event = f"Popup stuck: {reason}"
        self._maybe_auto_capture_debug_snapshot("popup_stuck", extra={"reason": reason})
        self.send_webhook_alert(
            "popup_stuck",
            "Reroll Popup Stuck",
            self._discord_message(
                "Reroll Popup Stuck",
                fields=[
                    ("What happened", "Confirmation popup stayed visible after repeated Yes clicks"),
                    ("Reason", reason),
                    ("Uptime", self._format_uptime()),
                    ("Recoveries", self.session_recovery_count),
                    ("Last trait/spec", display_trait(self.last_trait_seen) if self.last_trait_seen else "unknown"),
                    ("Passive shards", format_shard_count(self.session_latest_passive_shards) if self.session_latest_passive_shards is not None else "unknown"),
                    ("Power shards", format_shard_count(self.session_latest_power_shards) if self.session_latest_power_shards is not None else "unknown"),
                ],
            ),
            attach_screenshot=attach,
            screenshot_label="popup_stuck",
            dedup=True,
        )

    def send_near_miss_alert(self, trait, summary, miss_text, distance):
        self.session_near_misses += 1
        self.last_trait_seen = trait or self.last_trait_seen
        self.last_important_event = f"Near miss: {display_trait(trait)}"
        body = self._near_miss_discord_body(trait, summary, miss_text, distance)
        key = f"near_miss:{trait}:{distance or miss_text}"
        self.log(f"Near miss Discord alert queued | format=v2_clean_markdown | trait={display_trait(trait)}")
        return self.send_webhook_alert(key, "Near Miss Found", body, dedup=True, use_ping=False, raw_content=True)

    def _send_passive_shard_standalone_update(self, count_text, reason="update"):
        ok = self.send_discord_message(
            self._discord_message(
                "Passive Shard Update",
                fields=[
                    ("Passive shards", count_text),
                    ("Reason", reason),
                    ("Uptime", self._format_uptime()),
                ],
            ),
            dedup_key=f"passive_shards_standalone:{count_text}:{reason}",
            dedup_window=60,
            use_ping=False,
        )
        if ok:
            self.log("Passive shard standalone Discord update sent")
        else:
            self.log("Passive shard standalone Discord update failed")
        return ok

    def maybe_report_passive_shards(self, force=False):
        alerts_enabled = self.cfg.get("PASSIVE_SHARD_ALERTS", True)
        if not alerts_enabled and not self.cfg.get("STOP_ON_EMPTY_PASSIVE_SHARDS", True):
            return None
        interval = max(60, int(self.cfg.get("PASSIVE_SHARD_REPORT_INTERVAL", 1200)))
        now = time.time()
        if not force and now - self.last_passive_shard_report < interval:
            return self.last_passive_shards

        count = self.read_passive_shards()
        if count is None:
            attempts = (self.last_shard_ocr_state or {}).get("attempts") or []
            reasons = ", ".join(sorted({str(attempt.get("reason") or "").strip() for attempt in attempts if str(attempt.get("reason") or "").strip()})) or "no valid shard count"
            if self.last_passive_shards is not None:
                self._log_with_cooldown(
                    f"passive_shard_report_skip:{reasons}",
                    "Passive shard report skipped: no valid shard count parsed; "
                    f"retaining previous valid value {format_shard_count(self.last_passive_shards)}.",
                    cooldown=60.0,
                )
                return self.last_passive_shards
            self._log_with_cooldown(
                f"passive_shard_report_skip:{reasons}",
                "Passive shard report skipped: no valid shard count parsed.",
                cooldown=60.0,
            )
            return None

        self.last_passive_shard_report = now
        count_text = format_shard_count(count)
        self.log(f"Passive shards: {count_text}")
        bucket = self._passive_shard_bucket(count)
        if alerts_enabled:
            self._emit_passive_shard_threshold_alert(count, bucket)
        changed = count != self.last_passive_shards_sent

        if bucket == "empty":
            self.last_passive_shards_sent = count
        elif alerts_enabled and self.cfg.get("WEBHOOK_LIVE_STATUS_ENABLED", True):
            if force or changed:
                self.last_important_event = f"Passive shards: {count_text}"
                if self.maybe_update_live_status(force=True):
                    self.log("Passive shard update applied to live status")
                    self.last_passive_shards_sent = count
                else:
                    self.log("Passive shard live status update failed; sending standalone fallback")
                    if self._send_passive_shard_standalone_update(count_text, reason="live status fallback"):
                        self.last_passive_shards_sent = count
            else:
                self.log("Passive shard count unchanged; Discord update skipped.")
        elif alerts_enabled and (force or changed):
            if self._send_passive_shard_standalone_update(count_text, reason="scheduled report"):
                self.last_passive_shards_sent = count
        elif alerts_enabled:
            self.log("Passive shard count unchanged; Discord update skipped.")
        return count

    def power_shard_region_enabled(self):
        region = self.cfg.get("POWER_SHARD_REGION") or (0, 0, 0, 0)
        try:
            return len(region) == 4 and int(region[2]) > 0 and int(region[3]) > 0
        except Exception:
            return False

    def extract_power_shards(self, text):
        value, _normalized = parse_power_shard_count(text, self.last_power_shards)
        return value

    def _power_shard_bucket(self, count):
        if count is None:
            return "unknown"
        empty = int(self.cfg.get("POWER_SHARD_EMPTY_THRESHOLD", 0))
        critical = int(self.cfg.get("POWER_SHARD_CRITICAL_THRESHOLD", 1000))
        very_low = int(self.cfg.get("POWER_SHARD_VERY_LOW_THRESHOLD", 5000))
        low = int(self.cfg.get("POWER_SHARD_LOW_THRESHOLD", 10000))
        if count <= empty:
            return "empty"
        if count <= critical:
            return "critical"
        if count <= very_low:
            return "very_low"
        if count <= low:
            return "low"
        return "normal"

    def _power_bucket_rank(self, bucket):
        return {
            "unknown": -1,
            "normal": 0,
            "low": 1,
            "very_low": 2,
            "critical": 3,
            "empty": 4,
        }.get(bucket, -1)

    def _update_power_shard_session(self, count):
        if count is None:
            return
        if self.session_start_power_shards is None:
            self.session_start_power_shards = count
            self.log(f"Power shard session start | value={format_shard_count(count)}")
        self.session_latest_power_shards = count

    def power_shard_usage_summary(self):
        start = self.session_start_power_shards
        current = self.session_latest_power_shards
        if start is None or current is None:
            return "Power shard usage: unknown"
        consumed = max(0, int(start) - int(current))
        hours = (time.time() - self.session_started_at) / 3600.0 if self.session_started_at else 0.0
        rate = consumed / hours if hours > 0.01 else 0.0
        return (
            "Power shard usage: "
            f"start={format_shard_count(start)}, "
            f"current={format_shard_count(current)}, "
            f"consumed={format_shard_count(consumed)}, "
            f"burn_rate={format_shard_count(int(rate))}/hr"
        )

    def _power_shard_alert_due(self, bucket, now=None):
        if bucket in ("unknown", "normal"):
            return False
        now = time.time() if now is None else now
        cooldown = max(60, int(self.cfg.get("POWER_SHARD_ALERT_COOLDOWN", 1800)))
        previous = self.last_power_shard_bucket
        if self._power_bucket_rank(bucket) > self._power_bucket_rank(previous):
            return True
        last = self.last_power_shard_bucket_alert.get(bucket, 0.0)
        return now - last >= cooldown

    def _emit_power_shard_threshold_alert(self, count, bucket):
        if bucket in ("unknown", "normal"):
            self.last_power_shard_bucket = bucket
            return False
        now = time.time()
        if not self._power_shard_alert_due(bucket, now):
            self.log(f"Power shards {bucket} alert suppressed by cooldown | value={compact_shard_count(count)}")
            self.last_power_shard_bucket = bucket
            return False

        label = {
            "low": "low",
            "very_low": "very low",
            "critical": "critically low",
            "empty": "empty",
        }.get(bucket, bucket)
        self.log(f"Power shards {label} | value={compact_shard_count(count)}")
        self.last_important_event = f"Power shards {label}: {compact_shard_count(count)}"
        title = "Power Shards Empty" if bucket == "empty" else f"Power Shards {label.title()}"
        body = self._discord_message(
            title,
            fields=[
                ("Status", label),
                ("Value", format_shard_count(count)),
                ("Session", self.power_shard_usage_summary()),
                ("Uptime", self._format_uptime()),
            ],
        )
        self.send_webhook_alert(
            f"power_shards_{bucket}",
            title,
            body,
            critical=bucket in ("critical", "empty"),
            dedup=True,
        )
        self.last_power_shard_bucket_alert[bucket] = now
        self.last_power_shard_bucket = bucket
        return True

    def power_shards_empty_confirmed(self, count):
        if count is None:
            if self._power_empty_check_active:
                self.log("Power shard empty condition not confirmed after low/suspicious evidence")
            return False
        empty = int(self.cfg.get("POWER_SHARD_EMPTY_THRESHOLD", 0))
        if count <= empty:
            chosen = (self.last_power_shard_ocr_state or {}).get("chosen") or {}
            if chosen:
                strong, reason = self._passive_shard_zero_evidence(
                    chosen,
                    (self.last_power_shard_ocr_state or {}).get("attempts") or [],
                )
                if strong:
                    self.log(f"Power shard empty confirmed from strong evidence | {reason}")
                    return True
                self.log(
                    "Power shard empty condition not confirmed after low/suspicious evidence | "
                    f"keeping previous valid value | {reason}"
                )
                return False
            self.log("Power shard empty condition not confirmed after low/suspicious evidence | no OCR evidence available")
            return False
        confirmed = False
        if not confirmed and self._power_empty_check_active:
            self.log("Power shard empty condition not confirmed after low/suspicious evidence")
        return confirmed

    def should_check_power_shards_empty(self, count):
        self._power_empty_check_active = False
        if not self.cfg.get("STOP_ON_EMPTY_POWER_SHARDS", True):
            return False
        empty = int(self.cfg.get("POWER_SHARD_EMPTY_THRESHOLD", 0))
        critical = int(self.cfg.get("POWER_SHARD_CRITICAL_THRESHOLD", 1000))
        low = int(self.cfg.get("POWER_SHARD_LOW_THRESHOLD", 10000))
        near_threshold = max(empty, critical, low)
        trusted = self.last_power_shards if self.last_power_shards is not None else self.session_latest_power_shards
        chosen = (self.last_power_shard_ocr_state or {}).get("chosen") or {}
        chosen_value = chosen.get("parsed")
        try:
            chosen_value = int(chosen_value) if chosen_value is not None else None
        except Exception:
            chosen_value = None
        suspicious_zero = chosen_value == 0 or "suspicious zero" in str(chosen.get("reason") or "").lower()

        if count is not None and count <= near_threshold:
            self._power_empty_check_active = True
            self.log(f"Power shard empty check triggered | latest value={count}")
            return True
        if trusted is not None and trusted > near_threshold and (count is None or count > near_threshold):
            now = time.time()
            if now - self._last_power_empty_check_skip_log >= 60.0:
                self.log(f"Power shard empty check skipped | healthy trusted value={trusted}")
                self._last_power_empty_check_skip_log = now
            return False
        if chosen_value is not None and chosen_value <= near_threshold:
            self._power_empty_check_active = True
            self.log("Power shard empty check triggered | suspicious low OCR candidate")
            return True
        if suspicious_zero:
            self._power_empty_check_active = True
            self.log("Power shard empty check triggered | suspicious zero OCR candidate")
            return True
        if trusted is None and count is None:
            return False
        return count is not None

    def power_shard_ocr_attempts(self, image=None, region=None):
        _require_module("pyautogui", pyautogui)
        _require_module("pytesseract", pytesseract)
        region = tuple(region or self.cfg["POWER_SHARD_REGION"])
        ocr_region = self._expanded_region(region, padding=4)
        img = image if image is not None else pyautogui.screenshot(region=ocr_region)
        attempts = []
        for mode, variant in self._shard_image_variants(img):
            for psm in (7, 6):
                try:
                    raw = self._ocr_tesseract_image(variant, psm)
                except Exception as e:
                    raw = f"<error: {e}>"
                parsed, normalized, candidate_type = _parse_power_shard_count_detail(
                    "" if raw.startswith("<error:") else raw,
                    self.last_power_shards,
                    infer_missing_suffix=True,
                )
                if candidate_type == "malformed_plain_count":
                    reason = "rejected malformed plain shard count"
                elif not normalized:
                    reason = "no normalized digits"
                elif parsed is None:
                    reason = "no valid shard count"
                else:
                    reason = "parsed"
                attempts.append(
                    {
                        "mode": mode,
                        "psm": psm,
                        "raw": raw,
                        "normalized": normalized,
                        "parsed": parsed,
                        "formatted": format_shard_count(parsed) if parsed is not None else "not found",
                        "reason": reason,
                        "candidate_type": candidate_type,
                    }
                )
        return {
            "region": region,
            "ocr_region": ocr_region,
            "image": img,
            "processed_image": preprocess_ocr_image(img, scale=3, threshold=True),
            "attempts": attempts,
        }

    def _best_power_shard_attempt(self, attempts):
        valid = [attempt for attempt in attempts if attempt.get("parsed") is not None]
        if not valid:
            return None
        stable = []
        for attempt in valid:
            parsed = int(attempt["parsed"])
            normalized = str(attempt.get("normalized") or "")
            if parsed < 0:
                attempt["reason"] = "rejected garbage: negative"
                continue
            if parsed > 100_000_000:
                attempt["reason"] = "rejected garbage: implausibly high"
                continue
            if not re.search(r"\d", normalized):
                attempt["reason"] = "rejected garbage: no digits"
                continue
            if parsed == 0:
                strong_zero, zero_reason = self._passive_shard_zero_evidence(attempt, valid)
                if not strong_zero:
                    attempt["reason"] = f"suspicious zero rejected: {zero_reason}"
                    continue
                attempt["reason"] = zero_reason
            if parsed <= 9 and not re.search(r"\b\d(?:\.0+)?\b", normalized):
                attempt["reason"] = "rejected garbage: malformed tiny value"
                continue
            attempt["parsed"] = parsed
            attempt["formatted"] = format_shard_count(parsed)
            stable.append(attempt)
        valid = stable
        if not valid:
            return None
        if self.last_power_shards is not None:
            return min(valid, key=lambda item: abs(int(item["parsed"]) - int(self.last_power_shards)))
        priority = {"threshold": 0, "contrast": 1, "gray": 2, "raw": 3}
        return min(valid, key=lambda item: (priority.get(item.get("mode"), 9), item.get("psm", 9), -int(item["parsed"])))

    def read_power_shards(self):
        if not self.power_shard_region_enabled():
            if not self._power_shard_region_warned:
                self.log("Power shard region not set; Power shard reports are paused.")
                self._power_shard_region_warned = True
            return None

        region = tuple(self.cfg["POWER_SHARD_REGION"])
        try:
            result = self.power_shard_ocr_attempts(region=region)
        except Exception as e:
            self.log(f"Power shard OCR failed | region={region} | error={e}")
            return None

        attempts = result["attempts"]
        self.log(f"Power shard OCR region | configured={region} | used={result['ocr_region']}")
        best = self._best_power_shard_attempt(attempts)
        for attempt in attempts:
            self.log(
                "Power shard OCR | "
                f"mode={attempt['mode']} psm={attempt['psm']} | "
                f"raw={self._compact_debug_text(attempt['raw']) or '<empty>'} | "
                f"normalized={attempt['normalized'] or '<empty>'} | "
                f"parsed={attempt['formatted']} | candidate={attempt.get('candidate_type', 'none')} | "
                f"reason={attempt['reason']}"
            )

        self._write_ocr_debug_event(
            "power_shard_ocr",
            {
                "region": list(region),
                "ocr_region": list(result["ocr_region"]),
                "attempts": attempts,
                "chosen": best,
                "previous_value": self.last_power_shards,
                "infer_missing_suffix": True,
            },
        )
        self.last_power_shard_ocr_state = {
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "region": region,
            "ocr_region": result["ocr_region"],
            "chosen": best,
            "attempts": attempts,
            "previous_valid": self.last_power_shards,
        }
        self.record_decision_chain(
            subsystem="Shards",
            power_shard_result=best.get("formatted") if best else "not found",
            power_shard_reason=best.get("reason") if best else "no valid shard count",
        )
        if best is not None:
            count = int(best["parsed"])
            self.log(
                "Power shard OCR accepted | "
                f"raw={self._compact_debug_text(best.get('raw')) or '<empty>'} | "
                f"normalized={best.get('normalized') or '<empty>'} | "
                f"parsed={count} ({compact_shard_count(count)}) | "
                f"candidate={best.get('candidate_type', 'unknown')} | "
                f"source={best['mode']} psm={best['psm']}"
            )
            self.last_power_shards = count
            self._update_power_shard_session(count)
            return count

        reasons = ", ".join(sorted({attempt["reason"] for attempt in attempts})) or "no attempts"
        if "suspicious zero" in reasons:
            self.log("Power shard OCR suspicious zero rejected")
        self.log(f"Power shard OCR rejected as garbage or did not find a count | region={region} | reasons={reasons}")
        if self.last_power_shards is not None:
            self.log(f"Power shard OCR failed; keeping previous valid value {format_shard_count(self.last_power_shards)}")
        return None

    def _send_power_shard_standalone_update(self, count_text, reason="update"):
        ok = self.send_discord_message(
            self._discord_message(
                "Power Shard Update",
                fields=[
                    ("Power shards", count_text),
                    ("Reason", reason),
                    ("Uptime", self._format_uptime()),
                ],
            ),
            dedup_key=f"power_shards_standalone:{count_text}:{reason}",
            dedup_window=60,
            use_ping=False,
        )
        if ok:
            self.log("Power shard standalone Discord update sent")
        else:
            self.log("Power shard standalone Discord update failed")
        return ok

    def maybe_report_power_shards(self, force=False):
        if self.roll_domain != "powers" and not force:
            return self.last_power_shards
        alerts_enabled = self.cfg.get("POWER_SHARD_ALERTS", True)
        if not alerts_enabled and not self.cfg.get("STOP_ON_EMPTY_POWER_SHARDS", True):
            return None
        interval = max(60, int(self.cfg.get("POWER_SHARD_REPORT_INTERVAL", 1200)))
        now = time.time()
        if not force and now - self.last_power_shard_report < interval:
            return self.last_power_shards

        count = self.read_power_shards()
        if count is None:
            if self.last_power_shards is not None:
                self.log(
                    "Power shard report skipped: no valid shard count parsed; "
                    f"retaining previous valid value {format_shard_count(self.last_power_shards)}."
                )
            else:
                self.log("Power shard report skipped: no valid shard count parsed.")
            return None

        self.last_power_shard_report = now
        count_text = format_shard_count(count)
        self.log(f"Power shards: {count_text}")
        bucket = self._power_shard_bucket(count)
        if alerts_enabled:
            self._emit_power_shard_threshold_alert(count, bucket)
        changed = count != self.last_power_shards_sent

        if bucket == "empty":
            self.last_power_shards_sent = count
        elif alerts_enabled and self.cfg.get("WEBHOOK_LIVE_STATUS_ENABLED", True):
            if force or changed:
                self.last_important_event = f"Power shards: {count_text}"
                if self.maybe_update_live_status(force=True):
                    self.log("Power shard update applied to live status")
                    self.last_power_shards_sent = count
                else:
                    self.log("Power shard live status update failed; sending standalone fallback")
                    if self._send_power_shard_standalone_update(count_text, reason="live status fallback"):
                        self.last_power_shards_sent = count
            else:
                self.log("Power shard count unchanged; Discord update skipped.")
        elif alerts_enabled and (force or changed):
            if self._send_power_shard_standalone_update(count_text, reason="scheduled report"):
                self.last_power_shards_sent = count
        elif alerts_enabled:
            self.log("Power shard count unchanged; Discord update skipped.")
        return count

    def alert_macro_stopped(self, reason):
        self.set_status("Error")
        self.log(f"Macro stopped: {reason}")
        self._set_terminal_stop_reason(f"Macro stopped: {reason}")
        count = self.read_passive_shards()
        shard_line = f"\nPassive shards remaining: {format_shard_count(count)}" if count is not None else ""
        popup_state = "unknown"
        try:
            popup_state = "yes" if self.popup_active(log=True, context="macro stop alert") else "no"
        except Exception:
            popup_state = "unknown"
        self.record_decision_chain(
            subsystem="Runtime",
            runtime_state="macro_stopped",
            stop_reason=reason,
            popup_detected=popup_state,
        )
        self._maybe_auto_capture_debug_snapshot(
            "macro_stop",
            extra={"reason": reason, "popup_state": popup_state},
        )
        body = self._discord_message(
            "Macro Needs Attention",
            fields=[
                ("Reason", reason),
                ("Uptime", self._format_uptime()),
                ("Recoveries", self.session_recovery_count),
                ("Last trait/spec", display_trait(self.last_trait_seen) if self.last_trait_seen else "unknown"),
                ("Popup detected", popup_state),
                ("Passive shards", format_shard_count(count) if count is not None else "unknown"),
                ("Passive shard session", self.passive_shard_usage_summary()),
                ("Power shards", format_shard_count(self.session_latest_power_shards) if self.session_latest_power_shards is not None else "unknown"),
                ("Power shard session", self.power_shard_usage_summary()),
            ],
        )
        attach = bool(self.cfg.get("WEBHOOK_FAILURE_SCREENSHOTS", True)) and bool(
            self.cfg.get("WEBHOOK_SCREENSHOT_ON_MACRO_STOP", True)
        )
        self.send_webhook_alert(
            "macro_stopped",
            "Macro Needs Attention",
            body,
            critical=True,
            attach_screenshot=attach,
            screenshot_label="macro_stopped",
        )

    def capture_screen(self, label):
        _require_module("pyautogui", pyautogui)
        CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
        safe_label = re.sub(r"[^a-zA-Z0-9_-]+", "_", label.strip() or "capture")
        path = CAPTURE_DIR / f"{ARTIFACT_VERSION_PREFIX}_{time.strftime('%Y%m%d_%H%M%S')}_{safe_label}.png"
        pyautogui.screenshot().save(path)
        return str(path)

    def delete_capture(self, image_path):
        if not image_path:
            return
        try:
            path = Path(image_path)
            if path.exists() and path.is_file():
                path.unlink()
                self.log("Deleted local screenshot after Discord upload.")
        except Exception as e:
            self.log(f"Could not delete local screenshot: {e}")

    def send_webhook(self, image_path, trait, summary, ocr_text, is_test=False):
        if is_test:
            content = self._discord_message(
                "Webhook Test",
                fields=[
                    ("Status", "delivered"),
                    ("App", APP_DISPLAY_NAME),
                    ("Timestamp", time.strftime("%Y-%m-%d %H:%M:%S")),
                ],
                footer="If this message and image arrived, Discord delivery is working.",
            )
            return self._send_discord_file(content, image_path)

        clean_ocr = (
            ocr_text.replace("\u2014", "-")
            .replace("current--spec", "current spec")
            .replace("eexecutionerrioner", "executioner")
            .strip()
        )
        self.session_god_rolls += 1
        self.last_trait_seen = trait or self.last_trait_seen
        parsed_values = dict((self.last_decision_chain or {}).get("parsed_values") or {})
        if trait in SUPPORTED_POWER_DEFINITIONS:
            self._set_terminal_stop_reason(f"Power roll found: {display_trait(trait)}")
            content = self._roll_markdown_message(
                "Kon. Kept Power Roll",
                trait,
                summary,
                "A Power roll matched the active target rules, so the macro stopped and kept it.",
                [
                    "- Status: Kept",
                    "- Reason: all configured Power target thresholds were met",
                ],
                ocr_text=clean_ocr,
            )
            return self._send_discord_file(content, image_path)

        self._set_terminal_stop_reason(f"God roll found: {display_trait(trait)}")
        content = self._roll_markdown_message(
            "Kon. Kept Spec Roll",
            trait,
            summary,
            "A Spec roll matched the active target rules, so the macro stopped and kept it.",
            [
                "- Status: Kept",
                "- Reason: all configured Spec target thresholds were met",
            ],
            ocr_text=clean_ocr,
        )
        return self._send_discord_file(content, image_path)

    def test_webhook(self):
        if not self.cfg["WEBHOOK_URL"].strip():
            self.log("Webhook not set, skipping Discord send")
            return False
        shot = self.capture_screen("webhook_test")
        return self.send_webhook(shot, None, "", "", is_test=True)

    def _near_miss_distance_from_summary(self, trait, summary):
        values = self.extract_labeled_values(trait, summary)
        matched = []
        for idx, (low, high) in enumerate(self.rules.get(trait, [])):
            value = values[idx] if idx < len(values) else None
            matched.append((low, high, value is not None and in_range([value], low, high)))
        return self.describe_miss_distance(trait, values, matched)

    def startup_check_current_roll(self):
        fast_started = time.perf_counter()
        fast_state, fast_trait, fast_summary, fast_ocr_text, fast_missing, fast_near = self.check_roll(allow_fallback=False, startup_fast=True)
        fast_chain = dict(self.last_decision_chain or {})
        fast_ocr_candidate_debug = dict(self.last_ocr_candidate_debug or {})
        fast_trait_text = display_trait(fast_trait) if fast_trait else "unknown"
        fast_elapsed_ms = int((time.perf_counter() - fast_started) * 1000)
        self.log(
            "[Startup Verify] Startup fast current-spec probe | "
            f"state={fast_state} trait={fast_trait_text} | elapsed={fast_elapsed_ms}ms | "
            f"startup_fast_probe_ms={fast_elapsed_ms} | strategy=startup_fast_non_target_probe"
        )
        if fast_state == "NON_TARGET":
            self.last_trait_seen = fast_trait or self.last_trait_seen
            self._record_startup_spec_class("NON_TARGET filler")
            if self.roll_domain == "powers":
                if self._startup_context_active():
                    self._startup_context["powers_autoskip_current"] = True
                    self._startup_context["preflight_bypassed"] = True
                    self._startup_context["preflight_fallback_reason"] = "autoskip_power"
                self._record_startup_route(
                    "continue",
                    reason="startup_fast_power_autoskip",
                    confidence="strong",
                    supports=["autoskip_power_not_listed"],
                )
                self.log(
                    "Startup fast current power is AUTOSKIP/NON_TARGET; "
                    "skipping trust probe and slower full current-spec scan"
                )
                return "continue"
            popup_known_clear = bool(getattr(self, "_startup_context", {}).get("startup_popup_clear_known")) if self._startup_context_active() else False
            popup_visible = False if popup_known_clear else self._popup_active_checked(
                log=True,
                context="startup fast NON_TARGET trust probe",
                fast=True,
            )
            if not popup_visible and self._startup_context_active():
                trust_started = time.perf_counter()
                trust_changed, _trust_text = self.stats_changed(
                    (fast_ocr_text or "").strip() or (fast_summary or "").strip(),
                    "Startup fast NON_TARGET trust probe",
                    polls_override=1,
                    poll_delay_override=0.01,
                    unreadable_fast_fail_polls=1,
                    psm_sequence_override=(6,),
                    ui_signals=["startup_fast_non_target_probe"],
                    candidate_signal_enabled=False,
                    abandon_on_weak_samples=1,
                    initial_popup_known_false=popup_known_clear,
                    fast_popup_checks=True,
                )
                trust_state = self.last_recovery_verify_state if not trust_changed else "rolling"
                trust_details = self.last_recovery_verify_details or {}
                trust_support = self._startup_confirmation_support(
                    trust_state,
                    trust_details,
                    self.last_recovery_reason,
                    popup_state=False,
                )
                trust_elapsed_ms = int((time.perf_counter() - trust_started) * 1000)
                trust_signals = trust_support["signals"]
                trust_support_text = "+".join(trust_signals) if trust_signals else "none"
                trust_usefulness = "strong" if trust_support["strong"] and trust_changed else ("marginal" if trust_changed or trust_signals else ("weak" if trust_details.get("weak_samples", 0) else "none"))
                trust_exit_reason = trust_details.get("exit_reason") or trust_support["reason"] or self.last_recovery_reason or "none"
                self.log(
                    "[Startup Verify] Startup fast NON_TARGET trust probe | "
                    f"state={trust_state} trait={fast_trait_text} | elapsed={trust_elapsed_ms}ms | "
                    f"bridge_probe_elapsed={trust_elapsed_ms}ms | bridge_probe_usefulness={trust_usefulness} | "
                    f"bridge_probe_exit_reason={trust_exit_reason} | bridge_probe_supports={trust_support_text} | "
                    f"decision_confidence={'strong' if trust_support['strong'] else 'marginal' if trust_usefulness != 'none' else 'weak'} | "
                    f"startup_logic_version={STARTUP_LOGIC_VERSION} | strategy=bridge_probe_before_preflight"
                )
                if trust_changed and trust_support["strong"]:
                    self._startup_context["fast_non_target_trust"] = True
                    self._startup_context["preflight_bypassed"] = True
                    self._record_startup_route(
                        "continue",
                        reason="fast_non_target_probe_plus_bridge_probe_confirmed_rolling",
                        confidence="strong",
                        supports=trust_support["signals"],
                    )
                    self.log(
                        "Startup fast current-spec probe accepted strong NON_TARGET filler evidence; "
                        "bridge probe confirmed rolling, skipping slower full current-spec scan and Initial Auto Start preflight"
                    )
                    return "continue"
                self._startup_context["preflight_bypassed"] = False
                self._startup_context["preflight_fallback_reason"] = trust_exit_reason
                self.log(
                    "[Startup Timing] bridge probe abandoned early | "
                    f"bridge_probe_elapsed={trust_elapsed_ms}ms | bridge_probe_usefulness={trust_usefulness} | "
                    f"preflight_bypassed=False | preflight_fallback_reason={trust_exit_reason} | strategy=bridge_probe_fail_fast_to_preflight"
                )
            self.log(
                "Startup fast current-spec probe accepted strong NON_TARGET filler evidence; "
                "skipping slower full current-spec scan"
            )
            return "continue"

        fast_power_support = self._startup_fast_power_probe_support(
            fast_state,
            fast_trait,
            fast_summary,
            fast_ocr_text,
        )
        if fast_power_support["strong"]:
            state, trait, summary, ocr_text, missing, near = (
                fast_state,
                fast_trait,
                fast_summary,
                fast_ocr_text,
                fast_missing,
                fast_near,
            )
            trait_text = display_trait(trait) if trait else "unknown"
            self.log(
                "[Startup Verify] Startup fast current-spec check | "
                f"state={state} trait={trait_text} | elapsed={fast_elapsed_ms}ms | "
                f"startup_fast_probe_ms={fast_elapsed_ms} | startup_full_validation_skipped=True | "
                "strategy=trusted_startup_fast_power_probe"
            )
            self.log(
                "Startup fast power probe accepted strong supported mythical evidence; "
                f"skipping slower full current-spec scan | quality={fast_power_support['quality']} | "
                f"parsed_values={fast_power_support['parsed_values']} | "
                f"passive_detected={fast_power_support.get('passive_detected', False)}"
            )
        else:
            fast_spec_support = self._startup_fast_spec_bad_support(
                fast_state,
                fast_trait,
                fast_summary,
                fast_ocr_text,
                fast_missing,
                fast_chain,
            )
            if fast_spec_support["strong"]:
                state, trait, summary, ocr_text, missing, near = (
                    fast_state,
                    fast_trait,
                    fast_summary,
                    fast_ocr_text,
                    fast_missing,
                    fast_near,
                )
                self.last_decision_chain = fast_chain
                self.last_ocr_candidate_debug = fast_ocr_candidate_debug
                self.log(
                    "[Startup Verify] Startup fast current-spec check | "
                    f"state={state} trait={fast_trait_text} | elapsed={fast_elapsed_ms}ms | "
                    f"startup_fast_probe_ms={fast_elapsed_ms} | startup_full_validation_skipped=True | "
                    "strategy=trusted_startup_fast_spec_probe"
                )
                self.log(
                    "Startup fast Spec probe accepted strong BAD/DISABLED mythical evidence; "
                    f"skipping slower full current-spec scan | values={fast_spec_support['values']} | "
                    f"labels={fast_spec_support['value_count']}/{len(STAT_LABELS.get(fast_trait, [])) or '?'}"
                )
            else:
                started = time.perf_counter()
                state, trait, summary, ocr_text, missing, near = self.check_roll(allow_fallback=False)
                full_validation_ms = int((time.perf_counter() - started) * 1000)
                trait_text = display_trait(trait) if trait else "unknown"
                self.log(
                    "[Startup Verify] Startup fast current-spec check | "
                    f"state={state} trait={trait_text} | elapsed={full_validation_ms}ms | "
                    f"startup_fast_probe_ms={fast_elapsed_ms} | startup_full_validation_skipped=False | "
                    "strategy=full_validation_after_probe"
                )
                followup_proves_changed = self._startup_followup_proves_different_spec(
                    fast_trait,
                    state,
                    trait,
                    ocr_text or summary,
                )
                if fast_spec_support["strong"] and state in ("NON_TARGET", "ROLLING") and not followup_proves_changed:
                    self.log(
                        "Startup retained first strong BAD/DISABLED Spec after weak follow-up | "
                        f"initial_state={fast_state} initial_trait={display_trait(fast_trait)} | "
                        f"followup_state={state} followup_trait={display_trait(trait) if trait else 'unknown'} | "
                        f"values={fast_spec_support['values']} | reason=followup_did_not_prove_roll_changed"
                    )
                    state, trait, summary, ocr_text, missing, near = (
                        fast_state,
                        fast_trait,
                        fast_summary,
                        fast_ocr_text,
                        fast_missing,
                        fast_near,
                    )
                    self.last_decision_chain = fast_chain
                    self.last_ocr_candidate_debug = fast_ocr_candidate_debug

        if state == "GOD":
            self.last_trait_seen = trait or self.last_trait_seen
            self.log(f"Startup check | KEEP {trait.upper()} already on screen")
            self.set_status(f"GOD ROLL | {display_trait(trait)}")
            shot = ""
            webhook_sent = False
            if self.cfg["WEBHOOK_URL"].strip():
                shot = self.capture_screen(f"{trait}_startup")
                webhook_sent = self.send_webhook(shot, trait, summary, ocr_text)
                if webhook_sent and self.cfg.get("DELETE_SCREENSHOTS_AFTER_WEBHOOK", True):
                    shot = ""
            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            self.on_god_roll(stamp, trait, summary, shot, webhook_sent)
            self._set_startup_result(STARTUP_STOPPED_ON_CURRENT_SPEC)
            return "stop"

        if state == "NON_TARGET":
            self.last_trait_seen = trait or self.last_trait_seen
            self._record_startup_spec_class("NON_TARGET filler")
            self.log(
                "Startup current spec is NON_TARGET rollable filler; "
                "continuing to normal Initial Auto Start"
            )
            return "continue"

        if state in ("BAD", "DISABLED", "HIGH_VALUE"):
            miss_text = " | ".join(missing) if missing else "target stats not met"
            self.log(f"Startup check | Existing {self._manual_reroll_target_kind()} is not a god roll: {miss_text}")
            if near or state == "HIGH_VALUE":
                stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                distance = self._near_miss_distance_from_summary(trait, summary)
                self.on_near_miss(stamp, trait, summary, "", miss_text, distance)
                self.send_near_miss_alert(trait, summary, miss_text, distance)
                if state == "HIGH_VALUE":
                    self._set_terminal_stop_reason(f"High value roll: {display_trait(trait)}")
                    self.set_status(f"HIGH VALUE | {display_trait(trait)}")
                    self._set_startup_result(STARTUP_STOPPED_ON_CURRENT_SPEC)
                    return "stop"
            if state in ("BAD", "DISABLED"):
                self._record_startup_spec_class("manual-confirm-required suspicion")
                if self.roll_domain == "powers" and state == "BAD" and not self._confirm_power_bad_before_manual_reroll(
                    trait,
                    missing,
                    context="Startup Power BAD manual reroll",
                    fast_first=bool(fast_power_support.get("strong")),
                ):
                    self.log(
                        "Startup current power BAD was not stable enough for manual reroll; "
                        "falling back to Initial Auto Start"
                    )
                    return "continue"
                self.log(f"Startup current {self._manual_reroll_target_kind()} is {state}; manual rerolling immediately")
                self._mark_startup_manual_reroll(fallback=True)
                if self.manual_reroll_flow(f"startup current {state.lower()} {trait or 'unknown'}"):
                    recent_manual_confirm = self._manual_reroll_recently_confirmed()
                    if recent_manual_confirm:
                        self.log(
                            "[Startup Timing] current-spec manual reroll verify skipped | "
                            "source=manual_reroll_flow_behavior_confirmed | elapsed=0ms | "
                            "strategy=avoid_duplicate_post_reroll_verify"
                        )
                        self.clear_recovery_failures(f"startup current {state} rerolled")
                        self._set_startup_result(
                            STARTUP_CURRENT_SPEC_BAD_REROLLED_THEN_ROLLING,
                            rolling_confirmed=True,
                        )
                        self.log("Startup current-spec manual reroll complete; rolling confirmed")
                        return "rerolled"

                    verify_started = time.perf_counter()
                    changed, verify_text = self.stats_changed(
                        ocr_text.strip() or summary,
                        "Startup current-spec manual reroll verify",
                        ui_signals=["manual_reroll_flow_completed"],
                        polls_override=2,
                        poll_delay_override=0.06,
                        unreadable_fast_fail_polls=2,
                    )
                    self.log(
                        "[Startup Verify] current-spec manual reroll verify elapsed | "
                        f"{int((time.perf_counter() - verify_started) * 1000)}ms | changed={changed}"
                    )
                    if changed:
                        self.clear_recovery_failures(f"startup current {state} rerolled")
                        self._set_startup_result(
                            STARTUP_CURRENT_SPEC_BAD_REROLLED_THEN_ROLLING,
                            rolling_confirmed=True,
                        )
                        self.log("Startup current-spec manual reroll complete; rolling confirmed")
                        return "rerolled"
                    failure = STARTUP_FAILED_UNREADABLE_UI if self.last_recovery_verify_unreadable else STARTUP_FAILED_NO_ROLL_DETECTED
                    self._set_startup_result(failure)
                    self.log(
                        "Startup current-spec manual reroll finished, but rolling was not confirmed | "
                        f"OCR: {self._compact_debug_text(verify_text)}"
                    )
                    return "failed"
                self._set_startup_result(STARTUP_FAILED_NO_ROLL_DETECTED)
                self.log("Startup current-spec manual reroll failed; startup will stop safely")
                return "failed"
        else:
            self._record_startup_spec_class("unknown")
            self.log("Startup current-spec not reliable; falling back to Initial Auto Start")

        return "continue"

    def loop(self):
        self.running = True
        self.stop_event.clear()
        self._startup_shard_prime_pending = set()
        self.last_text = ""
        self.last_change = time.time()
        self.recovery_failures = 0
        self.watchdog_in_progress = False
        self.recovery_in_progress = False
        self.manual_reroll_active = False
        self.last_watchdog_attempt_at = 0.0
        self.last_watchdog_signature = ""
        self.session_started_at = time.time()
        self.session_recovery_count = 0
        self.session_god_rolls = 0
        self.session_near_misses = 0
        self.last_trait_seen = ""
        self.last_important_event = "Session started"
        self.terminal_stop_reason = ""
        self.last_auto_checkbox_classifier_summary = {}
        self.auto_checkbox_read_count = 0
        self.auto_checkbox_ambiguous_read_count = 0
        self.manual_reroll_direct_recovery_clicks = 0
        self.recent_route_budget_events = []
        self.last_verification_cache_stats = {}
        self.live_status_message_id = None
        self.live_status_can_edit = False
        self.last_status_update = 0.0
        self._webhook_dedup = {}

        self.log(f"Starting {APP_DISPLAY_NAME}...")
        self.set_status("Starting")
        self._begin_startup_context("session startup")
        deferred_startup_tasks = []
        startup_started = time.perf_counter()
        configured_startup_delay = max(0.0, float(self.cfg.get("STARTUP_DELAY", DEFAULT_CONFIG["STARTUP_DELAY"])))
        startup_probe_delay = min(configured_startup_delay, 0.05)
        if startup_probe_delay > 0 and not self._interruptible_sleep(startup_probe_delay, "startup initial delay"):
            self._finish_startup_summary(STARTUP_FAILED_TIMEOUT)
            self.running = False
            self.set_status("Stopped")
            self.finish_live_status("Manual stop during startup")
            self.log("Bot stopped.")
            return
        startup_delay_remaining = max(0.0, configured_startup_delay - startup_probe_delay)
        startup_delay_shortened = startup_delay_remaining > 0.0
        popup_visible_during_probe = False
        if startup_delay_shortened:
            popup_visible_during_probe = self._popup_active_checked(log=True, context="startup delay probe", fast=True)
            self.log(
                "[Startup Timing] startup delay conditionally shortened | "
                f"configured={configured_startup_delay:.2f}s | waited={startup_probe_delay:.2f}s | "
                f"skipped={startup_delay_remaining:.2f}s | popup_visible={popup_visible_during_probe} | strategy=front_half_early_probe"
            )
        if self._startup_context_active():
            self._startup_context["startup_popup_clear_known"] = not popup_visible_during_probe
        self.log(f"[Startup] delay elapsed | {int((time.perf_counter() - startup_started) * 1000)}ms")

        startup_action = self.startup_check_current_roll()
        if startup_action == "stop":
            self._finish_startup_summary(STARTUP_STOPPED_ON_CURRENT_SPEC)
            self.running = False
            self.set_status("Stopped")
            self.finish_live_status("Stopped on startup roll")
            self.log("Bot stopped.")
            return
        if startup_action == "failed":
            self._finish_startup_summary(self.last_startup_result or STARTUP_FAILED_NO_ROLL_DETECTED)
            self.alert_macro_stopped("Startup current-spec handling did not confirm rolling. Check Auto and button positions.")
            self.running = False
            self.finish_live_status("Startup current-spec handling failed")
            return

        self.last_passive_shard_report = 0.0
        deferred_startup_tasks.append("live_status")
        deferred_startup_tasks.append("passive_shards")
        if self.roll_domain == "powers":
            self.last_power_shard_report = 0.0
            deferred_startup_tasks.append("power_shards")
        self.log(
            "[Startup Timing] deferred_noncritical="
            f"{','.join(deferred_startup_tasks)} | strategy=prioritize_time_to_first_roll"
        )

        fast_non_target_trusted = bool(getattr(self, "_startup_context", {}).get("fast_non_target_trust", False)) if self._startup_context_active() else False
        initial_started = startup_action == "rerolled" or fast_non_target_trusted
        if startup_action == "rerolled":
            self.log("Initial auto-start skipped | startup current spec was rerolled manually")
        elif fast_non_target_trusted:
            self._set_startup_result(STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)
            self.log(
                "Initial auto-start skipped | startup fast NON_TARGET bridge probe already behavior-confirmed rolling"
            )
        initial_recovery_started = time.perf_counter()
        if not initial_started:
            max_initial_attempts = min(2, max(1, int(self.cfg.get("MAX_RECOVERY_ATTEMPTS", 3))))
            for attempt in range(max_initial_attempts):
                if self._stop_requested("initial auto start"):
                    break
                if self.start_or_recover("Initial Auto Start"):
                    initial_started = True
                    break
                if self.recovery_failed_should_stop(
                    "Initial Auto Start",
                    f"rolling activity could not be confirmed on startup attempt {attempt + 1}",
                ):
                    break
            self.log(
                "[Startup] Initial auto-start recovery elapsed | "
                f"{int((time.perf_counter() - initial_recovery_started) * 1000)}ms | "
                f"started={initial_started}"
            )
        if not initial_started:
            if self.last_startup_result in ("", "pending", STARTUP_STOPPED_ON_CURRENT_SPEC):
                self._set_startup_result(STARTUP_FAILED_NO_ROLL_DETECTED)
            self._finish_startup_summary(self.last_startup_result)
            self.alert_macro_stopped("Initial auto start did not confirm rolling after repeated attempts. Check passive shards and button positions.")
            self.running = False
            self.finish_live_status("Initial auto start failed")
            return
        if self.last_startup_result in ("", "pending"):
            self._set_startup_result(STARTUP_CONFIRMED_ROLLING, rolling_confirmed=True)
        self._finish_startup_summary(self.last_startup_result)

        deferred_started = time.perf_counter()
        if deferred_startup_tasks:
            self.log(
                "[Startup Timing] starting deferred startup tasks | "
                f"tasks={','.join(deferred_startup_tasks)}"
            )
        if "live_status" in deferred_startup_tasks:
            self.start_live_status()
        if "passive_shards" in deferred_startup_tasks:
            self._startup_shard_prime_pending.add("passive")
        if "power_shards" in deferred_startup_tasks:
            self._startup_shard_prime_pending.add("power")
        if deferred_startup_tasks:
            deferred_elapsed = time.perf_counter() - deferred_started
            self.log(
                "[Startup Timing] deferred startup tasks complete | "
                f"elapsed={int(deferred_elapsed * 1000)}ms"
            )
            self._record_timing_event(
                "startup_deferred_tasks",
                deferred_elapsed,
                tasks=",".join(deferred_startup_tasks),
                result="queued",
            )

        while not self.stop_event.is_set():
            loop_started = time.perf_counter()
            shard_elapsed = 0.0
            check_elapsed = 0.0
            bad_confirm_elapsed = 0.0
            manual_elapsed = 0.0
            loop_state = "unknown"
            try:
                shard_started = time.perf_counter()
                if "passive" in self._startup_shard_prime_pending:
                    self.maybe_report_passive_shards(force=True)
                    self._startup_shard_prime_pending.discard("passive")
                if "power" in self._startup_shard_prime_pending and self.roll_domain == "powers":
                    self.maybe_report_power_shards(force=True)
                    self._startup_shard_prime_pending.discard("power")

                shard_count = self.maybe_report_passive_shards()
                if (
                    self.should_check_passive_shards_empty(shard_count)
                    and self.passive_shards_empty_confirmed(shard_count)
                ):
                    self.log("Stopping macro: passive shards exhausted")
                    self.alert_macro_stopped("Passive shards are exhausted, so rolling cannot continue.")
                    break

                if self.roll_domain == "powers":
                    power_shard_count = self.maybe_report_power_shards()
                    if (
                        self.should_check_power_shards_empty(power_shard_count)
                        and self.power_shards_empty_confirmed(power_shard_count)
                    ):
                        self.log("Stopping macro: power shards exhausted")
                        self.alert_macro_stopped("Power shards are exhausted, so rolling cannot continue.")
                        break
                shard_elapsed = time.perf_counter() - shard_started

                check_started = time.perf_counter()
                state, trait, summary, ocr_text, missing, near = self.check_roll()
                check_elapsed = time.perf_counter() - check_started
                loop_state = state or "unknown"
                if trait:
                    self.last_trait_seen = trait

                current_text = ocr_text.strip()
                _cleaned_current, _trait, _numbers, _stat_signal, _marker, useful_current, unreliable_current = (
                    self._recovery_text_quality(current_text)
                )
                if useful_current and not unreliable_current and current_text != self.last_text:
                    self.last_text = current_text
                    self.last_change = time.time()
                    self.clear_recovery_failures("useful OCR activity during loop")
                elif current_text and current_text != self.last_text and unreliable_current:
                    self.log(f"Loop ignored weak OCR activity | {self._compact_debug_text(current_text)}")

                if state == "GOD":
                    self.last_trait_seen = trait or self.last_trait_seen
                    self.set_status(f"GOD ROLL | {display_trait(trait)}")
                    shot = ""
                    webhook_sent = False
                    if self.cfg["WEBHOOK_URL"].strip():
                        shot = self.capture_screen(trait)
                        webhook_sent = self.send_webhook(shot, trait, summary, ocr_text)
                        if webhook_sent and self.cfg.get("DELETE_SCREENSHOTS_AFTER_WEBHOOK", True):
                            shot = ""
                    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                    self.on_god_roll(stamp, trait, summary, shot, webhook_sent)
                    break

                if state == "NON_TARGET":
                    self.last_trait_seen = trait or self.last_trait_seen
                    self.set_status(f"ROLLING | {display_trait(trait)} filler")
                    filler_event = f"Rolling through non-target: {display_trait(trait)}"
                    if self.last_important_event != filler_event:
                        self.log(f"NON_TARGET rollable filler observed | trait={display_trait(trait)}; letting Auto continue")
                    self.last_important_event = filler_event
                    idle_for = time.time() - self.last_change
                    watchdog_threshold = self._watchdog_timeout()
                    suspicion_threshold = self._watchdog_suspicion_timeout()
                    if idle_for > suspicion_threshold and idle_for <= watchdog_threshold:
                        if self._should_trigger_watchdog_suspicion(current_text, state, trait, idle_for):
                            self.log(
                                f"NON_TARGET stale suspicion for {idle_for:.1f}s; escalating early watchdog recovery "
                                f"(threshold={suspicion_threshold:.1f}s full={watchdog_threshold:.1f}s)"
                            )
                            watchdog_result = self.unexpected_not_rolling_watchdog(
                                current_text,
                                state,
                                trait,
                                idle_for,
                                popup_known_clear=True,
                                banner_known_clear=True,
                                stage="suspicion",
                                allow_early=True,
                            )
                            if watchdog_result == "recovered":
                                if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "post-watchdog loop delay"):
                                    break
                                continue
                            if watchdog_result == "off_panel":
                                if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "post-watchdog off-panel loop delay"):
                                    break
                                continue
                            if watchdog_result == "failed":
                                if self.recovery_failed_should_stop(
                                    "Unexpected No-Roll Watchdog",
                                    "auto re-enable did not restore rolling",
                                ):
                                    self.alert_macro_stopped("Unexpected no-roll watchdog failed after repeated attempts. Check Auto, OCR, and button positions.")
                                    break
                                continue
                    if idle_for > watchdog_threshold:
                        self.log(
                            f"NON_TARGET stale for {idle_for:.1f}s; checking unexpected no-roll watchdog before recovery"
                        )
                        watchdog_result = self.unexpected_not_rolling_watchdog(current_text, state, trait, idle_for)
                        if watchdog_result == "recovered":
                            if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "post-watchdog loop delay"):
                                break
                            continue
                        if watchdog_result == "off_panel":
                            if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "post-watchdog off-panel loop delay"):
                                break
                            continue
                        if watchdog_result == "failed":
                            if self.recovery_failed_should_stop(
                                "Unexpected No-Roll Watchdog",
                                "auto re-enable did not restore rolling",
                            ):
                                self.alert_macro_stopped("Unexpected no-roll watchdog failed after repeated attempts. Check Auto, OCR, and button positions.")
                                break
                            continue
                        self.log("NON_TARGET stale watchdog skipped; trying normal auto-roll recovery")
                        if self.start_or_recover("Stuck Recovery"):
                            continue
                        if self.recovery_failed_should_stop(
                            "Stuck Recovery",
                            "no OCR/button activity signal after non-target stale recovery verification",
                        ):
                            self.alert_macro_stopped("No stat change after repeated recovery attempts. Check the OCR region, button positions, and passive shards.")
                            break

                elif state in ("BAD", "DISABLED", "HIGH_VALUE"):
                    miss_text = " | ".join(missing) if missing else "target stats not met"
                    self.set_status(f"Skipping {display_trait(trait)} | {miss_text[:60]}")
                    if state in ("BAD", "HIGH_VALUE") and near:
                        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                        distance = self._near_miss_distance_from_summary(trait, summary)
                        self.on_near_miss(stamp, trait, summary, "", miss_text, distance)
                        self.send_near_miss_alert(trait, summary, miss_text, distance)
                    self.clear_recovery_failures(f"roll evaluated as {state}")
                    if state == "HIGH_VALUE":
                        self._set_terminal_stop_reason(f"High value roll: {display_trait(trait)}")
                        self.set_status(f"HIGH VALUE | {display_trait(trait)}")
                        break
                    if self.roll_domain == "powers" and state == "BAD":
                        confirm_started = time.perf_counter()
                        fast_confirm = self._power_bad_fast_confirm_allowed(trait)
                        confirmed_bad = self._confirm_power_bad_before_manual_reroll(
                            trait,
                            missing,
                            context="Loop Power BAD manual reroll",
                            fast_first=fast_confirm,
                        )
                        bad_confirm_elapsed = time.perf_counter() - confirm_started
                        self._record_timing_event(
                            "bad_confirm",
                            bad_confirm_elapsed,
                            domain="powers",
                            route="fast" if fast_confirm else "fallback",
                            result="confirmed" if confirmed_bad else "deferred",
                            trait=power_display_name(trait) if trait else "unknown",
                        )
                        if not confirmed_bad:
                            self.set_status("ROLLING | Power BAD confirmation deferred")
                            if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "deferred power BAD loop delay"):
                                break
                            continue
                    reroll_reason = f"bad power {trait}" if self.roll_domain == "powers" else f"bad {trait}"
                    manual_started = time.perf_counter()
                    if not self.manual_reroll_flow(reroll_reason):
                        manual_elapsed = time.perf_counter() - manual_started
                        if self.recovery_failed_should_stop(
                            "Manual Reroll Auto Resume",
                            self._manual_reroll_failure_reason(),
                        ):
                            self.alert_macro_stopped("Manual reroll could not safely resume Auto after repeated attempts. Check Auto, OCR, and button positions.")
                            break
                        continue
                    manual_elapsed = time.perf_counter() - manual_started
                else:
                    self.set_status(f"ROLLING | {current_text[:48]}")

                    if self.popup_active():
                        self.log("Popup detected while rolling, confirming it")
                        self.confirm_popup_if_present("rolling popup")

                    elif self.banner_active():
                        self.log("Banner detected, trying auto-roll recovery")
                        if not self.start_or_recover("Banner Recovery"):
                            if self.recovery_failed_should_stop(
                                "Banner Recovery",
                                "banner remained or rolling activity could not be confirmed",
                            ):
                                self.alert_macro_stopped("Banner recovery failed after repeated attempts. The macro may be blocked or out of passive shards.")
                                break

                    elif time.time() - self.last_change > self.cfg["STUCK_TIMEOUT"]:
                        idle_for = time.time() - self.last_change
                        self.log(
                            f"Stuck timeout triggered after {idle_for:.1f}s "
                            f"(threshold={float(self.cfg['STUCK_TIMEOUT']):.1f}s), trying auto-roll recovery"
                        )
                        watchdog_result = self.unexpected_not_rolling_watchdog(
                            current_text,
                            state,
                            trait,
                            idle_for,
                            popup_known_clear=True,
                            banner_known_clear=True,
                        )
                        if watchdog_result == "recovered":
                            if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "post-watchdog loop delay"):
                                break
                            continue
                        if watchdog_result == "off_panel":
                            if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "post-watchdog off-panel loop delay"):
                                break
                            continue
                        if watchdog_result == "failed":
                            if self.recovery_failed_should_stop(
                                "Unexpected No-Roll Watchdog",
                                "auto re-enable did not restore rolling",
                            ):
                                self.alert_macro_stopped("Unexpected no-roll watchdog failed after repeated attempts. Check Auto, OCR, and button positions.")
                                break
                            continue
                        fallback = self.recovery_fallback_evaluate_current_roll("Stuck Recovery")
                        if fallback == "terminal":
                            break
                        if fallback == "recovered":
                            if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "post-recovery loop delay"):
                                break
                            continue
                        if fallback == "failed":
                            if self.recovery_failed_should_stop(
                                "Stuck Recovery",
                                "current-roll manual fallback could not verify rolling",
                            ):
                                self.alert_macro_stopped("Current-roll recovery failed after repeated attempts. Check OCR, button positions, and passive shards.")
                                break
                        elif fallback == "rollable_filler":
                            self.log("Stuck Recovery fallback saw NON_TARGET rollable filler; trying normal auto-roll recovery")
                            if self.start_or_recover("Stuck Recovery"):
                                continue
                            if self.recovery_failed_should_stop(
                                "Stuck Recovery",
                                "no OCR/button activity signal after rollable filler recovery verification",
                            ):
                                self.alert_macro_stopped("No stat change after repeated recovery attempts. Check the OCR region, button positions, and passive shards.")
                                break
                        elif not self.start_or_recover("Stuck Recovery"):
                            if self.recovery_failed_should_stop(
                                "Stuck Recovery",
                                "no OCR/button activity signal after recovery verification",
                            ):
                                self.alert_macro_stopped("No stat change after repeated recovery attempts. Check the OCR region, button positions, and passive shards.")
                                break

                total_elapsed = time.perf_counter() - loop_started
                self._record_timing_event(
                    "loop_total",
                    total_elapsed,
                    state=loop_state,
                    check_roll_ms=int(check_elapsed * 1000),
                    bad_confirm_ms=int(bad_confirm_elapsed * 1000),
                    manual_popup_auto_ms=int(manual_elapsed * 1000),
                    shards_ms=int(shard_elapsed * 1000),
                )
                if total_elapsed >= 2.0 or time.time() - self._last_loop_perf_log >= 30.0:
                    self._last_loop_perf_log = time.time()
                    self.log(
                        "Loop timing | "
                        f"state={loop_state} | check_roll={int(check_elapsed * 1000)}ms | "
                        f"bad_confirm={int(bad_confirm_elapsed * 1000)}ms | "
                        f"manual_popup_auto={int(manual_elapsed * 1000)}ms | "
                        f"shards={int(shard_elapsed * 1000)}ms | total={int(total_elapsed * 1000)}ms"
                    )
                if not self._interruptible_sleep(self.cfg["LOOP_DELAY"], "main loop delay"):
                    break
                self.maybe_update_live_status("running")

            except Exception as e:
                self.log(f"Fatal error: {e}")
                self.alert_macro_stopped(f"Fatal error: {e}")
                break

        self.running = False
        self.set_status("Stopped")
        self.finish_live_status(self._resolved_stop_reason())
        self.log("Bot stopped.")

    def start(self):
        if self.running:
            return
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread and self.thread.is_alive() and threading.current_thread() is not self.thread:
            self.thread.join(timeout=1.5)
