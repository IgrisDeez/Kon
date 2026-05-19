import json
import unittest
from pathlib import Path

from aelrith_forge.backend.bot import AelrithForgeBot


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "recovery_traces"


class TraceReplayBot(AelrithForgeBot):
    def __init__(self, fixture):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.cfg["CURRENT_SPEC_MARKER_OCR"] = False
        self.cfg["AUTO_VERIFY_DELAY"] = 0.0
        self.cfg["AUTO_VERIFY_POLL_DELAY"] = 0.0
        self.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
        self.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
        self._interruptible_sleep = lambda *_args, **_kwargs: True
        self.fixture = fixture
        self.auto_state_index = 0
        self.popup_state_index = 0
        self.banner_state_index = 0
        self.stats_index = 0
        self.click_labels = []
        self.set_roll_domain(fixture.get("roll_domain", "specs"))
        self.last_text = fixture.get("baseline", "")
        self.last_trait_seen = fixture.get("trait", "")

    def _begin_startup_context(self, reason="startup"):
        ctx = super()._begin_startup_context(reason)
        for key, value in (self.fixture.get("startup_context") or {}).items():
            ctx[key] = value
        return ctx

    def ocr_region(self, _region, psm=7):
        return self.fixture.get("baseline", "")

    def click(self, coords, label, offset=(0, 0), settle=0.2):
        self.click_labels.append(label)

    def _next_fixture_item(self, key, index_name, default):
        items = list(self.fixture.get(key, []))
        idx = getattr(self, index_name)
        if idx < len(items):
            item = items[idx]
            setattr(self, index_name, idx + 1)
            return item
        return default

    def _auto_state_info(self, state, profile):
        if state == "disabled":
            samples = [
                {"label": "base", "state": "disabled", "reason": "base frame signal without accent", "metrics": {}},
                {"label": "wide", "state": "disabled", "reason": "wide frame signal without accent", "metrics": {}},
                {"label": "tight", "state": "disabled", "reason": "tight frame signal without accent", "metrics": {}},
            ]
            reason = "wide frame signal without accent"
        elif profile == "strong_enabled":
            metrics = {"inner": {"green_ratio": 0.07}, "alt_inner": {"green_ratio": 0.08}}
            samples = [
                {"label": "base", "state": "enabled", "reason": "base inner accent signal", "metrics": metrics},
                {"label": "wide", "state": "enabled", "reason": "wide inner accent signal", "metrics": metrics},
                {"label": "tight", "state": "enabled", "reason": "tight inner accent signal", "metrics": metrics},
            ]
            reason = "inner checkbox accent signal"
        else:
            samples = [
                {"label": "base", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {}},
                {"label": "wide", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {}},
                {"label": "tight", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {}},
            ]
            reason = "all checkbox samples ambiguous"
        return {
            "state": state,
            "reason": reason,
            "samples": samples,
            "raw_point": tuple(self.cfg["AUTO_CHECKBOX"]),
            "left_nudge": int(self.cfg.get("AUTO_LEFT_NUDGE", 0)),
            "click_point": self.auto_checkbox_click_point(),
            "region": self.auto_checkbox_region(),
            "metrics": {},
        }

    def auto_checkbox_state(self):
        item = self._next_fixture_item("auto_states", "auto_state_index", {"state": "unknown", "profile": "ambiguous"})
        state = item.get("state", "unknown")
        profile = item.get("profile", "ambiguous")
        self.last_auto_checkbox_state = self._auto_state_info(state, profile)
        return state

    def popup_active(self, log=False, context="popup", fast=False):
        return bool(self._next_fixture_item("popup_states", "popup_state_index", False))

    def _safe_region_screenshot(self, region):
        return None

    def banner_active(self):
        return bool(self._next_fixture_item("banner_states", "banner_state_index", False))

    def stats_changed(self, baseline, context="Rolling activity", **kwargs):
        events = self.fixture.get("stats_sequence", [])
        if self.stats_index >= len(events):
            raise AssertionError(f"unexpected stats_changed context: {context}")
        event = events[self.stats_index]
        self.stats_index += 1
        expected_context = event.get("context")
        if expected_context and expected_context != context:
            raise AssertionError(f"expected stats_changed context {expected_context!r}, got {context!r}")
        details = dict(event.get("details") or {})
        details.setdefault("classification", event.get("state", "rolling" if event.get("changed") else "not_rolling"))
        details.setdefault("confirmed", bool(event.get("changed")))
        details.setdefault("rejection_reason", event.get("reason", "none"))
        details.setdefault("signal_sources", list(details.get("signal_sources") or []))
        details.setdefault("image_changed_samples", int(details.get("image_changed_samples", 0)))
        details.setdefault("max_change_score", float(details.get("max_change_score", 0.0)))
        details.setdefault("sample_text", event.get("text", baseline))
        self.last_recovery_verify_unreadable = bool(event.get("unreadable", False))
        self.last_recovery_verify_state = event.get("state", "rolling" if event.get("changed") else "not_rolling")
        self.last_recovery_reason = event.get("reason", "none")
        self.last_recovery_verify_details = details
        return bool(event.get("changed")), event.get("text", baseline)


class RecoveryTraceReplayTests(unittest.TestCase):
    def load_fixture(self, name):
        return json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))

    def run_fixture(self, name):
        fixture = self.load_fixture(name)
        bot = TraceReplayBot(fixture)
        if fixture["entrypoint"] == "start_or_recover":
            result = bot.start_or_recover(fixture.get("label", "Initial Auto Start"))
        elif fixture["entrypoint"] == "manual_reroll_flow":
            result = bot.manual_reroll_flow(fixture.get("reason", "bad mythical"))
        elif fixture["entrypoint"] == "unexpected_not_rolling_watchdog":
            result = bot.unexpected_not_rolling_watchdog(
                fixture.get("current_text", ""),
                fixture.get("state", "NON_TARGET"),
                fixture.get("trait", ""),
                fixture.get("idle_for", 10.0),
                allow_early=bool(fixture.get("allow_early", False)),
            )
        else:
            raise AssertionError(f"unsupported entrypoint {fixture['entrypoint']!r}")
        return fixture, bot, result

    def assert_snapshot(self, actual, expected):
        for key, value in expected.items():
            self.assertEqual(actual.get(key), value, f"snapshot mismatch for {key}")

    def test_recovery_trace_replay_fixtures(self):
        fixture_names = [
            "powers_startup_non_target_auto_enabled",
            "powers_startup_non_target_auto_disabled",
            "powers_startup_non_target_auto_unknown",
            "powers_manual_reroll_ambiguous_auto_resume",
            "watchdog_weak_readable_nonconfirming",
            "watchdog_disconnect_screen_skips_recovery",
            "watchdog_maintenance_screen_skips_recovery",
        ]
        for name in fixture_names:
            with self.subTest(name=name):
                fixture, bot, result = self.run_fixture(name)
                self.assertEqual(result, fixture["expected"]["result"])
                snapshot = (
                    bot.last_startup_route_snapshot
                    if fixture["expected"]["snapshot_type"] == "startup"
                    else bot.last_recovery_route_snapshot
                )
                self.assertSnapshotEqual(snapshot, fixture["expected"]["snapshot"])
                self.assertEqual(bot.click_labels, fixture["expected"]["click_labels"])

    def assertSnapshotEqual(self, actual, expected):
        self.assert_snapshot(actual, expected)
