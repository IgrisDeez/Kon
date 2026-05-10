from __future__ import annotations

import re
from typing import Any


def _match_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def classify_log_message(message: str, level: str = "info") -> dict[str, Any]:
    raw = str(message or "").strip()
    lowered = raw.lower()

    category = "RUNTIME"
    subsystem = "Runtime"

    if _match_any(lowered, ("discord", "webhook")):
        category, subsystem = "WEBHOOK", "Webhook"
    elif _match_any(lowered, ("[startup", "startup ", "initial auto start", "startup cleanup", "startup auto", "startup verify", "startup fallback", "startup route")):
        category, subsystem = "STARTUP", "Startup"
    elif _match_any(lowered, ("ocr", "tesseract", "current spec marker", "current-spec", "psm6", "psm7")):
        category, subsystem = "OCR", "OCR"
    elif _match_any(lowered, ("recovery", "manual reroll", "fallback", "popup", "checkbox", "auto resume", "safe filler")):
        category, subsystem = "RECOVERY", "Recovery"
    elif _match_any(lowered, ("god roll", "near miss", "kept roll", "passive shards", "passive shard", "current roll", "auto-roll active", "rolling activity")):
        category, subsystem = "ROLL", "Roll"
    elif _match_any(lowered, ("decision", "classification", "current spec is", "current spec=")):
        category, subsystem = "DECISION", "Decision"
    elif _match_any(lowered, ("settings", "preset", "mode set", "desired targets applied", "config path")):
        category, subsystem = "SETTINGS", "Settings"
    elif _match_any(lowered, ("history", "copied selected history row", "exported history", "cleared", "near-miss history")):
        category, subsystem = "HISTORY", "History"
    elif _match_any(lowered, ("picked ", "preview", "capture ", "manual debug report", "manual popup detection", "manual settings reset", "test ")):
        category, subsystem = "USER", "Operator"

    event_type = "info"
    if _match_any(lowered, ("sent successfully", "update sent successfully", "delivery is working", "created")):
        event_type = "send_success"
    elif _match_any(lowered, ("failed", "error", "fatal", "could not")):
        event_type = "failure"
    elif _match_any(lowered, ("skipping", "skipped", "suppressed", "suppression")):
        event_type = "skipped"
    elif _match_any(lowered, ("loaded successfully", "loaded", "migrated")):
        event_type = "loaded"
    elif _match_any(lowered, ("applied", "set to")):
        event_type = "applied"
    elif _match_any(lowered, ("started", "starting")):
        event_type = "started"
    elif _match_any(lowered, ("complete", "completed", "finished")):
        event_type = "completed"
    elif _match_any(lowered, ("confirmed", "validated", "active", "succeeded")):
        event_type = "confirmed"
    elif _match_any(lowered, ("accepted",)):
        event_type = "accepted"
    elif _match_any(lowered, ("weak", "ambiguous", "uncertain", "marginal")):
        event_type = "weak"
    elif _match_any(lowered, ("partial", "fragment", "fragmentary")):
        event_type = "partial"
    elif _match_any(lowered, ("rejected", "did not", "unreadable", "garbage ocr")):
        event_type = "rejected"
    elif _match_any(lowered, ("fallback",)):
        event_type = "fallback"

    if category == "ROLL":
        if "god roll" in lowered:
            event_type = "god_roll"
        elif "near miss" in lowered:
            event_type = "near_miss"
        elif "passive shard" in lowered:
            event_type = "shard_update"
    elif category == "WEBHOOK":
        if "live status" in lowered:
            event_type = "live_status"
        elif "test" in lowered:
            event_type = "test"
    elif category == "STARTUP":
        if "reliability" in lowered:
            event_type = "reliability"
        elif "preflight" in lowered:
            event_type = "preflight"
        elif "failed" in lowered:
            event_type = "failure"
    elif category == "OCR":
        if "accepted" in lowered:
            event_type = "accepted"
        elif _match_any(lowered, ("weak", "ambiguous", "uncertain", "marginal")):
            event_type = "weak"
        elif _match_any(lowered, ("partial", "fragment", "fragmentary")):
            event_type = "partial"
        elif _match_any(lowered, ("rejected", "unreadable", "garbage ocr", "did not find marker")):
            event_type = "rejected"
        elif "fallback" in lowered:
            event_type = "fallback"
    elif category == "RECOVERY":
        if "manual reroll" in lowered:
            event_type = "manual_reroll"
        elif "popup" in lowered:
            event_type = "popup_flow"
        elif "fallback" in lowered:
            event_type = "fallback"

    operator_visible = False
    if level in {"warn", "error"}:
        operator_visible = True
    elif category in {"STARTUP", "RECOVERY", "ROLL"}:
        operator_visible = True
    elif category == "OCR" and event_type in {"accepted", "weak", "partial", "rejected", "fallback"}:
        operator_visible = True
    elif category == "WEBHOOK" and event_type in {"failure", "skipped", "test"}:
        operator_visible = True

    if _match_any(lowered, ("mode set to", "no old runtime backup logs found", "cleaned ")) and level == "info":
        operator_visible = False
    if _match_any(lowered, ("settings loaded successfully", "settings applied", "desired targets applied", "loaded preset", "picked ", "copied selected history row", "exported history")):
        operator_visible = False
    if _match_any(lowered, ("discord update sent successfully", "discord webhook sent successfully", "discord live status updated", "deleted local screenshot after discord upload")):
        operator_visible = False

    event_code = f"{category}_{event_type}".upper()
    return {
        "category": category,
        "subsystem": subsystem,
        "event_type": event_type,
        "event_code": event_code,
        "operator_visible": operator_visible,
    }


def summarize_log_message(entry: dict[str, Any], limit: int = 160) -> str:
    text = str(entry.get("message", "") or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("Desired targets applied | ", "Targets applied | ")
    text = text.replace("Discord webhook sent successfully", "Discord delivery succeeded")
    text = text.replace("Discord update sent successfully", "Discord update sent")
    text = text.replace("Discord live status snapshot sent", "Live status snapshot sent")
    text = text.replace("Discord live status updated", "Live status updated")
    text = text.replace("Session stop summary | ", "Session summary | ")
    if "Source:" in text and entry.get("category") == "SETTINGS":
        text = text.split("Source:", 1)[0].rstrip(" .")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def normalize_log_entry(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    time_text = str(item.get("time", "") or "")
    level = str(item.get("level", "info") or "info").lower()
    if level not in {"info", "ok", "warn", "error"}:
        level = "info"
    message = str(item.get("message", "") or "")
    classified = classify_log_message(message, level)
    category = str(item.get("category") or classified["category"])
    subsystem = str(item.get("subsystem") or classified["subsystem"])
    event_type = str(item.get("event_type") or classified["event_type"])
    event_code = str(item.get("event_code") or f"{category}_{event_type}".upper())
    operator_visible = bool(item.get("operator_visible", classified["operator_visible"]))
    summary = str(item.get("summary") or summarize_log_message({"message": message, "category": category}, 160))
    return {
        "time": time_text,
        "level": level,
        "category": category,
        "subsystem": subsystem,
        "event_type": event_type,
        "event_code": event_code,
        "operator_visible": operator_visible,
        "message": message,
        "summary": summary,
    }
