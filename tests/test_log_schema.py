from aelrith_forge.backend.log_schema import classify_log_message, normalize_log_entry, summarize_log_message


def test_classify_startup_failure_as_operator_visible():
    entry = classify_log_message("Initial auto start failed after guarded retry", "error")
    assert entry["category"] == "STARTUP"
    assert entry["operator_visible"] is True
    assert entry["event_type"] == "failure"


def test_normalize_legacy_entry_adds_schema_fields():
    item = {"time": "2026-04-19 23:55:41", "level": "info", "message": "Settings applied."}
    entry = normalize_log_entry(item)
    assert entry is not None
    assert entry["category"] == "SETTINGS"
    assert entry["subsystem"] == "Settings"
    assert entry["summary"] == "Settings applied."


def test_summarize_log_message_truncates_cleanly():
    summary = summarize_log_message({"message": "x" * 300, "category": "OCR"}, limit=40)
    assert len(summary) <= 40
    assert summary.endswith("…")
