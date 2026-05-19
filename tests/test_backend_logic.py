import json
import shlex
import time
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import aelrith_forge.backend.bot as bot_module
import aelrith_forge.backend.controller as controller_module
from aelrith_forge import APP_DISPLAY_NAME, APP_PUBLIC_VERSION, APP_VERSION
from aelrith_forge.version import APP_PUBLIC_VERSION as PUBLIC_VERSION_METADATA
from aelrith_forge.version import APP_VERSION as VERSION_METADATA
from aelrith_forge.backend.bot import (
    AelrithForgeBot,
    DEFAULT_REAL_RULES,
    parse_passive_shard_count,
    parse_power_shard_count,
    sanitize_rules,
)
from aelrith_forge.backend.controller import BotController, CURRENT_SETTINGS_VERSION, GodRollEntry, NearMissEntry, default_settings
from aelrith_forge.backend.log_schema import normalize_log_entry
from aelrith_forge.backend.normalization import canonical_stat_key, normalize_ocr_text, normalize_stat_tokens


class StubBot(AelrithForgeBot):
    def __init__(self, candidates):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.cfg["CURRENT_SPEC_MARKER_OCR"] = False
        self._candidates = candidates

    def get_stats_ocr_candidates(self, *args, **kwargs):
        if kwargs.get("fallback_only"):
            return []
        return self._candidates


class FastLoopCandidateBot(AelrithForgeBot):
    def __init__(self, fast_candidates, primary_candidates=None, fallback_candidates=None, signature="sig"):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.cfg["CURRENT_SPEC_MARKER_OCR"] = False
        self.fast_candidates = list(fast_candidates)
        self.primary_candidates = list(primary_candidates or [])
        self.fallback_candidates = list(fallback_candidates or [])
        self.signature = signature
        self.calls = []

    def get_stats_ocr_candidates(self, *args, **kwargs):
        self.calls.append(dict(kwargs))
        self._last_stats_ocr_signature = self.signature
        if kwargs.get("fallback_only"):
            return list(self.fallback_candidates)
        if kwargs.get("fast_loop"):
            return list(self.fast_candidates)
        return list(self.primary_candidates)


class SequentialCandidateBot(AelrithForgeBot):
    def __init__(self, candidate_batches):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.cfg["CURRENT_SPEC_MARKER_OCR"] = False
        self.cfg["PARTIAL_TARGET_CONFIRM_DELAY"] = 0.0
        self.candidate_batches = list(candidate_batches)
        self.candidate_calls = 0

    def get_stats_ocr_candidates(self, *args, **kwargs):
        if kwargs.get("fallback_only"):
            return []
        index = min(self.candidate_calls, len(self.candidate_batches) - 1)
        self.candidate_calls += 1
        return self.candidate_batches[index]


class ActivityStubBot(AelrithForgeBot):
    def __init__(self, samples):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.samples = list(samples)
        self.cfg["AUTO_VERIFY_POLLS"] = max(1, len(self.samples))
        self.cfg["AUTO_VERIFY_POLL_DELAY"] = 0.0

    def ocr_region(self, _region, psm=7):
        if self.samples:
            return self.samples.pop(0)
        return ""

    def _ocr_tesseract_image(self, _image, psm=7):
        return self.ocr_region(None, psm=psm)

    def popup_active(self, log=False, context="popup"):
        return False

    def banner_active(self):
        return False

    def get_stats_ocr_candidates(self, *args, **kwargs):
        return []


class RecoveryFallbackStubBot(AelrithForgeBot):
    def __init__(self, state_tuple):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.state_tuple = state_tuple
        self.manual_calls = 0
        self.verify_calls = 0

    def check_roll(self):
        return self.state_tuple

    def manual_reroll_flow(self, reason="bad mythical"):
        self.manual_calls += 1
        return True

    def stats_changed(self, baseline, context="Rolling activity", ui_signals=None):
        self.verify_calls += 1
        return True, "current spec rampage combo ramp 20 damage 20 crit chance 3 crit damage 7"


class PopupStubBot(AelrithForgeBot):
    def __init__(self, samples):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.samples = list(samples)
        self.clicks = []

    def ocr_region(self, _region, psm=7):
        if self.samples:
            return self.samples.pop(0)
        return ""

    def click(self, coords, label, offset=(0, 0), settle=0.2):
        self.clicks.append((coords, label, offset, settle))


class PassiveShardStubBot(AelrithForgeBot):
    def __init__(self, attempts):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.cfg["PASSIVE_SHARD_REGION"] = (921, 376, 124, 27)
        self.attempts = attempts

    def passive_shard_ocr_attempts(self, image=None, region=None):
        return {
            "region": tuple(region or self.cfg["PASSIVE_SHARD_REGION"]),
            "ocr_region": (917, 372, 132, 35),
            "image": None,
            "processed_image": None,
            "attempts": self.attempts,
        }


class PowerShardStubBot(AelrithForgeBot):
    def __init__(self, attempts):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.cfg["POWER_SHARD_REGION"] = (921, 376, 124, 27)
        self.attempts = attempts

    def power_shard_ocr_attempts(self, image=None, region=None):
        return {
            "region": tuple(region or self.cfg["POWER_SHARD_REGION"]),
            "ocr_region": (917, 372, 132, 35),
            "image": None,
            "processed_image": None,
            "attempts": self.attempts,
        }


class FakeScreenshot:
    def save(self, path):
        Path(path).write_bytes(b"fake-png")


class FakePyAutoGui:
    @staticmethod
    def screenshot(*_args, **_kwargs):
        return FakeScreenshot()


@contextmanager
def controller_storage(temp_dir):
    root = Path(temp_dir)
    old_paths = {
        "SETTINGS_FILE": controller_module.SETTINGS_FILE,
        "HISTORY_FILE": controller_module.HISTORY_FILE,
        "NEAR_MISS_FILE": controller_module.NEAR_MISS_FILE,
        "LOG_FILE": controller_module.LOG_FILE,
        "CONFIG_BACKUP_DIR": controller_module.CONFIG_BACKUP_DIR,
        "LIVE_PROOF_DIR": controller_module.LIVE_PROOF_DIR,
    }
    controller_module.SETTINGS_FILE = root / "config" / "aelrith_forge_settings.json"
    controller_module.HISTORY_FILE = root / "output" / "json" / "aelrith_forge_history.json"
    controller_module.NEAR_MISS_FILE = root / "output" / "json" / "aelrith_forge_near_misses.json"
    controller_module.LOG_FILE = root / "output" / "logs" / "aelrith_forge_logs.json"
    controller_module.CONFIG_BACKUP_DIR = root / "config" / "backups"
    controller_module.LIVE_PROOF_DIR = root / "output" / "diagnostics" / "live_proof"
    try:
        controller_module.SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        yield controller_module.SETTINGS_FILE
    finally:
        for name, value in old_paths.items():
            setattr(controller_module, name, value)


class BackendLogicTests(unittest.TestCase):
    def make_bot(self):
        bot = AelrithForgeBot(lambda *_: None, lambda *_: None)
        bot.set_rules(DEFAULT_REAL_RULES)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["CURRENT_SPEC_MARKER_OCR"] = False
        return bot

    def saved_default_settings(self):
        controller = BotController.__new__(BotController)
        return json.loads(json.dumps(controller.normalize_settings(default_settings())))

    def force_strong_enabled_checkbox(self, bot):
        bot._auto_checkbox_confidence_tier = lambda: "strong_enabled"

    def apply_subjugator_luck_target(self, bot):
        bot.set_roll_domain("powers")
        bot.set_power_rules(
            {
                "subjugator": [
                    (0.0, 40.0),
                    (0.0, 40.0),
                    (0.0, 3.5),
                    (0.0, 13.0),
                    (17.0, 17.5),
                    (0.0, 20.0),
                ]
            }
        )

    def evaluate_power_text(self, bot, text, source_name="unit"):
        parsed = bot_module.parse_power_roll_text(text)
        self.assertIsNotNone(parsed)
        return bot.evaluate_power_trait_with_values(
            parsed["power"],
            parsed["values"],
            text,
            source_name=source_name,
            passive=parsed.get("passive"),
        )

    def test_rules_are_clamped_to_hard_caps(self):
        rules = sanitize_rules(
            {
                "fortune": [(31.0, 40.0), (-1.0, 12.0)],
                "chosen": [(29.0, 30.0), (9.0, 10.0)],
                "executioner": [(44.0, 99.0), (5.0, 0.0), (14.0, 30.0)],
                "rampage": [(15.0, 99.0), (29.0, 99.0), (3.0, 99.0), (9.0, 99.0)],
            }
        )
        self.assertEqual(rules["fortune"], [(30.0, 30.0), (0.0, 10.0)])
        self.assertEqual(rules["executioner"], [(44.0, 45.0), (4.0, 4.0), (14.0, 15.0)])
        self.assertEqual(rules["rampage"], [(15.0, 30.0), (29.0, 30.0), (3.0, 4.0), (9.0, 10.0)])

    def test_auto_checkbox_click_point_and_region_share_anchor(self):
        bot = self.make_bot()
        bot.cfg["AUTO_CHECKBOX"] = (1210, 629)
        bot.cfg["AUTO_LEFT_NUDGE"] = 10
        self.assertEqual(bot.auto_checkbox_click_point(), (1200, 629))
        self.assertEqual(bot.auto_checkbox_region(), (1178, 607, 44, 44))

        bot.cfg["AUTO_LEFT_NUDGE"] = 20
        self.assertEqual(bot.auto_checkbox_click_point(), (1190, 629))
        self.assertEqual(bot.auto_checkbox_region(), (1168, 607, 44, 44))

    def test_auto_checkbox_classifier_recognizes_enabled_and_disabled_crops(self):
        if bot_module.Image is None:
            self.skipTest("Pillow not available")
        bot = self.make_bot()

        green = bot_module.Image.new("RGB", (44, 44), (24, 24, 24))
        green.paste((20, 190, 60), (17, 17, 27, 27))
        self.assertEqual(bot._classify_auto_checkbox_image(green)[0], "enabled")

        blue = bot_module.Image.new("RGB", (44, 44), (24, 24, 24))
        blue.paste((50, 120, 220), (17, 17, 27, 27))
        self.assertEqual(bot._classify_auto_checkbox_image(blue)[0], "enabled")

        sky_background = bot_module.Image.new("RGB", (44, 44), (125, 135, 170))
        state, details = bot._classify_auto_checkbox_image(sky_background)
        self.assertEqual(state, "unknown")
        self.assertEqual(details["reason"], "broad blue background rejected")

        disabled = bot_module.Image.new("RGB", (44, 44), (20, 20, 20))
        disabled.paste((225, 225, 225), (0, 0, 44, 3))
        disabled.paste((225, 225, 225), (0, 41, 44, 44))
        disabled.paste((225, 225, 225), (0, 0, 3, 44))
        disabled.paste((225, 225, 225), (41, 0, 44, 44))
        self.assertEqual(bot._classify_auto_checkbox_image(disabled)[0], "disabled")

        grayscale_disabled = bot_module.Image.new("RGB", (44, 44), (18, 20, 34))
        grayscale_disabled.paste((92, 94, 108), (9, 9, 35, 35))
        grayscale_disabled.paste((155, 156, 170), (10, 10, 34, 13))
        grayscale_disabled.paste((155, 156, 170), (10, 31, 34, 34))
        grayscale_disabled.paste((155, 156, 170), (10, 10, 13, 34))
        grayscale_disabled.paste((155, 156, 170), (31, 10, 34, 34))
        state, details = bot._classify_auto_checkbox_image(grayscale_disabled)
        self.assertEqual(state, "disabled")
        self.assertEqual(details["reason"], "unchecked grayscale frame signal")

        dark_blank = bot_module.Image.new("RGB", (44, 44), (18, 20, 28))
        self.assertEqual(bot._classify_auto_checkbox_image(dark_blank)[0], "unknown")

        ambiguous = bot_module.Image.new("RGB", (44, 44), (128, 128, 128))
        self.assertEqual(bot._classify_auto_checkbox_image(ambiguous)[0], "unknown")

    def test_auto_checkbox_observability_counts_ambiguous_reads(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.last_auto_checkbox_state = {
            "raw_point": (1210, 629),
            "left_nudge": 10,
            "click_point": (1200, 629),
            "region": (1178, 607, 44, 44),
            "reason": "unit ambiguous classifier",
            "samples": [{"label": "inner", "state": "unknown", "reason": "flat crop"}],
        }
        bot._auto_checkbox_confidence_tier = lambda: "ambiguous"

        bot._log_auto_checkbox_state_read("Manual Reroll Auto Resume", 1, "unknown")
        summary = bot.auto_checkbox_session_summary()

        self.assertEqual(summary["reads"], 1)
        self.assertEqual(summary["ambiguous_reads"], 1)
        self.assertEqual(summary["manual_reroll_direct_recovery_clicks"], 0)
        self.assertEqual(summary["latest_classifier"]["context"], "Manual Reroll Auto Resume")
        self.assertEqual(summary["latest_classifier"]["state"], "unknown")

    def test_legacy_rampage_ranges_are_repaired(self):
        rules = sanitize_rules(
            {
                "rampage": [(19.3, 30.0), (1.0, 4.0), (4.0, 4.0), (9.0, 10.0)],
            }
        )
        self.assertEqual(rules["rampage"], [(19.3, 30.0), (29.0, 30.0), (4.0, 4.0), (9.0, 10.0)])

    def test_activity_detection_accepts_stat_number_change_without_current_spec(self):
        bot = ActivityStubBot(["DamageI>Damage6.7%", "DamageI>Damage6.8%"])
        bot._ocr_tesseract_image = lambda _image, psm=7: bot.ocr_region(None, psm=psm)
        changed, sample = bot.stats_changed("DamageI>Damage6.7%", context="unit activity")
        self.assertFalse(changed)
        self.assertEqual(sample, "DamageI>Damage6.7%")
        self.assertEqual(bot.last_recovery_verify_details.get("rejection_reason"), "no_material_change")
        self.assertTrue(any("unreliable_stats_samples=0/2" in message for message in bot.messages))

    def test_recovery_rejects_same_trait_seen_without_material_change(self):
        bot = ActivityStubBot(
            [
                "rampage combo ramp 26.5 damage 28.4 crit chance 3.2 crit damage 7.2",
                "rampage combo ramp 26.5 damage 28.4 crit chance 3.2 crit damage 7.2",
            ]
        )
        bot._ocr_tesseract_image = lambda _image, psm=7: bot.ocr_region(None, psm=psm)
        changed, _sample = bot.stats_changed(
            "rampage combo ramp 26.5 damage 28.4 crit chance 3.2 crit damage 7.2",
            context="unit recovery",
        )
        self.assertFalse(changed)
        self.assertEqual(bot.last_recovery_verify_state, "not_rolling")
        self.assertEqual(bot.last_recovery_verify_details.get("rejection_reason"), "no_material_change")
        self.assertTrue(any("classification=not_rolling" in message for message in bot.messages))
        self.assertTrue(any("rejection_reason=no_material_change" in message for message in bot.messages))

    def test_recovery_does_not_confirm_trait_only_sample(self):
        bot = ActivityStubBot(["rampage", "rampage"])
        bot._ocr_tesseract_image = lambda _image, psm=7: bot.ocr_region(None, psm=psm)
        changed, _sample = bot.stats_changed("", context="unit recovery")
        self.assertFalse(changed)
        self.assertEqual(bot.last_recovery_verify_state, "not_rolling")
        self.assertEqual(bot.last_recovery_verify_details.get("rejection_reason"), "trait_only_sample")
        self.assertTrue(any("classification=not_rolling" in message for message in bot.messages))
        self.assertTrue(any("rejection_reason=trait_only_sample" in message for message in bot.messages))

    def test_recovery_treats_repeated_junk_ocr_as_unreliable_after_button_flow(self):
        bot = ActivityStubBot(["ve ore", "", "ve ore", ""])
        changed, sample = bot.stats_changed(
            "ve ore",
            context="unit recovery",
            ui_signals=["manual_reroll_flow_completed"],
        )
        self.assertTrue(changed)
        self.assertEqual(sample, "ve ore")
        self.assertTrue(any("stats_ocr_unreliable_after_ui_flow" in message for message in bot.messages))

    def test_watchdog_rejects_repeated_control_text_after_auto_reenable(self):
        bot = ActivityStubBot(["orCode:279", "OCRPass", "StartPowers"])
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._ocr_tesseract_image = lambda _image, psm=7: bot.ocr_region(None, psm=psm)
        old_pyautogui = bot_module.pyautogui
        try:
            bot_module.pyautogui = None
            changed, returned = bot.stats_changed(
                "orCode:279",
                context="Unexpected No-Roll Watchdog verify",
                ui_signals=["watchdog_auto_reenable"],
                polls_override=3,
                poll_delay_override=0.0,
            )
        finally:
            bot_module.pyautogui = old_pyautogui

        self.assertFalse(changed)
        self.assertEqual(returned, "orCode:279")
        self.assertEqual(bot.last_recovery_verify_state, "not_rolling")
        self.assertEqual(bot.last_recovery_reason, "stats_region_off_target_ui_text")
        self.assertTrue(any("Current roll OCR region appears misconfigured" in message for message in bot.messages))
        self.assertFalse(any("stats_ocr_unreliable_after_ui_flow:watchdog_auto_reenable" in message for message in bot.messages))

    def test_watchdog_rejects_unreliable_non_control_text_after_auto_reenable(self):
        bot = ActivityStubBot(["ve ore", "", "ve ore"])
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._ocr_tesseract_image = lambda _image, psm=7: bot.ocr_region(None, psm=psm)
        old_pyautogui = bot_module.pyautogui
        try:
            bot_module.pyautogui = None
            changed, _returned = bot.stats_changed(
                "ve ore",
                context="Unexpected No-Roll Watchdog verify",
                ui_signals=["watchdog_auto_reenable"],
                polls_override=3,
                poll_delay_override=0.0,
            )
        finally:
            bot_module.pyautogui = old_pyautogui

        self.assertFalse(changed)
        self.assertEqual(bot.last_recovery_reason, "stats_ocr_unreliable_after_watchdog")

    def test_recovery_rejects_garbage_ocr_without_button_flow(self):
        bot = ActivityStubBot(["2", "-- eeeeas", "2", "-- eeeeas"])
        bot._ocr_tesseract_image = lambda _image, psm=7: bot.ocr_region(None, psm=psm)
        old_pyautogui = bot_module.pyautogui
        try:
            bot_module.pyautogui = None
            changed, _sample = bot.stats_changed("ve ore", context="unit recovery")
            self.assertFalse(changed)
            self.assertEqual(bot.last_recovery_verify_state, "unreadable_static")
            self.assertEqual(bot.last_recovery_verify_details.get("rejection_reason"), "unreadable_context")
            self.assertTrue(any("rejected garbage OCR" in message for message in bot.messages))
        finally:
            bot_module.pyautogui = old_pyautogui

    def test_stats_changed_reuses_one_stats_screenshot_per_poll_for_ocr_and_candidates(self):
        class CountingPyAutoGui:
            calls = []

            @classmethod
            def screenshot(cls, *args, **kwargs):
                image = object()
                cls.calls.append((args, kwargs, image))
                return image

        bot = self.make_bot()
        old_pyautogui = bot_module.pyautogui
        candidate_images = []
        ocr_images = []
        try:
            bot_module.pyautogui = CountingPyAutoGui
            bot._popup_active_checked = lambda *args, **kwargs: False
            bot.banner_active = lambda: False
            bot._region_signature = lambda image: id(image)
            bot._region_change_score = lambda _first, _second: 0.0
            bot._ocr_tesseract_image = lambda image, psm=7: ocr_images.append(image) or "current spec damagei damage 5"

            def fake_candidates(*_args, **kwargs):
                candidate_images.append(kwargs.get("image"))
                return []

            bot.get_stats_ocr_candidates = fake_candidates

            changed, _text = bot.stats_changed(
                "current spec damagei damage 5",
                context="Initial Auto Start unit cache",
                polls_override=1,
                poll_delay_override=0.0,
                post_popup_check_enabled=False,
            )
        finally:
            bot_module.pyautogui = old_pyautogui

        self.assertFalse(changed)
        self.assertEqual(len(CountingPyAutoGui.calls), 2)
        self.assertIs(ocr_images[0], CountingPyAutoGui.calls[1][2])
        self.assertIs(candidate_images[0], CountingPyAutoGui.calls[1][2])
        self.assertEqual(bot.last_verification_cache_stats["cache_misses"], 1)
        self.assertGreaterEqual(bot.last_verification_cache_stats["cache_hits"], 1)
        self.assertEqual(bot.recent_route_budget_events[-1]["name"], "startup_verify_budget")

    def test_recovery_outcome_helper_classifies_readable_insufficient_change(self):
        bot = self.make_bot()
        classification, rejection_reason = bot._recovery_failure_outcome(
            [
                {
                    "cleaned": "rampage combo ramp damage crit chance crit damage alpha beta",
                    "unreliable": False,
                    "trait_only": False,
                    "materially_different": True,
                }
            ],
            "rampage combo ramp damage crit chance crit damage",
            1,
            0,
        )
        self.assertEqual(classification, "not_rolling")
        self.assertEqual(rejection_reason, "readable_insufficient_change")

    def test_recovery_outcome_helper_classifies_unreadable_but_changed(self):
        bot = self.make_bot()
        classification, rejection_reason = bot._recovery_failure_outcome(
            [{"cleaned": "", "unreliable": True, "trait_only": False, "materially_different": False}],
            "",
            1,
            1,
        )
        self.assertEqual(classification, "unreadable_but_changed")
        self.assertEqual(rejection_reason, "unreadable_context_with_screen_change")

    def test_recovery_popup_confirmation_records_shared_outcome_fields(self):
        bot = ActivityStubBot(["junk"])
        bot.popup_active = lambda *args, **kwargs: True
        bot.clear_reroll_popup = lambda *args, **kwargs: True
        bot.banner_active = lambda: False
        changed, sample = bot.stats_changed("baseline text", context="unit recovery")
        self.assertTrue(changed)
        self.assertEqual(sample, "baseline text")
        self.assertEqual(bot.last_recovery_verify_state, "rolling")
        self.assertTrue(bot.last_recovery_verify_details.get("confirmed"))
        self.assertEqual(bot.last_recovery_verify_details.get("reason"), "popup_confirmed_before_polling")
        self.assertEqual(bot.last_recovery_verify_details.get("classification"), "rolling")
        self.assertEqual(bot.last_recovery_verify_details.get("signal_sources"), ["popup"])

    def test_recovery_banner_clear_records_shared_outcome_fields(self):
        bot = ActivityStubBot(["junk", "junk"])
        bot._ocr_tesseract_image = lambda _image, psm=7: bot.ocr_region(None, psm=psm)
        bot.popup_active = lambda *args, **kwargs: False
        banner_states = iter([True, False])
        bot.banner_active = lambda: next(banner_states, False)
        changed, sample = bot.stats_changed("baseline text", context="unit recovery")
        self.assertTrue(changed)
        self.assertEqual(sample, "junk")
        self.assertEqual(bot.last_recovery_verify_state, "rolling")
        self.assertTrue(bot.last_recovery_verify_details.get("confirmed"))
        self.assertEqual(bot.last_recovery_verify_details.get("reason"), "banner_cleared")
        self.assertEqual(bot.last_recovery_verify_details.get("classification"), "rolling")
        self.assertEqual(bot.last_recovery_verify_details.get("signal_sources"), ["banner"])

    def test_initial_recovery_fast_fails_repeated_unreadable_samples(self):
        bot = ActivityStubBot(["junk", "ve ore", "2", "-- eeeeas", "still junk"])
        changed, _sample = bot.stats_changed(
            "junk",
            context="Initial Auto Start auto verify",
            polls_override=5,
            poll_delay_override=0.0,
            unreadable_fast_fail_polls=3,
        )
        self.assertFalse(changed)
        self.assertTrue(bot.last_recovery_verify_unreadable)
        self.assertTrue(any("fast unreadable verify" in message for message in bot.messages))

    def test_recovery_fallback_rerolls_classified_bad_current_spec(self):
        bot = RecoveryFallbackStubBot(
            (
                "BAD",
                "rampage",
                "Combo Ramp 20 | Damage 20 | Crit Rate 3 | Crit Damage 7",
                "current spec rampage combo ramp 20 damage 20 crit chance 3 crit damage 7",
                ["Damage 20 < 29"],
                False,
            )
        )
        result = bot.recovery_fallback_evaluate_current_roll("Unit Recovery")
        self.assertEqual(result, "recovered")
        self.assertEqual(bot.manual_calls, 1)
        self.assertEqual(bot.verify_calls, 1)
        self.assertTrue(any("current spec is BAD" in message for message in bot.messages))

    def test_recovery_fallback_rerolls_disabled_target_current_spec(self):
        bot = RecoveryFallbackStubBot(
            (
                "DISABLED",
                "rampage",
                "Rampage target is disabled",
                "current spec rampage combo ramp 20 damage 20 crit chance 3 crit damage 7",
                ["Target disabled"],
                False,
            )
        )
        result = bot.recovery_fallback_evaluate_current_roll("Unit Recovery")
        self.assertEqual(result, "recovered")
        self.assertEqual(bot.manual_calls, 1)
        self.assertEqual(bot.verify_calls, 1)
        self.assertTrue(any("current spec is DISABLED" in message for message in bot.messages))

    def test_reroll_popup_clear_retries_until_popup_disappears(self):
        bot = PopupStubBot(["reroll sure", "reroll sure", ""])
        self.assertTrue(bot.clear_reroll_popup("unit popup"))
        self.assertEqual(len(bot.clicks), 2)
        self.assertTrue(any("Reroll popup Yes click attempt 2/3" in message for message in bot.messages))
        self.assertTrue(any("Reroll popup cleared" in message for message in bot.messages))

    def test_popup_clear_aborts_when_stop_requested(self):
        bot = PopupStubBot(["reroll sure"])
        bot.stop_event.set()
        self.assertFalse(bot.clear_reroll_popup("unit popup", already_detected=True))
        self.assertEqual(bot.clicks, [])
        self.assertTrue(any("Stop requested during popup clear" in message for message in bot.messages))

    def test_interruptible_sleep_returns_false_on_stop(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.stop_event.set()
        self.assertFalse(bot._interruptible_sleep(1.0, "unit sleep"))
        self.assertTrue(any("Stop requested during unit sleep" in message for message in messages))

    def test_stuck_recovery_fast_fails_unreadable_unclassified_context(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "junk"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.click = lambda *_args, **_kwargs: None
        bot.last_recovery_fallback_unclassified = True
        manual_calls = []

        def fake_stats_changed(*_args, **_kwargs):
            bot.last_recovery_verify_unreadable = True
            return False, "junk"

        bot.stats_changed = fake_stats_changed
        bot.manual_reroll_flow = lambda *_args, **_kwargs: manual_calls.append(True) or True

        self.assertFalse(bot.start_or_recover("Stuck Recovery"))
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("fast-fail" in message for message in messages))

    def test_initial_auto_start_fast_fails_unreadable_context(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "junk"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "enabled"
        bot.click = lambda *_args, **_kwargs: None
        manual_calls = []
        verify_kwargs = []

        def fake_stats_changed(*_args, **_kwargs):
            verify_kwargs.append(_kwargs)
            bot.last_recovery_verify_unreadable = True
            return False, "junk"

        bot.stats_changed = fake_stats_changed
        bot.manual_reroll_flow = lambda *_args, **_kwargs: manual_calls.append(True) or True

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(bot.last_startup_result, "failed_unreadable_ui")
        self.assertEqual(manual_calls, [])
        self.assertEqual(verify_kwargs[0]["polls_override"], 2)
        self.assertEqual(verify_kwargs[0]["unreadable_fast_fail_polls"], 1)
        self.assertTrue(any("Initial Auto Start fast-fail" in message for message in messages))
        self.assertTrue(any("failed_unreadable_ui" in message for message in messages))

    def test_initial_auto_start_skips_checkbox_toggle_when_already_enabled(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)

        def fake_stats_changed(_baseline, context="", **_kwargs):
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            bot.last_recovery_verify_state = "rolling"
            bot.last_recovery_verify_details = {
                "reason": "stat_numbers_changed",
                "signal_sources": ["ocr", "image_change"],
                "image_changed_samples": 1,
                "max_change_score": 9.0,
            }
            bot.last_recovery_reason = "stat_numbers_changed"
            bot.last_recovery_verify_unreadable = False
            return True, "current spec rampage combo ramp 20 damage 20"

        bot.stats_changed = fake_stats_changed
        clicks = []
        bot.click = lambda *_args, **_kwargs: clicks.append((_args, _kwargs))

        self.assertTrue(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(bot.last_startup_result, "confirmed_rolling")
        self.assertEqual(clicks, [])
        self.assertTrue(any("decision=continue_without_toggle" in message for message in messages))
        self.assertFalse(any("Manual reroll flow | initial auto start fallback" in message for message in messages))

    def test_initial_auto_start_clicks_only_when_checkbox_appears_off(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        states = iter(["disabled", "disabled"])
        bot.auto_checkbox_state = lambda: next(states, "enabled")
        bot._auto_checkbox_confidence_tier = lambda: "strong_disabled"

        def fake_stats_changed(_baseline, context="", **_kwargs):
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            bot.last_recovery_verify_state = "rolling"
            bot.last_recovery_verify_details = {
                "reason": "stat_numbers_changed",
                "signal_sources": ["ocr", "image_change"],
                "image_changed_samples": 1,
                "max_change_score": 9.0,
            }
            bot.last_recovery_reason = "stat_numbers_changed"
            bot.last_recovery_verify_unreadable = False
            return True, "current spec rampage combo ramp 20 damage 20"

        bot.stats_changed = fake_stats_changed
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(bot.last_startup_result, "failed_no_roll_detected")
        self.assertEqual(clicks, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))
        self.assertFalse(any("Manual reroll flow | initial auto start fallback" in message for message in messages))
        self.assertTrue(any("result=failed_no_roll_detected" in message for message in messages))

    def test_startup_strong_bad_spec_fast_probe_skips_full_validation(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._begin_startup_context("unit startup")
        calls = []

        def fake_check_roll(allow_fallback=True, startup_fast=False, **_kwargs):
            calls.append((allow_fallback, startup_fast))
            if not startup_fast:
                raise AssertionError("strong startup fast probe should skip full validation")
            bot.last_decision_chain = {
                "parsed_values": {
                    "Combo Ramp": 17.5,
                    "Damage": 17.4,
                    "Crit Rate": 3.8,
                    "Crit Damage": 7.13,
                }
            }
            bot.last_ocr_candidate_debug = {"chosen_source": "unit-fast"}
            return (
                "BAD",
                "rampage",
                "Combo Ramp 17.5 | Damage 17.4 | Crit Rate 3.8 | Crit Damage 7.13",
                "current spec rampage combo ramp 17.5 damage 17.4 crit chance 3.8 crit damage 7.13",
                ["Damage: 17.4 -> 29-30", "Crit Damage: 7.13 -> 9-10"],
                False,
            )

        bot.check_roll = fake_check_roll
        bot.manual_reroll_flow = lambda reason="": True
        bot._manual_reroll_recently_confirmed = lambda *_args, **_kwargs: True

        result = bot.startup_check_current_roll()

        self.assertEqual(result, "rerolled")
        self.assertEqual(calls, [(False, True)])
        self.assertTrue(any("startup_full_validation_skipped=True" in message for message in messages))
        self.assertTrue(any("trusted_startup_fast_spec_probe" in message for message in messages))

    def test_startup_non_target_bridge_probe_uses_single_compact_poll(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._begin_startup_context("unit startup")
        bot.popup_active = lambda *_args, **_kwargs: False
        bot._popup_active_checked = lambda *_args, **_kwargs: False
        stats_calls = []

        def fake_check_roll(allow_fallback=True, startup_fast=False, **_kwargs):
            if not startup_fast:
                raise AssertionError("strong NON_TARGET fast probe should not run full validation")
            return (
                "NON_TARGET",
                "non_target",
                "Unsupported or filler observed; letting Auto continue",
                "current spec swift damage 12 crit damage 5",
                ["Unsupported trait autoskip"],
                False,
            )

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            stats_calls.append((baseline, context, kwargs))
            bot.last_recovery_verify_state = "rolling"
            bot.last_recovery_verify_details = {
                "reason": "popup_confirmed_mid_polling",
                "signal_sources": ["popup"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "popup_confirmed_mid_polling"
            return True, "current spec swift damage 13 crit damage 5"

        bot.check_roll = fake_check_roll
        bot.stats_changed = fake_stats_changed

        result = bot.startup_check_current_roll()

        self.assertEqual(result, "continue")
        self.assertEqual(len(stats_calls), 1)
        _baseline, context, kwargs = stats_calls[0]
        self.assertEqual(context, "Startup fast NON_TARGET trust probe")
        self.assertEqual(kwargs["polls_override"], 1)
        self.assertEqual(kwargs["psm_sequence_override"], (6,))
        self.assertTrue(bot._startup_context["preflight_bypassed"])
        self.assertTrue(any("bridge probe confirmed rolling" in message for message in messages))

    def test_recovery_skips_checkbox_toggle_when_auto_already_enabled(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot.stats_changed = lambda *_args, **_kwargs: (True, "current spec rampage combo ramp 20 damage 20")
        clicks = []
        bot.click = lambda *_args, **_kwargs: clicks.append((_args, _kwargs))

        self.assertTrue(bot.start_or_recover("Stuck Recovery"))
        self.assertEqual(clicks, [])
        self.assertTrue(any("already enabled; skipping toggle" in message for message in messages))

    def test_auto_enable_uncertain_state_does_not_toggle(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *_args, **_kwargs: clicks.append((_args, _kwargs))

        self.assertEqual(bot.ensure_auto_enabled("unit recovery"), "uncertain")
        self.assertEqual(clicks, [])
        self.assertTrue(any("Auto state uncertain; using cautious fallback" in message for message in messages))

    def test_nonstartup_uncertain_auto_enable_clicks_only_after_validation_confirms_off(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        states = iter(["unknown", "unknown", "unknown", "disabled"])
        bot.auto_checkbox_state = lambda: next(states, "enabled")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        self.assertEqual(bot.ensure_auto_enabled("unit recovery", allow_uncertain_enable=True), "clicked")
        self.assertEqual(len(clicks), 1)
        self.assertEqual(clicks[0][0][1], "unit recovery")
        self.assertTrue(any("validation confirmed Auto is off, enabling now" in message for message in messages))

    def test_nonstartup_uncertain_auto_enable_skips_speculative_click_if_validation_stays_unknown(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        states = iter(["unknown", "unknown", "unknown", "unknown"])
        bot.auto_checkbox_state = lambda: next(states, "unknown")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        self.assertEqual(
            bot.ensure_auto_enabled("unit recovery", allow_uncertain_enable=True),
            "uncertain",
        )
        self.assertEqual(clicks, [])
        self.assertTrue(any("skipping speculative checkbox click" in message for message in messages))

    def test_initial_auto_start_unknown_after_retry_sends_one_fallback_click_and_confirms(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "unknown"
        bot.stats_changed = lambda *_args, **_kwargs: (True, "current spec rampage combo ramp 20 damage 20")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(bot.last_startup_result, "failed_no_roll_detected")
        self.assertEqual(clicks, [])
        self.assertTrue(any("Startup auto state uncertain; retrying state detection" in message for message in messages))
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))
        self.assertTrue(any("startup_fallback_click=False" in message for message in messages))
        self.assertTrue(any("cautious_uncertain_click=False" in message for message in messages))

    def test_initial_auto_start_unknown_after_retry_fails_safely_when_not_confirmed(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "unknown"
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True

        def fake_stats_changed(*_args, **_kwargs):
            bot.last_recovery_verify_unreadable = True
            return False, "junk"

        bot.stats_changed = fake_stats_changed
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(bot.last_startup_result, "failed_unreadable_ui")
        self.assertEqual(clicks, [])
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))
        self.assertTrue(any("startup_fallback_click=False" in message for message in messages))
        self.assertFalse(any("Restore Auto" in str(call) for call in clicks))


    def test_repeated_initial_auto_start_unknown_state_clicks_once_per_attempt_without_restore_loop(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "unknown"
        bot.manual_reroll_flow = lambda reason="": (_ for _ in ()).throw(AssertionError("startup fallback should not enter manual reroll"))

        def fake_stats_changed(*_args, **_kwargs):
            bot.last_recovery_verify_unreadable = True
            return False, "junk"

        bot.stats_changed = fake_stats_changed
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(bot.last_startup_result, "failed_unreadable_ui")
        self.assertEqual(clicks, [])
        self.assertEqual(sum("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages), 4)
        self.assertFalse(any("Restore Auto" in str(call) for call in clicks))

    def test_initial_auto_start_auto_resume_unknown_state_stays_conservative(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        result = bot.ensure_auto_enabled("Initial Auto Start Auto Resume", allow_uncertain_enable=True)
        self.assertEqual(result, "uncertain")
        self.assertEqual(clicks, [])
        self.assertTrue(any("skipping speculative checkbox click" in message for message in messages))

    def test_startup_fallback_click_result_is_exact_initial_auto_start_only(self):
        for reason in ("Initial Auto Start Auto Resume", "Stuck Recovery", "Manual Reroll Auto Resume"):
            with self.subTest(reason=reason):
                messages = []
                bot = AelrithForgeBot(messages.append, lambda *_: None)
                bot.cfg["OCR_DEBUG_FILE"] = False
                bot._interruptible_sleep = lambda *_args, **_kwargs: True
                bot.auto_checkbox_state = lambda: "unknown"
                clicks = []
                bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

                result = bot.ensure_auto_enabled(reason, allow_uncertain_enable=True)
                self.assertNotEqual(result, "startup_fallback_clicked")
                self.assertFalse(any(call[0][1] == "Initial Auto Start" for call in clicks))

    def test_unexpected_no_roll_watchdog_skips_guard_states(self):
        for state, guard in (
            ("ROLLING", "popup"),
            ("ROLLING", "manual"),
            ("ROLLING", "recovery"),
            ("GOD", "stop_state"),
            ("HIGH_VALUE", "stop_state"),
            ("BAD", "stop_state"),
            ("DISABLED", "stop_state"),
        ):
            with self.subTest(state=state, guard=guard):
                messages = []
                bot = AelrithForgeBot(messages.append, lambda *_: None)
                bot.cfg["OCR_DEBUG_FILE"] = False
                bot.cfg["UNEXPECTED_NO_ROLL_TIMEOUT"] = 1.0
                bot.cfg["UNEXPECTED_NO_ROLL_COOLDOWN"] = 1.0
                bot.popup_active = lambda *_args, **_kwargs: guard == "popup"
                bot.banner_active = lambda: False
                bot.manual_reroll_active = guard == "manual"
                bot.recovery_in_progress = guard == "recovery"
                clicks = []
                bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
                bot.auto_checkbox_state = lambda: "disabled"

                result = bot.unexpected_not_rolling_watchdog("same text", state, "rampage", 2.0)

                self.assertEqual(result, "skipped")
                self.assertEqual(clicks, [])

    def test_watchdog_rejects_text_only_current_spec_marker_change_without_visual_or_number_change(self):
        baseline = "current spec rampage combo ramp 16.8 damage 2.9 crit chance 3.85 crit damage 5.6"
        sample = "current spec ge rampage comboramp 16.8 cap.damage 2.9 critchance 3.85 critdamage 5.6"
        bot = ActivityStubBot([sample])
        bot.cfg["AUTO_VERIFY_POLLS"] = 1
        original_signal = bot._recovery_text_signal
        bot._recovery_text_signal = lambda _raw, _baseline, _numbers: (
            bot_module.normalize_text(sample),
            "current_spec_marker_changed",
        )

        try:
            changed, _text = bot.stats_changed(
                baseline,
                context="Unexpected No-Roll Watchdog suspicion",
                ui_signals=["watchdog_stale_suspicion"],
                polls_override=1,
                poll_delay_override=0.0,
                psm_sequence_override=(6,),
                candidate_signal_enabled=False,
                post_popup_check_enabled=False,
                initial_popup_known_false=True,
                initial_banner_known_false=True,
                abandon_on_weak_samples=1,
            )
        finally:
            bot._recovery_text_signal = original_signal

        self.assertFalse(changed)
        self.assertNotEqual(bot.last_recovery_reason, "current_spec_marker_changed")
        self.assertTrue(any("rejected text-only watchdog activity" in message for message in bot.messages))

    def test_watchdog_rejects_text_only_number_change_without_visual_change(self):
        baseline = "current spec rampage combo ramp 17.5 damage 17.4 crit chance 3.8 crit damage 7.13"
        sample = "current spec rampage combo ramp 17.5 damage 17.5 crit chance 3.8 crit damage 7.36"
        bot = ActivityStubBot([sample])
        bot.cfg["AUTO_VERIFY_POLLS"] = 1
        original_signal = bot._recovery_text_signal
        bot._recovery_text_signal = lambda _raw, _baseline, _numbers: (
            bot_module.normalize_text(sample),
            "stat_numbers_changed",
        )

        try:
            changed, _text = bot.stats_changed(
                baseline,
                context="Unexpected No-Roll Watchdog suspicion",
                ui_signals=["watchdog_stale_suspicion"],
                polls_override=1,
                poll_delay_override=0.0,
                psm_sequence_override=(6,),
                candidate_signal_enabled=False,
                post_popup_check_enabled=False,
                initial_popup_known_false=True,
                initial_banner_known_false=True,
                abandon_on_weak_samples=1,
            )
        finally:
            bot._recovery_text_signal = original_signal

        self.assertFalse(changed)
        self.assertNotEqual(bot.last_recovery_reason, "stat_numbers_changed")
        self.assertTrue(any("rejected text-only watchdog activity" in message for message in bot.messages))

    def test_unexpected_no_roll_watchdog_reenables_disabled_or_unknown_once(self):
        for checkbox_state in ("disabled", "unknown"):
            with self.subTest(checkbox_state=checkbox_state):
                messages = []
                bot = AelrithForgeBot(messages.append, lambda *_: None)
                bot.cfg["OCR_DEBUG_FILE"] = False
                bot.cfg["UNEXPECTED_NO_ROLL_TIMEOUT"] = 1.0
                bot.cfg["UNEXPECTED_NO_ROLL_COOLDOWN"] = 10.0
                bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
                bot._interruptible_sleep = lambda *_args, **_kwargs: True
                bot.popup_active = lambda *_args, **_kwargs: False
                bot.banner_active = lambda: False
                bot.auto_checkbox_state = lambda: checkbox_state
                calls = []

                def fake_stats_changed(baseline, context="Rolling activity", ui_signals=None, **_kwargs):
                    calls.append((baseline, context, tuple(ui_signals or ())))
                    return True, "current spec rampage combo ramp 21 damage 22"

                bot.stats_changed = fake_stats_changed
                clicks = []
                bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

                result = bot.unexpected_not_rolling_watchdog("same current text", "ROLLING", "rampage", 2.0)

                if checkbox_state == "disabled":
                    self.assertEqual(result, "recovered")
                    self.assertEqual(len(clicks), 1)
                    self.assertEqual(clicks[0][0][1], "Unexpected No-Roll Watchdog Auto Re-enable")
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(calls[0][1], "Unexpected No-Roll Watchdog verify")
                    self.assertEqual(calls[0][2], ("watchdog_auto_reenable",))
                    self.assertTrue(any("Unexpected No-Roll Watchdog | verified rolling resumed" in message for message in messages))
                else:
                    self.assertEqual(result, "skipped")
                    self.assertEqual(clicks, [])
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(calls[0][1], "Unexpected No-Roll Watchdog ambiguous checkbox confirm")
                    self.assertTrue(any("suppressed ambiguous checkbox click" in message for message in messages))

    def test_unexpected_no_roll_watchdog_success_clears_stale_signature(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["UNEXPECTED_NO_ROLL_TIMEOUT"] = 1.0
        bot.cfg["UNEXPECTED_NO_ROLL_COOLDOWN"] = 60.0
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "disabled"
        bot.stats_changed = lambda *_args, **_kwargs: (True, "current spec rampage combo ramp 23 damage 24")
        bot.click = lambda *_args, **_kwargs: None
        bot.last_watchdog_attempt_at = time.time()
        bot.last_watchdog_signature = "old|stale|signature"

        result = bot.unexpected_not_rolling_watchdog("same current text", "ROLLING", "rampage", 2.0)

        self.assertEqual(result, "recovered")
        self.assertEqual(bot.last_watchdog_attempt_at, 0.0)
        self.assertEqual(bot.last_watchdog_signature, "")
        self.assertTrue(any("stale signature cleared" in message for message in messages))

    def test_unexpected_no_roll_watchdog_enabled_skips_click(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["UNEXPECTED_NO_ROLL_TIMEOUT"] = 1.0
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("enabled skip should not verify"))

        result = bot.unexpected_not_rolling_watchdog("same current text", "ROLLING", "rampage", 2.0)

        self.assertEqual(result, "skipped")
        self.assertEqual(clicks, [])
        self.assertTrue(any("Auto appears enabled; skipping re-enable click" in message for message in messages))

    def test_unexpected_no_roll_watchdog_skips_disconnect_and_maintenance_screens(self):
        for sample, expected_reason in (
            ("clientinitiateddisconnect. errorcode 285 clientinitiateddisconnect. errorcode 285", "disconnect_screen"),
            ("glientinitiated disconnects erron ode 285 maintenance starting in 23s", "maintenance_screen"),
        ):
            with self.subTest(expected_reason=expected_reason):
                messages = []
                bot = AelrithForgeBot(messages.append, lambda *_: None)
                bot.cfg["OCR_DEBUG_FILE"] = False
                bot.cfg["UNEXPECTED_NO_ROLL_TIMEOUT"] = 1.0
                bot.popup_active = lambda *_args, **_kwargs: False
                bot.banner_active = lambda: False
                bot.auto_checkbox_state = lambda: (_ for _ in ()).throw(AssertionError("session-blocked watchdog path should not inspect Auto"))
                bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("session-blocked watchdog path should not verify recovery"))
                clicks = []
                bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

                result = bot.unexpected_not_rolling_watchdog(sample, "NON_TARGET", "colossus", 9.5, allow_early=True)

                self.assertEqual(result, "skipped")
                self.assertEqual(clicks, [])
                self.assertEqual(bot.last_recovery_route_snapshot.get("route_reason"), expected_reason)
                self.assertEqual(bot.last_recovery_route_snapshot.get("failure_type"), expected_reason)
                self.assertEqual(bot.last_recovery_route_snapshot.get("support_signals"), ["session_blocked", expected_reason])
                self.assertTrue(any("session-blocked screen" in message for message in messages))

    def test_unexpected_no_roll_watchdog_skips_off_target_control_text_region(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["UNEXPECTED_NO_ROLL_TIMEOUT"] = 1.0
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "disabled"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("off-target watchdog path should not click or verify")
        )

        result = bot.unexpected_not_rolling_watchdog("orCode:279", "ROLLING", None, 9.5, allow_early=True)

        self.assertEqual(result, "off_panel")
        self.assertEqual(clicks, [])
        self.assertEqual(bot.last_recovery_route_snapshot.get("route_reason"), "stats_region_off_target_ui_text")
        self.assertTrue(any("Current roll OCR region appears misconfigured" in message for message in messages))

    def test_stats_changed_classifies_disconnect_screen_as_session_blocked(self):
        bot = ActivityStubBot(["clientinitiateddisconnect. errorcode 285"])
        bot._interruptible_sleep = lambda *_args, **_kwargs: True

        changed, returned = bot.stats_changed(
            "clientinitiateddisconnect. errorcode 285",
            "Unexpected No-Roll Watchdog suspicion",
            polls_override=1,
            poll_delay_override=0.0,
            unreadable_fast_fail_polls=1,
            psm_sequence_override=(6,),
            post_popup_check_enabled=False,
        )

        self.assertFalse(changed)
        self.assertEqual(returned, "clientinitiateddisconnect. errorcode 285")
        self.assertEqual(bot.last_recovery_verify_state, "session_blocked")
        self.assertEqual(bot.last_recovery_reason, "disconnect_screen")

    def test_stats_changed_does_not_mislabel_normal_weak_readable_ocr_as_session_blocked(self):
        bot = ActivityStubBot(["rampage hp4.1 damage2.4"])
        bot._interruptible_sleep = lambda *_args, **_kwargs: True

        changed, _ = bot.stats_changed(
            "colossus damage 21.2 crit chance 1.6 luck 10.2 hp 30.0 crit damage 5.3",
            "Unexpected No-Roll Watchdog suspicion",
            polls_override=1,
            poll_delay_override=0.0,
            unreadable_fast_fail_polls=1,
            psm_sequence_override=(6,),
            post_popup_check_enabled=False,
        )

        self.assertFalse(changed)
        self.assertNotEqual(bot.last_recovery_verify_state, "session_blocked")

    def test_unexpected_no_roll_watchdog_failed_verify_suppresses_same_event(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["UNEXPECTED_NO_ROLL_TIMEOUT"] = 1.0
        bot.cfg["UNEXPECTED_NO_ROLL_COOLDOWN"] = 60.0
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "disabled"
        bot.stats_changed = lambda *_args, **_kwargs: (False, "same current text")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        self.assertEqual(bot.unexpected_not_rolling_watchdog("same current text", "ROLLING", "rampage", 2.0), "failed")
        self.assertEqual(bot.unexpected_not_rolling_watchdog("same current text", "ROLLING", "rampage", 2.0), "skipped")
        self.assertEqual(len(clicks), 1)
        self.assertTrue(any("failed to restore rolling" in message for message in messages))
        self.assertTrue(any("suppressed duplicate stale event" in message for message in messages))

    def test_startup_bad_current_spec_rerolls_immediately(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.check_roll = lambda *args, **kwargs: (
            "BAD",
            "rampage",
            "Combo Ramp 20 | Damage 20 | Crit Rate 3 | Crit Damage 7",
            "current spec rampage combo ramp 20 damage 20 crit chance 3 crit damage 7",
            ["Damage 20 < 29"],
            False,
        )
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True
        bot.stats_changed = lambda *_args, **_kwargs: (
            True,
            "current spec rampage combo ramp 21 damage 21 crit chance 3 crit damage 7",
        )

        self.assertEqual(bot.startup_check_current_roll(), "rerolled")
        self.assertEqual(bot.last_startup_result, "current_spec_bad_rerolled_then_rolling")
        self.assertEqual(manual_calls, ["startup current bad rampage"])
        self.assertTrue(any("Startup fast current-spec check | state=BAD trait=Rampage" in message for message in messages))
        self.assertTrue(any("manual rerolling immediately" in message for message in messages))
        self.assertTrue(any("rolling confirmed" in message for message in messages))

    def test_startup_strong_bad_spec_skips_weak_followup_validation(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        reads = [
            (
                "BAD",
                "rampage",
                "Combo Ramp 24.7 | Damage 17.3 | Crit Rate 2.9 | Crit Damage 7.8",
                "current spec rampage combo ramp 24.7 damage 17.3 crit chance 2.9 crit damage 7.8",
                ["Combo Ramp: 24.7 -> 29-30", "Damage: 17.3 -> 29-30", "Crit Damage: 7.8 -> 9-10"],
                False,
            ),
            (
                "NON_TARGET",
                "non_target",
                "Unsupported/filler trait is safe to autoskip",
                "currentspec. rampage comboramp 24.7 cap.datiage t730scatchance23ne.gadanige75",
                ["Unsupported trait autoskip"],
                False,
            ),
        ]
        check_calls = []

        def fake_check_roll(*args, **kwargs):
            check_calls.append(kwargs)
            return reads[min(len(check_calls) - 1, len(reads) - 1)]

        bot.check_roll = fake_check_roll
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True
        bot.stats_changed = lambda *_args, **_kwargs: (
            True,
            "current spec rampage combo ramp 25 damage 18 crit chance 3 crit damage 8",
        )

        self.assertEqual(bot.startup_check_current_roll(), "rerolled")
        self.assertEqual(manual_calls, ["startup current bad rampage"])
        self.assertEqual(len(check_calls), 1)
        self.assertTrue(any("startup_full_validation_skipped=True" in message for message in messages))
        self.assertTrue(any("trusted_startup_fast_spec_probe" in message for message in messages))
        self.assertTrue(any("manual rerolling immediately" in message for message in messages))

    def test_startup_disabled_current_spec_rerolls_immediately(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.check_roll = lambda *args, **kwargs: (
            "DISABLED",
            "rampage",
            "Rampage target is disabled",
            "current spec rampage combo ramp 20 damage 20 crit chance 3 crit damage 7",
            ["Target disabled"],
            False,
        )
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True
        bot.stats_changed = lambda *_args, **_kwargs: (
            True,
            "current spec rampage combo ramp 21 damage 21 crit chance 3 crit damage 7",
        )

        self.assertEqual(bot.startup_check_current_roll(), "rerolled")
        self.assertEqual(manual_calls, ["startup current disabled rampage"])
        self.assertEqual(bot.last_startup_result, "current_spec_bad_rerolled_then_rolling")
        self.assertTrue(any("Startup current mythical is DISABLED; manual rerolling immediately" in message for message in messages))

    def test_startup_bad_current_spec_fails_without_rolling_confirmation(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.check_roll = lambda *args, **kwargs: (
            "BAD",
            "rampage",
            "Combo Ramp 20 | Damage 20 | Crit Rate 3 | Crit Damage 7",
            "current spec rampage combo ramp 20 damage 20 crit chance 3 crit damage 7",
            ["Damage 20 < 29"],
            False,
        )
        bot.manual_reroll_flow = lambda reason="": True
        bot.stats_changed = lambda *_args, **_kwargs: (False, "same stuck text")

        self.assertEqual(bot.startup_check_current_roll(), "failed")
        self.assertEqual(bot.last_startup_result, "failed_no_roll_detected")
        self.assertTrue(any("rolling was not confirmed" in message for message in messages))

    def test_startup_bad_current_spec_fails_when_manual_reroll_flow_fails(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.check_roll = lambda *args, **kwargs: (
            "BAD",
            "rampage",
            "Combo Ramp 20 | Damage 20 | Crit Rate 3 | Crit Damage 7",
            "current spec rampage combo ramp 20 damage 20 crit chance 3 crit damage 7",
            ["Damage 20 < 29"],
            False,
        )
        bot.manual_reroll_flow = lambda reason="": False
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not verify failed reroll"))

        self.assertEqual(bot.startup_check_current_roll(), "failed")
        self.assertEqual(bot.last_startup_result, "failed_no_roll_detected")
        self.assertTrue(any("manual reroll failed" in message for message in messages))

    def test_startup_non_target_current_spec_continues_without_manual_reroll(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.check_roll = lambda *args, **kwargs: (
            "NON_TARGET",
            "non_target",
            "Unsupported/filler trait (vigor) is safe to autoskip",
            "current spec vigor damage 5.0 range 3.0",
            ["Unsupported trait autoskip"],
            False,
        )
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("NON_TARGET should not verify manual reroll"))

        self.assertEqual(bot.startup_check_current_roll(), "continue")
        self.assertEqual(manual_calls, [])
        self.assertEqual(bot.last_startup_result, "")
        self.assertTrue(any("Startup fast current-spec probe | state=NON_TARGET trait=Non-target Roll" in message for message in messages))
        self.assertTrue(any("accepted strong NON_TARGET filler evidence" in message for message in messages))
        self.assertFalse(any("manual rerolling immediately" in message for message in messages))

    def test_recovery_fallback_treats_non_target_as_rollable_filler(self):
        bot = RecoveryFallbackStubBot(
            (
                "NON_TARGET",
                "non_target",
                "Unsupported/filler trait (vigor) is safe to autoskip",
                "current spec vigor damage 5.0 range 3.0",
                ["Unsupported trait autoskip"],
                False,
            )
        )
        result = bot.recovery_fallback_evaluate_current_roll("Unit Recovery")
        self.assertEqual(result, "rollable_filler")
        self.assertEqual(bot.manual_calls, 0)
        self.assertEqual(bot.verify_calls, 0)
        self.assertTrue(any("NON_TARGET rollable filler" in message for message in bot.messages))

    def test_manual_reroll_auto_resume_uncertain_results_fail_flow(self):
        for auto_result in ("uncertain", "clicked_uncertain_restored", "clicked_uncertain_rolled_back"):
            with self.subTest(auto_result=auto_result):
                messages = []
                bot = AelrithForgeBot(messages.append, lambda *_: None)
                bot.cfg["OCR_DEBUG_FILE"] = False
                bot._interruptible_sleep = lambda *_args, **_kwargs: True
                bot.popup_active = lambda *_args, **_kwargs: True
                bot.clear_reroll_popup = lambda *_args, **_kwargs: True
                bot.click = lambda *_args, **_kwargs: None
                bot.ensure_auto_enabled = lambda *_args, **_kwargs: auto_result
                if auto_result == "uncertain":
                    bot._attempt_auto_reenable_once = lambda *_args, **_kwargs: False

                self.assertFalse(bot.manual_reroll_flow("unit bad mythical"))
                self.assertTrue(any(f"result={auto_result}" in message for message in messages))
                self.assertTrue(any("not reporting flow complete" in message for message in messages))
                self.assertFalse(any("Manual reroll flow complete" in message for message in messages))

    def test_manual_reroll_auto_resume_unknown_does_not_speculative_toggle(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
        bot.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.stats_changed = lambda *_args, **_kwargs: (False, "same text")

        self.assertFalse(bot.manual_reroll_flow("unit bad mythical"))

        labels = [call[0][1] for call in clicks]
        self.assertIn("Manual Reroll", labels)
        self.assertIn("Confirm Reroll", labels)
        self.assertNotIn("Manual Reroll Auto Resume", labels)
        self.assertIn("Manual Reroll Auto Resume Recovery Auto Re-enable", labels)
        self.assertTrue(any("popup not confirmed; pressing fallback Yes" in message for message in messages))
        self.assertTrue(any("bounded recovery re-enable verify" in message for message in messages))
        self.assertTrue(any("bounded recovery did not safely confirm rolling" in message for message in messages))
        self.assertFalse(any("Manual reroll flow complete" in message for message in messages))

    def test_manual_reroll_active_popup_still_confirms_reroll(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["POPUP_RETRY_DELAY"] = 0.0
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        popup_states = iter([True, False])
        bot.popup_active = lambda *_args, **_kwargs: next(popup_states, False)
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.stats_changed = lambda baseline, context="", ui_signals=None, **_kwargs: (
            context == "Manual Reroll Auto Resume verify"
            and tuple(ui_signals or ()) == ("manual_reroll_auto_resume",),
            "current spec rampage combo ramp 21 damage 22",
        )

        self.assertTrue(bot.manual_reroll_flow("unit bad mythical"))
        self.assertEqual([call[0][1] for call in clicks], ["Manual Reroll", "Confirm Popup"])
        self.assertFalse(any("popup absence confirmed; skipping fallback Yes" in message for message in messages))

    def test_manual_reroll_popup_cleared_resume_verify_uses_single_fast_psm6_poll(self):
        bot = self.make_bot()
        transition = bot._manual_reroll_timing_profile(False)

        profile = bot._stats_verify_profile(
            "manual_reroll_resume_verify",
            transition_profile=transition,
            popup_known_false=True,
        )

        self.assertEqual(profile["polls_override"], 1)
        self.assertEqual(profile["psm_sequence_override"], (6,))
        self.assertEqual(profile["unreadable_fast_fail_polls"], 1)
        self.assertFalse(profile["post_popup_check_enabled"])
        self.assertFalse(profile["mid_popup_check_enabled"])

    def test_manual_reroll_popup_psm6_fallback_detects_confirm_dialog(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["POPUP_RETRY_DELAY"] = 0.0
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        popup_reads = {"count": 0}

        def fake_ocr(region, psm=7):
            if tuple(region) == tuple(bot.cfg["POPUP_REGION"]):
                popup_reads["count"] += 1
                if popup_reads["count"] == 1 and psm == 7:
                    return "."
                if popup_reads["count"] == 2 and psm == 6:
                    return "are you sure you want to reroll"
                return ""
            return "current spec rampage combo ramp 20 damage 20"

        bot.ocr_region = fake_ocr
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.stats_changed = lambda baseline, context="", ui_signals=None, **_kwargs: (
            context == "Manual Reroll Auto Resume verify"
            and tuple(ui_signals or ()) == ("manual_reroll_auto_resume",),
            "current spec rampage combo ramp 21 damage 22",
        )

        self.assertTrue(bot.manual_reroll_flow("unit bad mythical"))
        self.assertEqual([call[0][1] for call in clicks], ["Manual Reroll", "Confirm Popup"])
        self.assertGreaterEqual(popup_reads["count"], 2)
        self.assertFalse(any("popup not confirmed; pressing fallback Yes" in message for message in messages))

    def test_manual_reroll_fast_visual_popup_path_skips_popup_ocr_and_resume_ocr(self):
        if bot_module.Image is None:
            self.skipTest("Pillow unavailable")
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("visual refresh should skip resume OCR")
        )
        popup_ocr_reads = []
        bot.ocr_region = lambda region, psm=7: popup_ocr_reads.append((tuple(region), psm)) or ""

        dark = bot_module.Image.new("RGB", (80, 40), (12, 12, 12))
        bright = bot_module.Image.new("RGB", (80, 40), (225, 225, 225))
        mid = bot_module.Image.new("RGB", (80, 40), (80, 80, 80))
        screenshots = iter([dark, dark, bright, dark, mid])

        class VisualPyAutoGui:
            @staticmethod
            def screenshot(*_args, **_kwargs):
                return next(screenshots)

        old_pyautogui = bot_module.pyautogui
        try:
            bot_module.pyautogui = VisualPyAutoGui
            self.assertTrue(bot.manual_reroll_flow("unit bad mythical"))
        finally:
            bot_module.pyautogui = old_pyautogui

        self.assertEqual([call[0][1] for call in clicks], ["Manual Reroll", "Confirm Popup"])
        self.assertEqual(popup_ocr_reads, [])
        self.assertTrue(any("route=fast_visual" in message for message in messages))
        self.assertTrue(any("visual roll refresh" in message for message in messages))

    def test_manual_reroll_visual_resume_after_auto_click_still_runs_bounded_verify(self):
        if bot_module.Image is None:
            self.skipTest("Pillow unavailable")
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.auto_checkbox_state = lambda: "disabled"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        verify_calls = []

        def fake_stats_changed(baseline, context="", ui_signals=None, **_kwargs):
            verify_calls.append((baseline, context, tuple(ui_signals or ())))
            return True, "current spec rampage combo ramp 21 damage 22 crit chance 3 crit damage 7"

        bot.stats_changed = fake_stats_changed
        bot.ocr_region = lambda _region, psm=7: ""
        dark = bot_module.Image.new("RGB", (80, 40), (12, 12, 12))
        bright = bot_module.Image.new("RGB", (80, 40), (225, 225, 225))
        mid = bot_module.Image.new("RGB", (80, 40), (80, 80, 80))
        screenshots = iter([dark, dark, bright, dark, mid])

        class VisualPyAutoGui:
            @staticmethod
            def screenshot(*_args, **_kwargs):
                return next(screenshots)

        old_pyautogui = bot_module.pyautogui
        try:
            bot_module.pyautogui = VisualPyAutoGui
            self.assertTrue(bot.manual_reroll_flow("unit bad mythical"))
        finally:
            bot_module.pyautogui = old_pyautogui

        self.assertEqual([call[0][1] for call in clicks], ["Manual Reroll", "Confirm Popup", "Manual Reroll Auto Resume"])
        self.assertEqual(len(verify_calls), 1)
        self.assertEqual(verify_calls[0][1], "Manual Reroll Auto Resume verify")
        self.assertTrue(any("visual refresh observed after Auto click" in message for message in messages))

    def test_manual_reroll_ambiguous_visual_popup_falls_back_to_ocr(self):
        if bot_module.Image is None:
            self.skipTest("Pillow unavailable")
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["POPUP_RETRY_DELAY"] = 0.0
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot._ocr_tesseract_image = lambda *_args, **_kwargs: "current spec rampage combo ramp 21 damage 22"
        bot.stats_changed = lambda baseline, context="", ui_signals=None, **_kwargs: (
            context == "Manual Reroll Auto Resume verify"
            and tuple(ui_signals or ()) == ("manual_reroll_auto_resume",),
            "current spec rampage combo ramp 21 damage 22",
        )
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        popup_reads = {"count": 0}

        def fake_ocr(region, psm=7):
            if tuple(region) == tuple(bot.cfg["POPUP_REGION"]):
                popup_reads["count"] += 1
                return "are you sure you want to reroll" if popup_reads["count"] == 1 and psm == 7 else ""
            return "current spec rampage combo ramp 21 damage 22"

        bot.ocr_region = fake_ocr
        same = bot_module.Image.new("RGB", (80, 40), (20, 20, 20))

        class AmbiguousPyAutoGui:
            @staticmethod
            def screenshot(*_args, **_kwargs):
                return same

        old_pyautogui = bot_module.pyautogui
        try:
            bot_module.pyautogui = AmbiguousPyAutoGui
            self.assertTrue(bot.manual_reroll_flow("unit bad mythical"))
        finally:
            bot_module.pyautogui = old_pyautogui

        self.assertGreaterEqual(popup_reads["count"], 1)
        self.assertIn("Confirm Popup", [call[0][1] for call in clicks])
        self.assertTrue(any("visual fallback" in message for message in messages))
        self.assertTrue(any("route=ocr_fallback" in message for message in messages))

    def test_manual_reroll_auto_resume_uncertain_uses_bounded_recovery_path(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
        bot.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.ensure_auto_enabled = lambda *_args, **_kwargs: "uncertain"
        recovery_calls = []

        def fake_attempt(context, baseline, **kwargs):
            recovery_calls.append((context, baseline, kwargs))
            return True

        bot._attempt_auto_reenable_once = fake_attempt

        self.assertTrue(bot.manual_reroll_flow("bad power colossus"))
        self.assertEqual([call[0][1] for call in clicks], ["Manual Reroll", "Confirm Reroll"])
        self.assertEqual(len(recovery_calls), 1)
        self.assertEqual(recovery_calls[0][0], "Manual Reroll Auto Resume Recovery")
        self.assertEqual(recovery_calls[0][2]["verify_signal"], "manual_reroll_auto_reenable")
        self.assertTrue(recovery_calls[0][2]["force_click_on_ambiguous"])
        self.assertTrue(recovery_calls[0][2]["direct_click_on_forced_unknown"])
        self.assertTrue(any("popup not confirmed; pressing fallback Yes" in message for message in messages))
        self.assertTrue(any("restored by bounded recovery path" in message for message in messages))
        self.assertTrue(any("Manual reroll flow complete" in message for message in messages))

    def test_manual_reroll_bounded_recovery_handoff_skips_extra_uncertain_validation_read(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
        bot.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.click = lambda *_args, **_kwargs: None
        reads = {"count": 0}

        def fake_auto_checkbox_state():
            reads["count"] += 1
            return "unknown"

        bot.auto_checkbox_state = fake_auto_checkbox_state

        def fake_attempt(*_args, **_kwargs):
            self.assertEqual(reads["count"], 2)
            self.assertTrue(_kwargs["direct_click_on_forced_unknown"])
            return False

        bot._attempt_auto_reenable_once = fake_attempt

        self.assertFalse(bot.manual_reroll_flow("bad power colossus"))
        self.assertTrue(any("deferring extra validation to bounded recovery path" in message for message in messages))

    def test_manual_reroll_auto_resume_rechecks_unknown_then_confirmed_disabled(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
        bot.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        states = iter(["unknown", "unknown", "unknown"])
        bot.auto_checkbox_state = lambda: next(states, "disabled")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        stats_contexts = []
        bot.stats_changed = lambda baseline, context="", ui_signals=None, **_kwargs: (
            stats_contexts.append(context) is None
            and
            context == "Manual Reroll Auto Resume Recovery verify"
            and tuple(ui_signals or ()) == ("manual_reroll_auto_reenable",),
            "current spec rampage combo ramp 21 damage 22",
        )

        self.assertTrue(bot.manual_reroll_flow("unit bad mythical"))

        labels = [call[0][1] for call in clicks]
        self.assertIn("Manual Reroll", labels)
        self.assertIn("Confirm Reroll", labels)
        self.assertIn("Manual Reroll Auto Resume Recovery Auto Re-enable", labels)
        self.assertNotIn("Manual Reroll Auto Resume Recovery ambiguous checkbox guard", stats_contexts)
        self.assertTrue(any("deferring extra validation to bounded recovery path" in message for message in messages))
        self.assertTrue(any("optimized manual reroll unknown checkbox path" in message for message in messages))
        self.assertTrue(any("restored by bounded recovery path" in message for message in messages))
        self.assertTrue(any("Manual reroll flow complete" in message for message in messages))

    def test_manual_reroll_auto_resume_confirmed_does_not_need_watchdog(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
        bot.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot.unexpected_not_rolling_watchdog = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("manual reroll should not rely on watchdog for normal resume")
        )
        bot.stats_changed = lambda baseline, context="", ui_signals=None, **_kwargs: (
            context == "Manual Reroll Auto Resume verify"
            and tuple(ui_signals or ()) == ("manual_reroll_auto_resume",),
            "current spec rampage combo ramp 21 damage 22",
        )
        bot.click = lambda *_args, **_kwargs: None

        self.assertTrue(bot.manual_reroll_flow("unit bad mythical"))
        self.assertTrue(any("Manual reroll auto resume safely confirmed | result=already_enabled" in message for message in messages))
        self.assertTrue(any("Manual reroll auto resume rolling activity confirmed" in message for message in messages))
        self.assertTrue(any("Manual reroll flow complete" in message for message in messages))

    def test_manual_reroll_resume_accepts_popup_cleared_roll_like_image_change(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: True
        bot.clear_reroll_popup = lambda *_args, **_kwargs: True
        bot._safe_region_screenshot = lambda *_args, **_kwargs: None
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot.click = lambda *_args, **_kwargs: None
        stats_calls = []

        def fake_stats_changed(baseline, context="", **kwargs):
            stats_calls.append((context, kwargs))
            bot.last_recovery_verify_details = {
                "classification": "not_rolling",
                "rejection_reason": "readable_insufficient_change",
                "image_changed_samples": 2,
                "max_change_score": 17.43,
                "unreadable": False,
                "samples_detail": [
                    {
                        "cleaned": "infernal critdamage5.1",
                        "unreliable": False,
                        "materially_different": True,
                        "trait_only": False,
                        "image_changed": True,
                    },
                    {
                        "cleaned": "solid hp4.7 damage2.1",
                        "unreliable": False,
                        "materially_different": True,
                        "trait_only": False,
                        "image_changed": True,
                    },
                ],
            }
            bot.last_recovery_reason = "readable_insufficient_change"
            bot.last_recovery_verify_unreadable = False
            return False, baseline

        bot.stats_changed = fake_stats_changed

        self.assertTrue(bot.manual_reroll_flow("bad power subjugator"))
        self.assertEqual(len(stats_calls), 1)
        self.assertEqual(stats_calls[0][0], "Manual Reroll Auto Resume verify")
        self.assertFalse(stats_calls[0][1]["candidate_signal_enabled"])
        self.assertFalse(stats_calls[0][1]["post_popup_check_enabled"])
        self.assertFalse(stats_calls[0][1]["mid_popup_check_enabled"])
        self.assertTrue(any("popup-cleared roll refresh" in message for message in messages))

    def test_manual_reroll_resume_accepts_popup_cleared_roll_like_ocr_below_image_threshold(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: True
        bot.clear_reroll_popup = lambda *_args, **_kwargs: True
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot.click = lambda *_args, **_kwargs: None

        def fake_stats_changed(baseline, context="", **kwargs):
            self.assertEqual(context, "Manual Reroll Auto Resume verify")
            self.assertFalse(kwargs["candidate_signal_enabled"])
            self.assertFalse(kwargs["post_popup_check_enabled"])
            self.assertFalse(kwargs["mid_popup_check_enabled"])
            bot.last_recovery_verify_details = {
                "classification": "not_rolling",
                "rejection_reason": "readable_insufficient_change",
                "image_changed_samples": 0,
                "max_change_score": 6.57,
                "unreadable": False,
                "samples_detail": [
                    {
                        "cleaned": "solid hp6.7 .damage3.5",
                        "unreliable": False,
                        "materially_different": True,
                        "trait_only": False,
                        "image_changed": False,
                        "change_score": 6.57,
                    }
                ],
            }
            bot.last_recovery_reason = "readable_insufficient_change"
            bot.last_recovery_verify_unreadable = False
            return False, baseline

        bot.stats_changed = fake_stats_changed

        self.assertTrue(bot.manual_reroll_flow("bad power cursebrand"))
        self.assertTrue(any("reason=recent_popup_clear_roll_like_ocr" in message for message in messages))
        self.assertTrue(any("support=recent_popup_clear+roll_like_ocr" in message for message in messages))
        self.assertTrue(any("Manual reroll flow complete" in message for message in messages))

    def test_manual_reroll_auto_resume_known_enabled_fails_without_activity_confirmation(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
        bot.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot.stats_changed = lambda *_args, **_kwargs: (False, "same text")
        bot.click = lambda *_args, **_kwargs: None

        self.assertFalse(bot.manual_reroll_flow("unit bad mythical"))
        self.assertTrue(any("did not confirm rolling activity" in message for message in messages))
        self.assertFalse(any("Manual reroll flow complete" in message for message in messages))

    def test_manual_reroll_resume_rejects_stale_text_after_popup_clear(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: True
        bot.clear_reroll_popup = lambda *_args, **_kwargs: True
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot.click = lambda *_args, **_kwargs: None

        def fake_stats_changed(baseline, context="", **kwargs):
            self.assertEqual(context, "Manual Reroll Auto Resume verify")
            self.assertFalse(kwargs["candidate_signal_enabled"])
            bot.last_recovery_verify_details = {
                "classification": "not_rolling",
                "rejection_reason": "no_material_change",
                "image_changed_samples": 0,
                "max_change_score": 0.0,
                "unreadable": False,
                "samples_detail": [
                    {
                        "cleaned": "subjugator luck9.4 critdamage10.2",
                        "unreliable": False,
                        "materially_different": False,
                        "trait_only": False,
                        "image_changed": False,
                    }
                ],
            }
            bot.last_recovery_reason = "no_material_change"
            bot.last_recovery_verify_unreadable = False
            return False, baseline

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.manual_reroll_flow("bad power subjugator"))
        self.assertTrue(any("reason=no_material_change" in message for message in messages))
        self.assertFalse(any("popup-cleared roll refresh" in message for message in messages))
        self.assertFalse(any("Manual reroll flow complete" in message for message in messages))

    def test_powers_manual_reroll_flow_uses_active_powers_button_coordinates(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir):
            controller = BotController()
            settings = controller.normalize_settings(default_settings())
            settings["roll_domain"] = "powers"
            settings["powers_layout"]["stats_region"] = "100,100,300,80"
            settings["powers_layout"]["popup_region"] = "200,200,140,70"
            settings["powers_layout"]["protected_region"] = "300,300,180,80"
            settings["powers_layout"]["preview_region"] = "400,400,260,70"
            settings["powers_layout"]["current_power_region"] = "400,400,260,70"
            settings["powers_layout"]["coords"] = {
                "auto": "101,202",
                "roll": "303,404",
                "yes": "505,606",
            }
            controller.apply_settings(settings, save=False, announce=False)

            bot = controller.bot
            bot.cfg["OCR_DEBUG_FILE"] = False
            bot.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
            bot.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
            bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
            bot._interruptible_sleep = lambda *_args, **_kwargs: True
            bot.popup_active = lambda *_args, **_kwargs: False
            bot.auto_checkbox_state = lambda: "disabled"
            clicks = []

            def capture_click(coords, label, offset=(0, 0), settle=0.2):
                clicks.append((tuple(coords), label, offset, settle))

            bot.click = capture_click
            bot.stats_changed = lambda baseline, context="", ui_signals=None, **_kwargs: (
                context == "Manual Reroll Auto Resume verify"
                and tuple(ui_signals or ()) == ("manual_reroll_auto_resume",),
                "curserbrand damage 28.4 crit chance 3.6 crit damage 11.4",
            )

            self.assertTrue(bot.manual_reroll_flow("bad power cursebrand"))
            self.assertEqual(clicks[0][1], "Manual Reroll")
            self.assertIn(clicks[1][1], ("Confirm Reroll", "Confirm Popup"))
            self.assertEqual(clicks[2][1], "Manual Reroll Auto Resume")
            self.assertEqual([entry[0] for entry in clicks], [(303, 404), (505, 606), (101, 202)])

    def test_powers_manual_reroll_logs_use_power_wording(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["MANUAL_POPUP_TIMEOUT"] = 0.01
        bot.cfg["MANUAL_POPUP_POLL_DELAY"] = 0.01
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "unknown"
        bot.click = lambda *_args, **_kwargs: None
        bot._attempt_auto_reenable_once = lambda *_args, **_kwargs: False

        self.assertFalse(bot.manual_reroll_flow())
        self.assertEqual(bot._manual_reroll_failure_reason(), "bad power manual reroll could not resume Auto safely")
        self.assertTrue(any("bad power" in message for message in messages))
        self.assertTrue(any("domain=powers target=power" in message for message in messages))
        self.assertFalse(any("bad mythical" in message for message in messages))

    def test_power_bad_requires_coherent_required_parse(self):
        messages = []
        bot = StubBot(
            [
                (
                    "partial-power",
                    "Subjugator Damage36.8 CritChance2.8 Luck9.4",
                    "Subjugator Damage36.8 CritChance2.8 Luck9.4",
                )
            ]
        )
        bot.log = messages.append
        self.apply_subjugator_luck_target(bot)

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "ROLLING")
        self.assertIsNone(trait)
        self.assertEqual(summary, "")
        self.assertEqual(missing, [])
        self.assertFalse(near)
        self.assertFalse(bot.last_decision_chain.get("power_parse_coherent"))
        self.assertTrue(any("POWER BAD gate deferred" in message for message in messages))

    def test_power_bad_confirmation_accepts_stable_configured_miss(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        self.apply_subjugator_luck_target(bot)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        text = "Subjugator NPC Slow 20% 5s Damage 36.8 Crit Chance 2.8 Luck 9.4 HP 34.4 Crit Damage 10.2"
        state, trait, _summary, _ocr_text, missing, _near = self.evaluate_power_text(bot, text, "initial")
        bot.check_roll = lambda allow_fallback=True, startup_fast=False: self.evaluate_power_text(bot, text, "confirm")

        self.assertEqual(state, "BAD")
        self.assertTrue(bot._confirm_power_bad_before_manual_reroll(trait, missing, context="Unit Power BAD manual reroll"))
        self.assertTrue(any("Unit Power BAD manual reroll confirmed" in message for message in messages))

    def test_power_manual_reroll_start_log_includes_configured_miss_context(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        self.apply_subjugator_luck_target(bot)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        text = "Subjugator NPC Slow 20% 5s Damage 36.8 Crit Chance 2.8 Luck 9.4 HP 34.4 Crit Damage 10.2"
        state, trait, _summary, _ocr_text, missing, _near = self.evaluate_power_text(bot, text, "initial")
        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "subjugator")
        self.assertIn("Luck: 9.4 -> 17-17.5", missing)
        bot.popup_active = lambda *_args, **_kwargs: True
        bot.clear_reroll_popup = lambda *_args, **_kwargs: True
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot.click = lambda *_args, **_kwargs: None
        bot.stats_changed = lambda *_args, **_kwargs: (True, "infernal critdamage5.1")

        self.assertTrue(bot.manual_reroll_flow("bad power subjugator"))
        start_logs = [message for message in messages if message.startswith("Manual reroll flow | bad power subjugator")]
        self.assertTrue(start_logs)
        self.assertIn("trigger=power_bad trait=Subjugator", start_logs[-1])
        self.assertIn("Luck: 9.4 -> 17-17.5", start_logs[-1])
        self.assertIn("source=initial", start_logs[-1])

    def test_power_bad_confirmation_rejects_changed_values(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        self.apply_subjugator_luck_target(bot)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        initial = "Subjugator NPC Slow 20% 5s Damage 36.8 Crit Chance 2.8 Luck 9.4 HP 34.4 Crit Damage 10.2"
        changed = "Subjugator NPC Slow 20% 5s Damage 36.8 Crit Chance 2.8 Luck 10.4 HP 34.4 Crit Damage 10.2"
        state, trait, _summary, _ocr_text, missing, _near = self.evaluate_power_text(bot, initial, "initial")
        bot.check_roll = lambda allow_fallback=True, startup_fast=False: self.evaluate_power_text(bot, changed, "confirm")

        self.assertEqual(state, "BAD")
        self.assertFalse(bot._confirm_power_bad_before_manual_reroll(trait, missing, context="Unit Power BAD manual reroll"))
        self.assertTrue(any("Unit Power BAD manual reroll rejected" in message for message in messages))

    def test_loop_manual_reroll_runs_after_stable_power_bad_confirmation(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        self.apply_subjugator_luck_target(bot)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["STARTUP_DELAY"] = 0.0
        bot.cfg["LOOP_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: not bot.stop_event.is_set()
        bot.startup_check_current_roll = lambda: "rerolled"
        bot.start_live_status = lambda *_args, **_kwargs: True
        bot.finish_live_status = lambda *_args, **_kwargs: True
        bot.maybe_update_live_status = lambda *_args, **_kwargs: True
        bot.maybe_report_passive_shards = lambda force=False: None
        bot.maybe_report_power_shards = lambda force=False: None
        bot.should_check_passive_shards_empty = lambda _count: False
        bot.should_check_power_shards_empty = lambda _count: False
        text = "Subjugator NPC Slow 20% 5s Damage 36.8 Crit Chance 2.8 Luck 9.4 HP 34.4 Crit Damage 10.2"
        bot.check_roll = lambda allow_fallback=True, startup_fast=False: self.evaluate_power_text(bot, text, "loop")
        manual_calls = []

        def manual_reroll(reason=""):
            manual_calls.append(reason)
            bot.stop_event.set()
            return True

        bot.manual_reroll_flow = manual_reroll

        bot.loop()

        self.assertEqual(manual_calls, ["bad power subjugator"])
        self.assertTrue(any("Loop Power BAD manual reroll confirmed" in message for message in messages))

    def test_powers_startup_bad_current_power_trusts_strong_fast_probe(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        calls = []

        def fake_check_roll(*args, **kwargs):
            calls.append(kwargs)
            bot.record_decision_chain(
                subsystem="Classification",
                classification="BAD",
                current_trait="Colossus",
                power_parse_coherent=True,
                power_candidate_quality=151,
                power_required_values={
                    "Damage": 22.2,
                    "Crit Chance": 1.8,
                    "Crit Damage": 7.6,
                    "Luck": 14.6,
                    "Boss damage bonus": 23.4,
                },
            )
            return (
                "BAD",
                "colossus",
                "Damage 22.2 | Crit Chance 1.8 | Luck 14.6 | HP 27.8 | Crit Damage 7.6 | Passive Boss damage bonus 23.4",
                "Colossus > +23.4% Boss DMG, Damage 22.2%, Crit Chance 1.8%, Luck 14.6%, HP 27.8%, Crit Damage 7.6%",
                ["Damage 22.2 < 30"],
                False,
            )

        bot.check_roll = fake_check_roll
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or False
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("failed reroll should not verify"))

        self.assertEqual(bot.startup_check_current_roll(), "failed")
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].get("startup_fast"))
        self.assertTrue(calls[1].get("startup_fast"))
        self.assertFalse(calls[1].get("allow_fallback"))
        self.assertEqual(manual_calls, ["startup current bad colossus"])
        self.assertTrue(any("Startup Power BAD manual reroll confirmed" in message for message in messages))
        self.assertTrue(any("route=fast_startup_power_probe" in message for message in messages))
        self.assertTrue(any("strategy=trusted_startup_fast_power_probe" in message for message in messages))
        self.assertTrue(any("skipping slower full current-spec scan" in message for message in messages))

    def test_powers_startup_autoskip_current_power_skips_trust_probe(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._begin_startup_context("unit test")
        bot.check_roll = lambda *args, **kwargs: (
            "NON_TARGET",
            "non_target_power",
            "Unsupported or filler power observed; letting Auto continue",
            "Tempered HP 3.2 Damage 4.2",
            ["Non-target power"],
            False,
        )
        bot.popup_active = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Powers autoskip should not run popup trust probe")
        )
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Powers autoskip should not run startup trust probe")
        )

        self.assertEqual(bot.startup_check_current_roll(), "continue")
        self.assertTrue(bot._startup_context["powers_autoskip_current"])
        self.assertEqual(bot._startup_context["preflight_fallback_reason"], "autoskip_power")
        self.assertTrue(any("AUTOSKIP/NON_TARGET" in message for message in messages))

    def test_powers_startup_autoskip_enabled_auto_skips_preflight_and_verify(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "autoskip_power"
        bot._startup_context["powers_autoskip_current"] = True
        bot.ocr_region = lambda *_args, **_kwargs: "tempered hp3.2 damage4.2"
        bot.auto_checkbox_state = lambda: "enabled"
        self.force_strong_enabled_checkbox(bot)
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("enabled Powers autoskip should not run OCR verification")
        )
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        self.assertTrue(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(clicks, [])
        self.assertTrue(any("powers_autoskip_preflight_skipped=True" in message for message in messages))
        self.assertTrue(any("powers_autoskip=True | action=continue" in message for message in messages))

    def test_powers_startup_autoskip_disabled_auto_observes_without_click(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "autoskip_power"
        bot._startup_context["powers_autoskip_current"] = True
        bot.ocr_region = lambda *_args, **_kwargs: "tempered hp3.2 damage4.2"
        bot.auto_checkbox_state = lambda: "disabled"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled Powers autoskip should observe without OCR verification")
        )

        self.assertTrue(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(clicks, [])
        self.assertTrue(any("powers_autoskip_preflight_skipped=True" in message for message in messages))
        self.assertTrue(any("startup_powers_observe_without_toggle" in message for message in messages))
        self.assertTrue(any("decision=skip_toggle_observe_first" in message for message in messages))
        self.assertTrue(any("powers_autoskip_current=True" in message for message in messages))

    def test_powers_startup_autoskip_unknown_auto_observes_without_guarded_recovery(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "autoskip_power"
        bot._startup_context["powers_autoskip_current"] = True
        bot.ocr_region = lambda *_args, **_kwargs: "tempered hp3.2 damage4.2"
        bot.auto_checkbox_state = lambda: "unknown"
        bot.stats_changed = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unknown Powers autoskip should observe without OCR verification")
        )
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bounded_calls = []
        bot._attempt_auto_reenable_once = lambda *args, **kwargs: bounded_calls.append((args, kwargs)) or False

        self.assertTrue(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(clicks, [])
        self.assertEqual(bounded_calls, [])
        self.assertTrue(any("powers_autoskip_preflight_skipped=True" in message for message in messages))
        self.assertTrue(any("startup_powers_observe_without_toggle" in message for message in messages))
        self.assertTrue(any("decision=skip_toggle_observe_first" in message for message in messages))

    def test_powers_startup_compact_non_target_preflight_enabled_does_not_click(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "stat_numbers_changed"
        bot.ocr_region = lambda *_args, **_kwargs: "fierce hp3.1 .damage4.7"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "enabled"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        stats_calls = []

        def fake_stats_changed(_baseline, context="", **kwargs):
            stats_calls.append((context, kwargs))
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                return False, _baseline
            if context == "Initial Auto Start auto verify":
                bot.last_recovery_verify_details = {
                    "reason": "popup_confirmed_mid_polling",
                    "signal_sources": ["ocr", "popup"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "popup_confirmed_mid_polling"
                return True, "tempered hp4.7 .damage4.5"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        self.assertTrue(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual([call[0] for call in stats_calls], ["Initial Auto Start preflight rolling check", "Initial Auto Start auto verify"])
        self.assertEqual(stats_calls[0][1]["polls_override"], 1)
        self.assertEqual(stats_calls[0][1]["psm_sequence_override"], (6,))
        self.assertFalse(stats_calls[0][1]["candidate_signal_enabled"])
        self.assertFalse(stats_calls[0][1]["post_popup_check_enabled"])
        self.assertTrue(stats_calls[0][1]["fast_popup_checks"])
        self.assertTrue(any("auto_state=enabled_no_click" in message for message in messages))
        self.assertEqual(clicks, [])

    def test_powers_startup_compact_non_target_preflight_disabled_blocks_auto_click(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "stat_numbers_changed"
        bot.ocr_region = lambda *_args, **_kwargs: "fierce hp3.1 .damage4.7"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "disabled"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        def fake_stats_changed(_baseline, context="", **kwargs):
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                return False, _baseline
            if context == "Initial Auto Start auto verify":
                bot.last_recovery_verify_details = {
                    "reason": "popup_confirmed_mid_polling",
                    "signal_sources": ["ocr", "popup"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "popup_confirmed_mid_polling"
                return True, "tempered hp4.7 .damage4.5"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(clicks, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))
        self.assertFalse(any("startup_powers_observe_without_toggle" in message for message in messages))

    def test_powers_startup_compact_enabled_no_click_skips_double_check_after_decisive_nonconfirming_primary(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "stat_numbers_changed"
        bot.ocr_region = lambda *_args, **_kwargs: "fierce hp3.1 .damage4.7"
        bot.popup_active = lambda *_args, **_kwargs: False
        states = iter(["enabled", "enabled"])
        bot.auto_checkbox_state = lambda: next(states, "enabled")
        bot.click = lambda *_args, **_kwargs: None
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or False
        stats_calls = []

        def fake_stats_changed(_baseline, context="", **kwargs):
            stats_calls.append((context, kwargs))
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            if context == "Initial Auto Start auto verify":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {
                    "reason": "no_material_change",
                    "signal_sources": [],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual([call[0] for call in stats_calls], ["Initial Auto Start preflight rolling check", "Initial Auto Start auto verify"])
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("double_check_skipped=True" in message for message in messages))
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))

    def test_startup_guarded_recovery_decisive_nonconfirming_skips_double_check(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "Executioner"
        bot._startup_context["preflight_fallback_reason"] = "none"
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot._observe_auto_state = lambda *_args, **_kwargs: "unknown"
        bot.auto_checkbox_state = lambda: "disabled"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        stats_calls = []

        def fake_stats_changed(_baseline, context="", **kwargs):
            stats_calls.append((context, kwargs))
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            if context == "Initial Auto Start auto verify":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            if context == "Initial Auto Start guarded startup verify":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {
                    "reason": "no_material_change",
                    "signal_sources": [],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(
            [call[0] for call in stats_calls],
            ["Initial Auto Start preflight rolling check", "Initial Auto Start auto verify"],
        )
        self.assertEqual(clicks, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))

    def test_specs_safe_filler_unknown_auto_with_weak_refresh_fails_without_fake_confirm(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("specs")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "stat_numbers_changed"
        bot.ocr_region = lambda *_args, **_kwargs: "current spec damageii damage14.6"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot._observe_auto_state = lambda *_args, **_kwargs: "unknown"
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True
        stats_calls = []

        def fake_stats_changed(_baseline, context="", **kwargs):
            stats_calls.append(context)
            if context == "Initial Auto Start auto verify":
                bot.last_recovery_verify_details = {
                    "reason": "current_spec_marker_changed",
                    "signal_sources": ["ocr"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "current_spec_marker_changed"
                bot.last_recovery_verify_unreadable = False
                return True, "current spec damageii damage14.7"
            bot.last_recovery_verify_state = "not_rolling"
            bot.last_recovery_verify_details = {
                "reason": "no_material_change",
                "signal_sources": [],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "no_material_change"
            bot.last_recovery_verify_unreadable = False
            return False, _baseline

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(stats_calls, ["Initial Auto Start preflight rolling check", "Initial Auto Start auto verify"])
        self.assertEqual(clicks, [])
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("spec_safe_filler_weak_stale_evidence_rejected" in message for message in messages))
        self.assertTrue(any("spec safe filler startup avoided blind Auto click" in message for message in messages))
        self.assertTrue(any("decision=fail_safe_without_fake_confirm" in message for message in messages))
        self.assertFalse(any("Manual reroll flow" in message for message in messages))

    def test_specs_safe_filler_unknown_auto_without_useful_evidence_fails_without_click_or_manual_reroll(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("specs")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "stat_numbers_changed"
        bot.ocr_region = lambda *_args, **_kwargs: "current spec damageii damage14.6"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot._observe_auto_state = lambda *_args, **_kwargs: "unknown"
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True
        stats_calls = []

        def fake_stats_changed(_baseline, context="", **kwargs):
            stats_calls.append(context)
            bot.last_recovery_verify_state = "not_rolling"
            bot.last_recovery_verify_details = {
                "reason": "no_material_change",
                "signal_sources": [],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "no_material_change"
            bot.last_recovery_verify_unreadable = False
            return False, _baseline

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(stats_calls, ["Initial Auto Start preflight rolling check", "Initial Auto Start auto verify"])
        self.assertEqual(clicks, [])
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("spec_safe_filler_unproven_auto_state_fail_safe" in message for message in messages))
        self.assertTrue(any("manual reroll blocked for safe filler because current roll was not BAD/DISABLED" in message for message in messages))

    def test_specs_safe_filler_disabled_auto_blocks_startup_click_and_does_not_manual_reroll(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("specs")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "stat_numbers_changed"
        bot.ocr_region = lambda *_args, **_kwargs: "current spec damageii damage14.6"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "disabled"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or False
        stats_calls = []

        def fake_stats_changed(_baseline, context="", **kwargs):
            stats_calls.append(context)
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            if context == "Initial Auto Start auto verify":
                bot.last_recovery_verify_state = "rolling"
                bot.last_recovery_verify_details = {
                    "reason": "stat_numbers_changed",
                    "signal_sources": ["ocr", "image_change"],
                    "image_changed_samples": 1,
                    "max_change_score": 8.0,
                }
                bot.last_recovery_reason = "stat_numbers_changed"
                bot.last_recovery_verify_unreadable = False
                return True, "current spec damageii damage14.7"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(stats_calls, ["Initial Auto Start preflight rolling check"])
        self.assertEqual(clicks, [])
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))

    def test_specs_startup_weak_marker_change_does_not_manual_reroll_without_bad_or_popup(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("specs")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "weak_non_improving_dead_phase"
        bot.ocr_region = lambda *_args, **_kwargs: "came"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "disabled"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True
        stats_calls = []

        def fake_stats_changed(_baseline, context="", **kwargs):
            stats_calls.append(context)
            bot.last_recovery_verify_state = "rolling"
            bot.last_recovery_verify_details = {
                "reason": "current_spec_marker_changed",
                "signal_sources": ["current_spec_refresh"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
                "classification": "rolling",
            }
            bot.last_recovery_reason = "current_spec_marker_changed"
            bot.last_recovery_verify_unreadable = False
            return True, "current-spec. critchanceiii critchance1.1"

        bot.stats_changed = fake_stats_changed

        self.assertTrue(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(manual_calls, [])
        self.assertEqual(clicks, [])
        self.assertEqual(stats_calls, ["Initial Auto Start preflight rolling check"])
        self.assertTrue(any("startup_specs_observe_without_toggle" in message for message in messages))
        self.assertTrue(any("decision=skip_toggle_observe_first" in message for message in messages))
        self.assertFalse(any("Auto-roll still not confirmed after double check. Using manual reroll fallback." in message for message in messages))

    def test_specs_startup_unknown_checkbox_with_roll_like_ocr_observes_without_click(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("specs")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "weak_non_improving_dead_phase"
        bot.ocr_region = lambda *_args, **_kwargs: "came"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True

        def fake_stats_changed(_baseline, context="", **kwargs):
            bot.last_recovery_verify_state = "rolling"
            bot.last_recovery_verify_details = {
                "reason": "current_spec_marker_changed",
                "signal_sources": ["current_spec_refresh"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
                "classification": "rolling",
            }
            bot.last_recovery_reason = "current_spec_marker_changed"
            bot.last_recovery_verify_unreadable = False
            return True, "current-spec. damageii damage24.9"

        bot.stats_changed = fake_stats_changed

        self.assertTrue(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(clicks, [])
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("startup_specs_observe_without_toggle" in message for message in messages))
        self.assertTrue(any("auto_state=unknown" in message and "decision=skip_toggle_observe_first" in message for message in messages))

    def test_powers_safe_filler_unresolved_startup_still_blocks_manual_reroll(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "manual_probe_required"
        bot.ocr_region = lambda *_args, **_kwargs: "current power fierce damage4.7"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot._observe_auto_state = lambda *_args, **_kwargs: "unknown"
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True

        def fake_stats_changed(_baseline, context="", **kwargs):
            bot.last_recovery_verify_state = "not_rolling"
            bot.last_recovery_verify_details = {
                "reason": "no_material_change",
                "signal_sources": [],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "no_material_change"
            bot.last_recovery_verify_unreadable = False
            return False, _baseline

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(clicks, [])
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))
        self.assertFalse(any("spec_safe_filler_auto_resume_unresolved_manual_fallback" in message for message in messages))

    def test_powers_startup_compact_non_target_preflight_unknown_blocks_bounded_recovery_click(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "stat_numbers_changed"
        bot.ocr_region = lambda *_args, **_kwargs: "fierce hp3.1 .damage4.7"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bounded_calls = []

        def fake_stats_changed(_baseline, context="", **kwargs):
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                return False, _baseline
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed
        bot._attempt_auto_reenable_once = lambda *args, **kwargs: bounded_calls.append((args, kwargs)) or True

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(clicks, [])
        self.assertEqual(bounded_calls, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))
        self.assertFalse(any("startup_powers_observe_without_toggle" in message for message in messages))

    def test_powers_startup_compact_disabled_blocks_initial_click(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "stat_numbers_changed"
        bot.ocr_region = lambda *_args, **_kwargs: "fierce hp3.1 .damage4.7"
        bot.popup_active = lambda *_args, **_kwargs: False
        states = iter(["disabled", "disabled"])
        bot.auto_checkbox_state = lambda: next(states, "disabled")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        def fake_stats_changed(_baseline, context="", **kwargs):
            if context == "Initial Auto Start preflight rolling check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                return False, _baseline
            if context == "Initial Auto Start auto verify":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {
                    "reason": "no_material_change",
                    "signal_sources": [],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            if context == "Initial Auto Start double check":
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {
                    "reason": "no_material_change",
                    "signal_sources": [],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "no_material_change"
                bot.last_recovery_verify_unreadable = False
                return False, _baseline
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(clicks, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))

    def test_startup_defers_force_shard_priming_until_first_loop_iteration(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["STARTUP_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.startup_check_current_roll = lambda: "rerolled"
        bot.start_live_status = lambda: messages.append("LIVE_STATUS_STARTED")
        bot._finish_startup_summary = lambda *_args, **_kwargs: messages.append("STARTUP_SUMMARY_DONE")
        bot.finish_live_status = lambda *_args, **_kwargs: None
        bot.should_check_passive_shards_empty = lambda _count: False
        bot.should_check_power_shards_empty = lambda _count: False
        bot.passive_shards_empty_confirmed = lambda _count: False
        bot.power_shards_empty_confirmed = lambda _count: False

        def passive_report(force=False):
            messages.append(f"PASSIVE_FORCE={force}")
            return 10

        def power_report(force=False):
            messages.append(f"POWER_FORCE={force}")
            return 8

        bot.maybe_report_passive_shards = passive_report
        bot.maybe_report_power_shards = power_report

        def fake_check_roll():
            bot.stop_event.set()
            return "ROLLING", None, "", "", [], False

        bot.check_roll = fake_check_roll

        bot.loop()

        summary_idx = messages.index("STARTUP_SUMMARY_DONE")
        passive_force_idx = messages.index("PASSIVE_FORCE=True")
        power_force_idx = messages.index("POWER_FORCE=True")
        self.assertLess(summary_idx, passive_force_idx)
        self.assertLess(summary_idx, power_force_idx)

    def test_unsupported_power_non_target_does_not_enter_manual_reroll(self):
        bot = StubBot(
            [
                (
                    "tesseract-test",
                    "ascendant > damage 12.2%, crit chance 2.1%, hp 14.0%",
                    "Ascendant > Damage 12.2%, Crit Chance 2.1%, HP 14.0%",
                )
            ]
        )
        bot.set_roll_domain("powers")
        bot.manual_reroll_flow = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unsupported/filler powers should not enter manual reroll")
        )

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "NON_TARGET")
        self.assertEqual(trait, "non_target_power")
        self.assertIn("Unsupported or filler power observed", summary)
        self.assertEqual(missing, ["Non-target power"])
        self.assertFalse(near)

    def test_disabled_supported_power_autoskips_without_manual_reroll(self):
        bot = StubBot(
            [
                (
                    "tesseract-test",
                    "Colossus > +23.4% Boss DMG, Damage 22.2%, Crit Chance 1.8%, Luck 14.6%, HP 27.8%, Crit Damage 7.6%",
                    "Colossus > +23.4% Boss DMG, Damage 22.2%, Crit Chance 1.8%, Luck 14.6%, HP 27.8%, Crit Damage 7.6%",
                )
            ]
        )
        bot.set_roll_domain("powers")
        bot.set_enabled_powers({"cursebrand", "subjugator"})
        bot.manual_reroll_flow = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("disabled supported powers should autoskip, not manual reroll")
        )

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "NON_TARGET")
        self.assertEqual(trait, "non_target_power")
        self.assertIn("not enabled", summary)
        self.assertEqual(missing, ["Autoskip power"])
        self.assertFalse(near)
        self.assertTrue(any("AUTOSKIP Power | trait=Colossus" in message for message in bot.messages))

    def test_power_loop_bad_uses_fast_confirmation_for_coherent_stable_read(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        self.apply_subjugator_luck_target(bot)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["STARTUP_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.startup_check_current_roll = lambda: "rerolled"
        bot._finish_startup_summary = lambda *_args, **_kwargs: None
        bot.finish_live_status = lambda *_args, **_kwargs: None
        bot.start_live_status = lambda: None
        bot.maybe_report_passive_shards = lambda force=False: 10
        bot.maybe_report_power_shards = lambda force=False: 10
        bot.should_check_passive_shards_empty = lambda _count: False
        bot.should_check_power_shards_empty = lambda _count: False
        bot.passive_shards_empty_confirmed = lambda _count: False
        bot.power_shards_empty_confirmed = lambda _count: False
        bad_text = "Subjugator NPC Slow 20% 5s Damage 36.8 Crit Chance 2.8 Luck 9.4 HP 34.4 Crit Damage 10.2"
        check_calls = []

        def fake_check_roll(*args, **kwargs):
            check_calls.append(kwargs)
            return self.evaluate_power_text(bot, bad_text, "loop")

        bot.check_roll = fake_check_roll

        def manual_reroll(reason=""):
            bot.stop_event.set()
            return True

        bot.manual_reroll_flow = manual_reroll

        bot.loop()

        self.assertGreaterEqual(len(check_calls), 2)
        self.assertEqual(check_calls[1], {"allow_fallback": False, "startup_fast": False})
        self.assertTrue(any("Loop Power BAD manual reroll confirmed | route=fast_power_probe" in message for message in messages))

    def test_weak_power_bad_chain_does_not_use_fast_confirmation(self):
        bot = AelrithForgeBot(lambda *_: None, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.last_decision_chain = {
            "classification": "BAD",
            "current_trait": "Subjugator",
            "power_parse_coherent": False,
            "power_candidate_quality": 150,
            "power_required_values": {"Luck": None},
        }

        self.assertFalse(bot._power_bad_fast_confirm_allowed("subjugator"))

    def test_power_check_skips_fallback_for_coherent_bad_fast_read(self):
        class FastPowerBot(AelrithForgeBot):
            def __init__(self, text):
                self.messages = []
                super().__init__(self.messages.append, lambda *_: None)
                self.cfg["OCR_DEBUG_FILE"] = False
                self.text = text
                self.calls = []

            def get_stats_ocr_candidates(self, *args, **kwargs):
                self.calls.append(kwargs)
                if kwargs.get("fallback_only"):
                    raise AssertionError("coherent BAD power should not need fallback OCR")
                if kwargs.get("fast_loop"):
                    return [("fast-loop", self.text, self.text)]
                return [("primary", self.text, self.text)]

        bad_text = "Subjugator NPC Slow 20% 5s Damage 36.8 Crit Chance 2.8 Luck 9.4 HP 34.4 Crit Damage 10.2"
        bot = FastPowerBot(bad_text)
        self.apply_subjugator_luck_target(bot)

        state, trait, _summary, _text, missing, _near = bot.check_roll()

        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "subjugator")
        self.assertTrue(any("Luck" in item for item in missing))
        self.assertEqual(bot.calls, [{"startup_fast": False, "fast_loop": True}])

    def test_powers_startup_verify_sample_bad_power_manual_rerolls(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        self.apply_subjugator_luck_target(bot)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot._begin_startup_context("unit test")
        bot._startup_context["current_spec_class"] = "NON_TARGET filler"
        bot._startup_context["preflight_fallback_reason"] = "manual_probe_required"
        bot.ocr_region = lambda *_args, **_kwargs: "battleborn hp7.1 damage5.7"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot._observe_auto_state = lambda *_args, **_kwargs: "unknown"
        bot.auto_checkbox_state = lambda: "unknown"
        bot.click = lambda *_args, **_kwargs: None
        bad_text = "Subjugator NPC Slow 20% 5s Damage 36.8 Crit Chance 2.8 Luck 9.4 HP 34.4 Crit Damage 10.2"

        def fake_stats_changed(_baseline, context="", **_kwargs):
            bot.last_recovery_verify_state = "not_rolling"
            bot.last_recovery_verify_details = {
                "classification": "not_rolling",
                "rejection_reason": "readable_insufficient_change",
                "reason": "readable_insufficient_change",
                "signal_sources": ["ocr", "image_change"],
                "image_changed_samples": 1,
                "max_change_score": 7.0,
                "samples_detail": [
                    {
                        "cleaned": bad_text,
                        "unreliable": False,
                        "materially_different": True,
                        "trait_only": False,
                        "image_changed": True,
                    }
                ],
            }
            bot.last_recovery_reason = "readable_insufficient_change"
            bot.last_recovery_verify_unreadable = False
            return False, _baseline

        bot.stats_changed = fake_stats_changed
        bot.check_roll = lambda allow_fallback=True, startup_fast=False: self.evaluate_power_text(bot, bad_text, "confirm")
        manual_calls = []

        def manual_reroll(reason=""):
            manual_calls.append(reason)
            bot.last_manual_reroll_confirmed_at = time.perf_counter()
            return True

        bot.manual_reroll_flow = manual_reroll

        self.assertTrue(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(manual_calls, ["initial auto start current bad subjugator"])
        self.assertTrue(any("Startup verification saw supported BAD Power" in message for message in messages))

    def test_startup_high_value_current_spec_stops_as_before(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.check_roll = lambda *args, **kwargs: (
            "HIGH_VALUE",
            "rampage",
            "Combo Ramp 30 | Damage 29 | Crit Rate 4 | Crit Damage 9",
            "current spec rampage combo ramp 30 damage 29 crit chance 4 crit damage 9",
            ["high value threshold met"],
            False,
        )
        bot.on_near_miss = lambda *_args, **_kwargs: None
        bot.send_near_miss_alert = lambda *_args, **_kwargs: None

        self.assertEqual(bot.startup_check_current_roll(), "stop")
        self.assertTrue(any("Startup fast current-spec check | state=HIGH_VALUE" in message for message in messages))

    def test_startup_god_current_spec_stops_as_before(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.check_roll = lambda *args, **kwargs: (
            "GOD",
            "rampage",
            "Combo Ramp 30 | Damage 30 | Crit Rate 4 | Crit Damage 10",
            "current spec rampage combo ramp 30 damage 30 crit chance 4 crit damage 10",
            [],
            False,
        )
        bot.on_god_roll = lambda *_args, **_kwargs: None

        self.assertEqual(bot.startup_check_current_roll(), "stop")
        self.assertTrue(any("Startup check | KEEP RAMPAGE already on screen" in message for message in messages))

    def test_startup_unreadable_current_spec_falls_back_to_initial_auto_start(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.check_roll = lambda *args, **kwargs: ("ROLLING", None, "", "junk", [], False)
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True

        self.assertEqual(bot.startup_check_current_roll(), "continue")
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("Startup current-spec not reliable; falling back to Initial Auto Start" in message for message in messages))

    def test_recovery_failure_allows_retries_before_stopping(self):
        bot = self.make_bot()
        bot.cfg["MAX_RECOVERY_ATTEMPTS"] = 3
        self.assertFalse(bot.recovery_failed_should_stop("Stuck Recovery", "first miss"))
        self.assertFalse(bot.recovery_failed_should_stop("Stuck Recovery", "second miss"))
        self.assertTrue(bot.recovery_failed_should_stop("Stuck Recovery", "third miss"))

    def test_extracts_fortune_chosen_stat_labels(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "fortune",
            "current spec fortune chosen drop 29.7 luck 9.4",
        )
        self.assertEqual(values, [29.7, 9.4])

    def test_extracts_fortune_chosen_when_labels_are_glued_to_values(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "fortune",
            "fortunechosen 28.0 chance 1drop. damarge10.3 .luck5.2",
        )
        self.assertEqual(values, [28.0, 5.2])

    def test_tesseract_config_is_windows_shlex_safe(self):
        bot = self.make_bot()
        config = bot._tesseract_config(7)
        args = shlex.split(config, posix=False)
        self.assertIn("tessedit_char_whitelist=", args[-1])
        self.assertNotIn('"', config)

    def test_extracts_executioner_stat_labels(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "executioner",
            "current spec executioner npc dmg 44.5 crit chance 3.5 crit damage 14.2",
        )
        self.assertEqual(values, [44.5, 3.5, 14.2])

    def test_extracts_executioner_with_common_ocr_crit_typos(self):
        bot = self.make_bot()
        easy_values = bot.extract_labeled_values(
            "executioner",
            "CURRENT SPEC Executioner > Below 50%b HP: +41.5% DMG, ait @ance 3.1%, Git Damage 7.6%",
        )
        psm_values = bot.extract_labeled_values(
            "executioner",
            "CURRENT-SPEC Executioner > Below 50% HP: +41.5% D.: uit Chance 3.1%, Crit Darmaee 6%",
        )
        merged = bot.merge_labeled_values("executioner", easy_values, psm_values)
        self.assertEqual(easy_values, [41.5, 3.1, 7.6])
        self.assertEqual(psm_values, [None, 3.1, 6.0])
        self.assertEqual(merged, [41.5, 3.1, 7.6])

    def test_executioner_parser_repairs_decimal_dash_and_integer_decimal_loss(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "executioner",
            "current spec eexecutionerrioner below 50 k hp 44-9 dmg. ait cance 2.5 . crit damage 109",
        )
        self.assertEqual(values, [44.9, 2.5, 10.9])

    def test_stat_normalization_aliases_and_fuzzy_labels(self):
        self.assertEqual(canonical_stat_key("executioner npc dmg"), "npc_damage")
        self.assertEqual(canonical_stat_key("npc dmq", cutoff=0.58), "npc_damage")
        self.assertEqual(canonical_stat_key("critdanuge", cutoff=0.58), "crit_damage")
        self.assertEqual(canonical_stat_key("gritdamage", cutoff=0.58), "crit_damage")
        self.assertEqual(canonical_stat_key("ciitdaitage", cutoff=0.58), "crit_damage")
        self.assertIn("npc_damage", normalize_stat_tokens("Executioner NPC DMG 44.5"))
        self.assertIn("crit_damage", normalize_stat_tokens("CritDanuge7.2%"))

    def test_extracts_rampage_stat_labels_without_confusing_crit_damage(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "rampage",
            "current spec rampage combo ramp 16.8 cap damage 29.2 crit rate 3.2 crit damage 9.6",
        )
        self.assertEqual(values, [16.8, 29.2, 3.2, 9.6])

    def test_extracts_rampage_from_screenshot_style_text(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "rampage",
            "rampage > combo ramp: 16.8%, damage 24.3%, crit chance 2.8%, crit damage 8.8%",
        )
        self.assertEqual(values, [16.8, 24.3, 2.8, 8.8])

    def test_structured_rampage_pairing_uses_nearest_following_values(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "rampage",
            "Rampage > Combo Ramp: 22.6% Cap, Damage 19.1%, Crit Chance 3.0%, Crit Damage 6.8%",
        )
        self.assertEqual(values, [22.6, 19.1, 3.0, 6.8])

    def test_extracts_rampage_when_crit_labels_are_glued_to_values(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "rampage",
            "rampage combo ramp 22.0 cap. damage 19.1 . critchance3.0 .critdamage6.8",
        )
        self.assertEqual(values, [22.0, 19.1, 3.0, 6.8])

    def test_rampage_ordered_parse_keeps_damage_distinct_from_crit_damage(self):
        bot = self.make_bot()
        values, debug = bot.extract_labeled_values(
            "rampage",
            "rampage comboramp 27.9 cap.damage 16.5 critchance 2.0 crit damage 8.5",
            return_debug=True,
        )
        self.assertEqual(values, [27.9, 16.5, 2.0, 8.5])
        self.assertFalse(debug["parse_errors"])
        self.assertIn("damage:16.5", " ".join(debug.get("ordered_segments", [])))

    def test_extracts_rampage_crit_damage_from_mangled_trailing_label(self):
        bot = self.make_bot()
        values, debug = bot.extract_labeled_values(
            "rampage",
            "Rampage>ComboRamp:26.5%Cap,Damage 28.40%CritChance3.2%,CritDanuge7.2%",
            return_debug=True,
        )
        self.assertEqual(values, [26.5, 28.4, 3.2, 7.2])
        self.assertFalse(debug["parse_errors"])
        self.assertTrue(any("Crit Damage recovered from fuzzy OCR label" in item for item in debug["detected_labels"]))

    def test_extracts_rampage_crit_damage_from_gritdamage_decimal_loss(self):
        bot = self.make_bot()
        values, debug = bot.extract_labeled_values(
            "rampage",
            "Rampage ComboRamp26.5 Cap Damage28.4 CritChance32 GritDamage 72",
            return_debug=True,
        )
        self.assertEqual(values, [26.5, 28.4, 3.2, 7.2])
        self.assertFalse(debug["parse_errors"])

    def test_extracts_rampage_crit_damage_from_ciitdaitage_label(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "rampage",
            "Rampage Combo Ramp 26.5 Damage 28.4 Crit Chance 3.2 CiitDaitage7.2%",
        )
        self.assertEqual(values, [26.5, 28.4, 3.2, 7.2])

    def test_rampage_parser_ignores_noisy_number_after_valid_crit_rate(self):
        bot = self.make_bot()
        values, debug = bot.extract_labeled_values(
            "rampage",
            "Rampage ComboRamp26.5 Damage28.4 CritChance3.2 296 CritDanuge7.2",
            return_debug=True,
        )
        self.assertEqual(values, [26.5, 28.4, 3.2, 7.2])
        self.assertFalse(debug["parse_errors"])
        self.assertTrue(any("ignored noisy candidate 296" in item for item in debug["detected_labels"]))

    def test_extracts_rampage_damage_from_dalage_ocr_typo(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "rampage",
            "rampage combo ramp 21.4ycap.dalage 21.7 .critchance3.7 .critdamage7.9",
        )
        self.assertEqual(values, [21.4, 21.7, 3.7, 7.9])

    def test_rampage_candidate_merge_keeps_better_damage_reading(self):
        bot = self.make_bot()
        parsed = bot._parse_stat_ocr_candidates(
            [
                (
                    "tesseract-full-threshold-psm6",
                    "rampage combo ramp 21.4ycap.dalage 21.7 .critchance3.7 .critdamage7.9",
                    "Rampage>Combo Ramp: 21.4yCap,Dalage\n21.7%,CritChance3.7%,CritDamage7.9%",
                ),
                (
                    "tesseract-full-original-psm6",
                    "ge combo 21.4 cap.damage 2.7 critchance 379 . critdamage 7.9",
                    "ge>Combo :21.4%Cap,Damage\n2.7% CritChance 379%, CritDamage 7.9%",
                ),
            ],
            bad_panel_words=[],
        )
        self.assertEqual(parsed["merged_values"], [21.4, 21.7, 3.7, 7.9])

    def test_rampage_fragment_damage_read_is_not_usable_parse(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        parsed = bot._parse_stat_ocr_candidates(
            [
                (
                    "fragment",
                    "rampage damagei damage5.0",
                    "Rampage DamageI>Damage5.0%",
                )
            ],
            bad_panel_words=[],
        )
        self.assertIsNone(parsed["trait"])
        self.assertEqual(parsed["source_name"], "fragment")
        self.assertEqual(parsed["merged_values"], [])
        self.assertTrue(any("Rejected fragmentary Rampage read" in message for message in messages))

    def test_repeated_rampage_fragment_rejections_are_deduped(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        candidate = (
            "fragment",
            "rampage damagei damage5.0",
            "Rampage DamageI>Damage5.0%",
        )
        for _ in range(3):
            parsed = bot._parse_stat_ocr_candidates([candidate], bad_panel_words=[])
            self.assertIsNone(parsed["trait"])
        self.assertEqual(sum("Rejected fragmentary Rampage read" in message for message in messages), 1)

    def test_repeated_rampage_fragment_rejections_emit_grouped_summary(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        candidate = (
            "fragment",
            "rampage damagei damage5.0",
            "Rampage DamageI>Damage5.0%",
        )
        for _ in range(11):
            parsed = bot._parse_stat_ocr_candidates([candidate], bad_panel_words=[])
            self.assertIsNone(parsed["trait"])
        self.assertEqual(sum("Rejected fragmentary Rampage read" in message for message in messages), 1)
        self.assertTrue(any("Suppressed repeated fragmentary Rampage rejection x10" in message for message in messages))

    def test_near_identical_rampage_fragments_are_grouped(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        for raw in (
            "Rampage DamageI>Damage5.0%",
            "Rampage DamageI>Damage5.1%",
            "Rampage DamageI>Damage5.2%",
            "Rampage DamageI>Damage5.3%",
        ):
            parsed = bot._parse_stat_ocr_candidates(
                [("fragment", normalize_ocr_text(raw), raw)],
                bad_panel_words=[],
            )
            self.assertIsNone(parsed["trait"])
        self.assertEqual(sum("Rejected fragmentary Rampage read" in message for message in messages), 1)
        self.assertFalse(any("Suppressed repeated fragmentary Rampage rejection" in message for message in messages))

    def test_materially_different_rampage_fragments_still_log(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._parse_stat_ocr_candidates(
            [("fragment-a", "rampage damagei damage5.0", "Rampage DamageI>Damage5.0%")],
            bad_panel_words=[],
        )
        bot._parse_stat_ocr_candidates(
            [("fragment-b", "rampage damagei damage8.0", "Rampage DamageI>Damage8.0%")],
            bad_panel_words=[],
        )
        self.assertEqual(sum("Rejected fragmentary Rampage read" in message for message in messages), 2)

    def test_rampage_candidate_selection_prefers_coherent_damage_parse(self):
        bot = self.make_bot()
        parsed = bot._parse_stat_ocr_candidates(
            [
                (
                    "high-ocr-quality-but-collided",
                    "current spec rampage combo ramp 27.9 damage 8.5 crit chance 2.0 crit damage 8.5",
                    "CURRENT SPEC Rampage Combo Ramp 27.9 Damage 8.5 Crit Chance 2.0 Crit Damage 8.5",
                ),
                (
                    "lower-ocr-quality-coherent",
                    "rampage comboramp 27.9 cap.damage 16.5 critchance 2.0 crit damage 8.5",
                    "Rampage>ComboRamp:27.9%Cap,Damage 16.5%CritChance2.0%,CritDamage8.5%",
                ),
            ],
            bad_panel_words=[],
        )
        self.assertEqual(parsed["source_name"], "lower-ocr-quality-coherent")
        self.assertEqual(parsed["merged_values"], [27.9, 16.5, 2.0, 8.5])

    def test_rampage_candidate_selection_rejects_clean_fragment_for_noisier_structure(self):
        bot = self.make_bot()
        parsed = bot._parse_stat_ocr_candidates(
            [
                (
                    "clean-fragment",
                    "current spec rampage damagei damage8.0",
                    "CURRENT SPEC Rampage DamageI>Damage8.0%",
                ),
                (
                    "noisier-structured",
                    "rampage comboramp 27.9 cap.dainage 16.5 critchance 2.0 gait damage 8.5",
                    "Rampage>ComboRamp:27.9%Cap,Dainage 16.5%CritChance2.0%,GaitDamage8.5%",
                ),
            ],
            bad_panel_words=[],
        )
        self.assertEqual(parsed["source_name"], "noisier-structured")
        self.assertEqual(parsed["merged_values"], [27.9, 16.5, 2.0, 8.5])

    def test_rampage_parser_rejects_implausible_stat_pairing(self):
        bot = self.make_bot()
        values, debug = bot.extract_labeled_values(
            "rampage",
            "current spec rampage combo ramp 16.8 crit rate 29.2 crit damage 8.8",
            return_debug=True,
        )
        self.assertEqual(values, [16.8, None, None, 8.8])
        self.assertTrue(any("Crit Rate" in error for error in debug["parse_errors"]))

    def test_rampage_parser_repairs_missing_decimal_percent_ocr(self):
        bot = self.make_bot()
        values, debug = bot.extract_labeled_values(
            "rampage",
            "current spec rampage combo paugjo 245 cap damage 17.9 git clance 3.7 crit damage 74",
            return_debug=True,
        )
        self.assertEqual(values, [24.5, 17.9, 3.7, 7.4])
        self.assertTrue(any("corrected" in label for label in debug["detected_labels"]))

    def test_rampage_preview_ocr_typo_still_detects_trait_and_crit_rate(self):
        bot = self.make_bot()
        text = "current spec rgxaga combo ramp 22.6 cap. ait onance 3.0 . crit damage a133e"
        self.assertEqual(bot_module.detect_trait(text), "rampage")
        values = bot.extract_labeled_values("rampage", text)
        self.assertEqual(values, [22.6, None, 3.0, None])

    def test_rampage_parser_repairs_damage_decimal_loss(self):
        bot = self.make_bot()
        values = bot.extract_labeled_values(
            "rampage",
            "current spec rampage combo ramp 22.6 damage 191 crit chance 30 crit damage 68",
        )
        self.assertEqual(values, [22.6, 19.1, 3.0, 6.8])

    def test_rampage_parser_rejects_orphan_damage_debris_between_labels(self):
        bot = self.make_bot()
        values, debug = bot.extract_labeled_values(
            "rampage",
            "currentspec. -rampage comboramp 17.5 cap.damage r1bmcaitchance38.gtdakige736",
            return_debug=True,
        )
        self.assertEqual(values, [17.5, None, 3.8, 7.36])
        self.assertTrue(any("ignored orphan OCR debris" in item for item in debug["detected_labels"]))

    def test_extracts_passive_shard_count(self):
        bot = self.make_bot()
        self.assertEqual(bot.extract_passive_shards("Passive Shards: 1,240"), 1240)
        self.assertEqual(bot.extract_passive_shards("shards 0"), 0)
        self.assertEqual(bot.extract_passive_shards("Passive Shards: 47.1k"), 47100)
        self.assertEqual(bot.extract_passive_shards("Passive Shards: 47,1k"), 47100)
        self.assertEqual(bot.extract_passive_shards("Passive Shards: 47lk"), 47100)
        self.assertEqual(bot.extract_passive_shards("Passive Shards: 47ik"), 47100)
        self.assertEqual(bot.extract_passive_shards("Passive Shards: 1.2m"), 1200000)
        self.assertEqual(bot.extract_passive_shards("Passive Shards: 1200"), 1200)
        self.assertEqual(bot.extract_passive_shards("51.2k Passive Shards"), 51200)
        self.assertEqual(bot.extract_passive_shards("51 2K"), 51200)
        self.assertEqual(bot.extract_passive_shards("201K Passive Shards"), 201000)
        self.assertEqual(bot.extract_passive_shards("20.1K Passive Shards"), 20100)
        self.assertEqual(bot.extract_passive_shards("2.01K Passive Shards"), 2010)
        self.assertEqual(bot.extract_passive_shards("201k"), 201000)
        self.assertIsNone(bot.extract_passive_shards("Be"))
        self.assertIsNone(bot.extract_passive_shards("OPassiveShards"))

    def test_passive_shard_sanity_check_preserves_plain_three_digit_k_values(self):
        bot = self.make_bot()
        bot.last_passive_shards = 47000
        self.assertEqual(bot.extract_passive_shards("Passive Shards: 471k"), 471000)

    def test_passive_shard_region_preserves_plain_three_digit_k_values(self):
        value, normalized = parse_passive_shard_count("Passive Shards: 512K", infer_missing_suffix=True)
        self.assertEqual(normalized, "512k")
        self.assertEqual(value, 512000)

    def test_passive_shard_explicit_suffix_candidate_wins(self):
        value, normalized, source = bot_module._parse_passive_shard_count_detail(
            "201K Passive Shards",
            infer_missing_suffix=True,
        )
        self.assertEqual(normalized, "201k")
        self.assertEqual(value, 201000)
        self.assertEqual(source, "suffix")

    def test_passive_shard_region_infers_missing_k_suffix(self):
        value, normalized = parse_passive_shard_count("Passive Shards: 56", infer_missing_suffix=True)
        self.assertEqual(normalized, "56")
        self.assertEqual(value, 56000)

    def test_passive_shard_region_infers_missing_k_suffix_with_decimal(self):
        value, normalized = parse_passive_shard_count("56.3 PassiveShards", infer_missing_suffix=True)
        self.assertEqual(normalized, "56.3")
        self.assertEqual(value, 56300)

    def test_passive_shard_region_preserves_plain_three_digit_k_with_zero(self):
        value, normalized = parse_passive_shard_count("Passive Shards: 560k", infer_missing_suffix=True)
        self.assertEqual(normalized, "560k")
        self.assertEqual(value, 560000)

    def test_passive_shard_region_repairs_s_for_five_before_k(self):
        value, normalized = parse_passive_shard_count("S5'GK PassiveShards", previous_value=55000, infer_missing_suffix=True)
        self.assertEqual(normalized, "55k")
        self.assertEqual(value, 55000)

    def test_passive_shard_region_recovers_decimal_split_before_k(self):
        value, normalized = parse_passive_shard_count("= 55'9K' Passive:Shards", infer_missing_suffix=True)
        self.assertEqual(normalized, "55.9k")
        self.assertEqual(value, 55900)

    def test_passive_shard_plain_integer_default_stays_integer(self):
        value, _normalized = parse_passive_shard_count("Passive Shards: 56")
        self.assertEqual(value, 56)

    def test_passive_shard_reporting_logs_parse_skip(self):
        bot = PassiveShardStubBot(
            [
                {
                    "mode": "raw",
                    "psm": 7,
                    "raw": "Be",
                    "normalized": "",
                    "parsed": None,
                    "formatted": "not found",
                    "reason": "no normalized digits",
                }
            ]
        )
        self.assertIsNone(bot.maybe_report_passive_shards(force=True))
        self.assertTrue(any("Passive shard OCR rejected as garbage" in message for message in bot.messages))
        self.assertTrue(any("Passive shard report skipped" in message for message in bot.messages))

    def test_passive_shard_report_failure_retains_previous_valid_value(self):
        bot = PassiveShardStubBot(
            [
                {
                    "mode": "raw",
                    "psm": 7,
                    "raw": "Be",
                    "normalized": "",
                    "parsed": None,
                    "formatted": "not found",
                    "reason": "no normalized digits",
                }
            ]
        )
        bot.last_passive_shards = 201000
        self.assertEqual(bot.maybe_report_passive_shards(force=True), 201000)
        self.assertEqual(bot.last_passive_shards, 201000)
        self.assertTrue(any("retaining previous valid value 201,000" in message for message in bot.messages))

    def test_passive_shard_report_failure_dedups_repeated_skip_log(self):
        bot = PassiveShardStubBot(
            [
                {
                    "mode": "raw",
                    "psm": 7,
                    "raw": "Be",
                    "normalized": "",
                    "parsed": None,
                    "formatted": "not found",
                    "reason": "no normalized digits",
                }
            ]
        )
        bot.last_passive_shards = 201000
        bot.maybe_report_passive_shards(force=True)
        bot.maybe_report_passive_shards(force=True)
        self.assertEqual(
            sum(
                "Passive shard report skipped: no valid shard count parsed; retaining previous valid value" in message
                for message in bot.messages
            ),
            1,
        )

    def test_passive_shard_offtarget_roll_text_backs_off_in_powers_mode(self):
        class CountingPassiveShardBot(PassiveShardStubBot):
            def __init__(self, attempts):
                super().__init__(attempts)
                self.calls = 0

            def passive_shard_ocr_attempts(self, image=None, region=None):
                self.calls += 1
                return super().passive_shard_ocr_attempts(image=image, region=region)

        bot = CountingPassiveShardBot(
            [
                {
                    "mode": "raw",
                    "psm": 7,
                    "raw": "Mythi",
                    "normalized": "",
                    "parsed": None,
                    "formatted": "not found",
                    "reason": "no normalized digits",
                },
                {
                    "mode": "gray",
                    "psm": 6,
                    "raw": "Non-targetPow",
                    "normalized": "",
                    "parsed": None,
                    "formatted": "not found",
                    "reason": "no normalized digits",
                },
            ]
        )
        bot.set_roll_domain("powers")
        bot.last_passive_shards = 201000

        self.assertIsNone(bot.read_passive_shards())
        self.assertEqual(bot.read_passive_shards(), 201000)
        self.assertEqual(bot.calls, 1)
        self.assertGreater(bot._passive_shard_backoff_until, time.time())
        self.assertTrue(any("backing off repeated reads" in message for message in bot.messages))

    def test_power_shard_reporting_still_runs_while_passive_backoff_is_active(self):
        bot = PowerShardStubBot(
            [
                {
                    "mode": "raw",
                    "psm": 7,
                    "raw": "473K Power Shards",
                    "normalized": "473k",
                    "parsed": 473000,
                    "formatted": "473,000",
                    "reason": "parsed",
                    "candidate_type": "explicit_suffix",
                }
            ]
        )
        bot.set_roll_domain("powers")
        bot._passive_shard_backoff_until = time.time() + 60

        self.assertEqual(bot.maybe_report_power_shards(force=True), 473000)
        self.assertEqual(bot.last_power_shards, 473000)

    def test_passive_shard_state_keeps_previous_value_after_garbage_ocr(self):
        bot = PassiveShardStubBot(
            [
                {
                    "mode": "raw",
                    "psm": 7,
                    "raw": "OPassiveShards",
                    "normalized": "",
                    "parsed": None,
                    "formatted": "not found",
                    "reason": "no normalized digits",
                }
            ]
        )
        bot.last_passive_shards = 51200
        self.assertIsNone(bot.read_passive_shards())
        self.assertEqual(bot.last_passive_shards, 51200)
        self.assertTrue(any("keeping previous valid value" in message for message in bot.messages))

    def test_passive_shard_threshold_alert_crossing_and_cooldown(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["PASSIVE_SHARD_ALERT_COOLDOWN"] = 3600
        self.assertTrue(bot._emit_passive_shard_threshold_alert(9000, "low"))
        self.assertFalse(bot._emit_passive_shard_threshold_alert(8500, "low"))
        self.assertTrue(bot._emit_passive_shard_threshold_alert(4500, "very_low"))
        self.assertTrue(any("Passive shards low" in message for message in messages))
        self.assertTrue(any("alert suppressed by cooldown" in message for message in messages))

    def test_passive_shard_empty_stop_requires_valid_empty_read(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        self.assertTrue(bot.cfg["STOP_ON_EMPTY_PASSIVE_SHARDS"])
        self.assertFalse(bot.passive_shards_empty_confirmed(None))
        self.assertFalse(bot.passive_shards_empty_confirmed(1))
        self.assertFalse(bot.passive_shards_empty_confirmed(0))
        bot.last_shard_ocr_state = {
            "chosen": {
                "raw": "Passive Shards: 0",
                "normalized": "0",
                "parsed": 0,
                "reason": "strong explicit zero",
            },
            "attempts": [
                {
                    "raw": "Passive Shards: 0",
                    "normalized": "0",
                    "parsed": 0,
                    "reason": "strong explicit zero",
                }
            ],
        }
        self.assertTrue(bot.passive_shards_empty_confirmed(0))
        self.assertTrue(any("not confirmed" in message for message in messages))
        self.assertTrue(any("empty confirmed from strong evidence" in message for message in messages))

    def test_passive_shard_empty_check_skips_healthy_trusted_value(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.last_passive_shards = 192000
        self.assertFalse(bot.should_check_passive_shards_empty(192000))
        self.assertFalse(bot.should_check_passive_shards_empty(192000))
        self.assertEqual(sum("empty check skipped" in message for message in messages), 1)

    def test_passive_shard_empty_confirm_is_quiet_without_active_gate(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        self.assertFalse(bot.passive_shards_empty_confirmed(192000))
        self.assertFalse(any("Passive shard empty condition not confirmed" in message for message in messages))

    def test_passive_shard_empty_check_triggers_for_low_and_suspicious_values(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.last_passive_shards = 192000
        self.assertTrue(bot.should_check_passive_shards_empty(0))
        bot.last_shard_ocr_state = {
            "chosen": {"parsed": 0, "reason": "suspicious zero rejected: weak OCR"},
            "attempts": [],
        }
        self.assertFalse(bot.should_check_passive_shards_empty(None))
        bot.last_passive_shards = None
        bot.session_latest_passive_shards = None
        self.assertTrue(bot.should_check_passive_shards_empty(None))
        self.assertTrue(any("empty check triggered" in message for message in messages))

    def test_passive_shard_suspicious_zero_preserves_previous_valid_value(self):
        bot = PassiveShardStubBot(
            [
                {
                    "mode": "raw",
                    "psm": 7,
                    "raw": "0PassiveShards",
                    "normalized": "0",
                    "parsed": 0,
                    "formatted": "0",
                    "reason": "parsed",
                },
                {
                    "mode": "gray",
                    "psm": 6,
                    "raw": "OPassiveShards",
                    "normalized": "0",
                    "parsed": 0,
                    "formatted": "0",
                    "reason": "parsed",
                },
            ]
        )
        bot.last_passive_shards = 51200
        self.assertIsNone(bot.read_passive_shards())
        self.assertEqual(bot.last_passive_shards, 51200)
        self.assertFalse(bot.passive_shards_empty_confirmed(0))
        self.assertTrue(any("Passive shard OCR suspicious zero rejected" in message for message in bot.messages))
        self.assertTrue(any("keeping previous valid value" in message for message in bot.messages))

    def test_passive_shard_garbage_zero_inputs_do_not_confirm_empty(self):
        for raw in ("OPassiveShards", "0PassiveShards", "PassiveShards"):
            bot = PassiveShardStubBot(
                [
                    {
                        "mode": "raw",
                        "psm": 7,
                        "raw": raw,
                        "normalized": "0" if raw != "PassiveShards" else "",
                        "parsed": 0 if raw != "PassiveShards" else None,
                        "formatted": "0" if raw != "PassiveShards" else "not found",
                        "reason": "parsed" if raw != "PassiveShards" else "no normalized digits",
                    }
                ]
            )
            bot.last_passive_shards = 1200
            self.assertIsNone(bot.read_passive_shards())
            self.assertEqual(bot.last_passive_shards, 1200)
            self.assertFalse(bot.passive_shards_empty_confirmed(0))

    def test_passive_shard_strong_zero_read_can_confirm_empty(self):
        bot = PassiveShardStubBot(
            [
                {
                    "mode": "raw",
                    "psm": 7,
                    "raw": "Passive Shards: 0",
                    "normalized": "0",
                    "parsed": 0,
                    "formatted": "0",
                    "reason": "parsed",
                }
            ]
        )
        self.assertEqual(bot.read_passive_shards(), 0)
        self.assertEqual(bot.last_passive_shards, 0)
        self.assertTrue(bot.passive_shards_empty_confirmed(0))

    def test_passive_shard_session_usage_uses_accepted_reads_only(self):
        bot = self.make_bot()
        bot.session_started_at = time.time() - 3600
        bot._update_passive_shard_session(51200)
        bot._update_passive_shard_session(47000)
        summary = bot.passive_shard_usage_summary()
        self.assertIn("start=51,200", summary)
        self.assertIn("current=47,000", summary)
        self.assertIn("consumed=4,200", summary)

    def test_passive_shard_report_updates_live_status(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["WEBHOOK_URL"] = "https://discord.example/webhook"
        bot.cfg["WEBHOOK_LIVE_STATUS_ENABLED"] = True
        bot.read_passive_shards = lambda: 201000
        bot.maybe_update_live_status = lambda *args, **kwargs: True
        self.assertEqual(bot.maybe_report_passive_shards(force=True), 201000)
        self.assertEqual(bot.last_passive_shards_sent, 201000)
        self.assertTrue(any("Passive shard update applied to live status" in message for message in messages))

    def test_passive_shard_live_status_failure_falls_back_to_standalone(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["WEBHOOK_URL"] = "https://discord.example/webhook"
        bot.cfg["WEBHOOK_LIVE_STATUS_ENABLED"] = True
        bot.read_passive_shards = lambda: 201000
        fallback = []
        bot.maybe_update_live_status = lambda *args, **kwargs: False
        bot._send_passive_shard_standalone_update = lambda count_text, reason="": fallback.append((count_text, reason)) or True
        self.assertEqual(bot.maybe_report_passive_shards(force=True), 201000)
        self.assertEqual(bot.last_passive_shards_sent, 201000)
        self.assertEqual(fallback, [("201,000 (201k)", "live status fallback")])
        self.assertTrue(any("live status update failed" in message for message in messages))

    def test_version_matches_shared_metadata(self):
        self.assertEqual(APP_VERSION, VERSION_METADATA)
        self.assertEqual(APP_PUBLIC_VERSION, PUBLIC_VERSION_METADATA)
        self.assertEqual(APP_PUBLIC_VERSION, "v1.2")
        self.assertEqual(APP_DISPLAY_NAME, f"Kon. {APP_PUBLIC_VERSION}")

    def test_webhook_deletes_uploaded_screenshot(self):
        class Response:
            status_code = 204
            text = ""

        class Requests:
            @staticmethod
            def post(*_args, **_kwargs):
                return Response()

        old_requests = bot_module.requests
        bot_module.requests = Requests
        try:
            bot = self.make_bot()
            bot.cfg["WEBHOOK_URL"] = "https://discord.example/webhook"
            with TemporaryDirectory() as temp_dir:
                path = Path(temp_dir) / "shot.png"
                path.write_bytes(b"fake-png")
                ok = bot.send_webhook(str(path), "fortune", "Drop 30 | Luck 10", "current spec fortune")
                self.assertTrue(ok)
                self.assertFalse(path.exists())
        finally:
            bot_module.requests = old_requests

    def test_live_status_message_is_created_and_updated(self):
        class Response:
            status_code = 200
            text = ""

            def json(self):
                return {"id": "message-123"}

        class Requests:
            posts = []
            patches = []

            @classmethod
            def post(cls, *args, **kwargs):
                cls.posts.append((args, kwargs))
                return Response()

            @classmethod
            def patch(cls, *args, **kwargs):
                cls.patches.append((args, kwargs))
                return Response()

        old_requests = bot_module.requests
        bot_module.requests = Requests
        try:
            bot = self.make_bot()
            bot.cfg["WEBHOOK_URL"] = "https://discord.example/api/webhooks/id/token"
            bot.session_started_at = 1.0
            self.assertTrue(bot.start_live_status())
            self.assertEqual(bot.live_status_message_id, "message-123")
            self.assertTrue(bot.maybe_update_live_status(force=True))
            self.assertTrue(Requests.patches)
            self.assertIn("/messages/message-123", Requests.patches[0][0][0])
        finally:
            bot_module.requests = old_requests

    def test_webhook_alert_dedup_suppresses_before_screenshot_capture(self):
        bot = self.make_bot()
        bot.cfg["WEBHOOK_URL"] = "https://discord.example/webhook"
        bot.cfg["WEBHOOK_DEDUP_WINDOW"] = 90
        captures = []

        def fake_capture(label):
            captures.append(label)
            return "missing.png"

        bot.capture_screen = fake_capture
        bot._send_discord_file = lambda *_args, **_kwargs: True
        self.assertTrue(bot.send_webhook_alert("popup_stuck", "Popup", "body", attach_screenshot=True))
        self.assertFalse(bot.send_webhook_alert("popup_stuck", "Popup", "body", attach_screenshot=True))
        self.assertEqual(captures, ["webhook_alert"])

    def test_near_miss_discord_alert_uses_clean_spec_layout(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_rules(DEFAULT_REAL_RULES)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["CURRENT_SPEC_MARKER_OCR"] = False
        bot._format_uptime = lambda: "9m 21s"
        sent = []
        dedup_keys = []
        bot._webhook_should_send = lambda key, window=None: dedup_keys.append(key) or True
        bot.send_discord_message = lambda content, **kwargs: sent.append((content, kwargs)) or True

        ok = bot.send_near_miss_alert(
            "rampage",
            "Combo Ramp 29.1 | Damage 29.2 | Crit Rate 3.2 | Crit Damage 6.9",
            "Crit Damage: 6.9 -> 9-10",
            "Crit Damage: 2.1 below min",
        )

        self.assertTrue(ok)
        self.assertEqual(bot.session_near_misses, 1)
        self.assertEqual(bot.last_important_event, "Near miss: Rampage")
        self.assertEqual(dedup_keys, ["near_miss:rampage:Crit Damage: 2.1 below min"])
        content, kwargs = sent[0]
        self.assertFalse(kwargs["use_ping"])
        self.assertTrue(content.startswith("# Kon. Near Miss - Spec"))
        self.assertIn("## What happened", content)
        self.assertIn("Rampage was close to the configured target", content)
        self.assertIn("## Roll", content)
        self.assertIn("- Type: Spec", content)
        self.assertIn("- Trait: Rampage", content)
        self.assertIn("- Combo Ramp: 29.1", content)
        self.assertIn("- Damage: 29.2", content)
        self.assertIn("- Crit Rate: 3.2", content)
        self.assertIn("- Crit Damage: 6.9", content)
        self.assertIn("## Target check", content)
        self.assertIn("- Missed stat: Crit Damage", content)
        self.assertIn("- Rolled: 6.9", content)
        self.assertIn("- Needed: 9-10", content)
        self.assertIn("- Gap: -2.1", content)
        self.assertIn("## Session\n- Uptime: 9m 21s\n- Time:", content)
        self.assertIn("## OCR", content)
        self.assertNotIn("Near Miss Found", content)
        self.assertTrue(any("format=v2_clean_markdown" in message for message in messages))

    def test_near_miss_alert_sends_raw_markdown_through_alert_wrapper(self):
        bot = self.make_bot()
        sent = []

        def fake_send_discord_message(content, **kwargs):
            sent.append((content, kwargs))
            return True

        bot._webhook_should_send = lambda *_args, **_kwargs: True
        bot.send_discord_message = fake_send_discord_message

        self.assertTrue(
            bot.send_near_miss_alert(
                "rampage",
                "Combo Ramp 29.1 | Damage 29.2 | Crit Rate 3.2 | Crit Damage 6.9",
                "Crit Damage: 6.9 -> 9-10",
                "Crit Damage: 2.1 below min",
            )
        )

        content, kwargs = sent[0]
        self.assertTrue(content.startswith("# Kon. Near Miss"))
        self.assertFalse(content.startswith(APP_VERSION))
        self.assertNotIn("| Near Miss Found", content)
        self.assertFalse(kwargs["use_ping"])

    def test_near_miss_discord_alert_uses_clean_power_layout(self):
        bot = self.make_bot()
        bot.set_roll_domain("powers")
        bot._format_uptime = lambda: "2m 3s"
        sent = []
        dedup_keys = []
        bot._webhook_should_send = lambda key, window=None: dedup_keys.append(key) or True
        bot.send_discord_message = lambda content, **kwargs: sent.append((content, kwargs)) or True

        ok = bot.send_near_miss_alert(
            "subjugator",
            "Passive NPC Slow 20 5s | Damage 36.8 | Crit Chance 2.8 | Luck 9.4 | HP (optional) 34.4 | Crit Damage 10.2",
            "Luck: 9.4 -> 17-17.5",
            "Luck: 7.6 below min",
        )

        self.assertTrue(ok)
        self.assertEqual(bot.session_near_misses, 1)
        self.assertEqual(bot.last_important_event, "Near miss: Subjugator")
        self.assertEqual(dedup_keys, ["near_miss:subjugator:Luck: 7.6 below min"])
        content, kwargs = sent[0]
        self.assertFalse(kwargs["use_ping"])
        self.assertTrue(content.startswith("# Kon. Near Miss - Power"))
        self.assertIn("Subjugator was close to the configured target", content)
        self.assertIn("- Type: Power", content)
        self.assertIn("- Power: Subjugator", content)
        self.assertIn("- Passive NPC Slow: 20 5s", content)
        self.assertIn("- Damage: 36.8", content)
        self.assertIn("- HP: 34.4", content)
        self.assertIn("- Missed stat: Luck", content)
        self.assertIn("- Rolled: 9.4", content)
        self.assertIn("- Needed: 17-17.5", content)
        self.assertIn("- Gap: -7.6", content)
        self.assertIn("## Session\n- Uptime: 2m 3s\n- Time:", content)
        self.assertIn("## OCR", content)

    def test_god_roll_discord_alert_uses_clear_spec_layout(self):
        bot = self.make_bot()
        bot._format_uptime = lambda: "4m 5s"
        sent = []
        bot._send_discord_file = lambda *args, **kwargs: sent.append((args, kwargs)) or True

        ok = bot.send_webhook(
            "shot.png",
            "rampage",
            "Combo Ramp 30 | Damage 30 | Crit Rate 3.5 | Crit Damage 10",
            "current spec rampage combo ramp 30 damage 30",
        )

        self.assertTrue(ok)
        content = sent[0][0][0]
        self.assertTrue(content.startswith("# Kon. Kept Spec Roll"))
        self.assertIn("## What happened", content)
        self.assertIn("matched the active target rules", content)
        self.assertIn("- Type: Spec", content)
        self.assertIn("- Trait: Rampage", content)
        self.assertIn("- Combo Ramp: 30", content)
        self.assertIn("- Status: Kept", content)
        self.assertIn("## Session\n- Uptime: 4m 5s\n- Time:", content)
        self.assertIn("## OCR", content)

    def test_god_roll_discord_alert_uses_clear_power_layout(self):
        bot = self.make_bot()
        bot.set_roll_domain("powers")
        bot._format_uptime = lambda: "7m 8s"
        sent = []
        bot._send_discord_file = lambda *args, **kwargs: sent.append((args, kwargs)) or True

        ok = bot.send_webhook(
            "shot.png",
            "subjugator",
            "Passive NPC Slow 20 5s | Damage 41 | Crit Chance 3 | Luck 17.2 | Crit Damage 14",
            "subjugator npc slow damage luck",
        )

        self.assertTrue(ok)
        content = sent[0][0][0]
        self.assertTrue(content.startswith("# Kon. Kept Power Roll"))
        self.assertIn("- Type: Power", content)
        self.assertIn("- Power: Subjugator", content)
        self.assertIn("- Passive NPC Slow: 20 5s", content)
        self.assertIn("- Status: Kept", content)
        self.assertIn("all configured Power target thresholds were met", content)
        self.assertIn("## Session\n- Uptime: 7m 8s\n- Time:", content)

    def test_check_roll_marks_rampage_god_roll_with_combo_ramp(self):
        bot = StubBot(
            [
                (
                    "tesseract-test",
                    "current spec rampage combo ramp 16.8 cap damage 29.4 crit chance 3.2 crit damage 9.1",
                )
            ]
        )
        bot.set_rules(DEFAULT_REAL_RULES)
        state, trait, summary, _text, missing, near = bot.check_roll()
        self.assertEqual(state, "GOD")
        self.assertEqual(trait, "rampage")
        self.assertIn("Combo Ramp 16.8", summary)
        self.assertEqual(missing, [])
        self.assertFalse(near)

    def test_check_roll_marks_god_roll_from_ocr_candidate(self):
        bot = StubBot(
            [
                (
                    "tesseract-test",
                    "current spec executioner npc dmg 44.8 crit chance 3.5 crit damage 14.7",
                )
            ]
        )
        bot.set_rules(DEFAULT_REAL_RULES)
        state, trait, summary, _text, missing, near = bot.check_roll()
        self.assertEqual(state, "GOD")
        self.assertEqual(trait, "executioner")
        self.assertIn("NPC DMG 44.8", summary)
        self.assertEqual(missing, [])
        self.assertFalse(near)

    def test_check_roll_classifies_unsupported_trait_as_autoskip_filler(self):
        bot = StubBot(
            [
                (
                    "tesseract-test",
                    "current spec vigor damage 5.0 range 3.0",
                    "CURRENT SPEC Vigor Damage 5.0% Range 3.0%",
                )
            ]
        )
        state, trait, summary, _text, missing, near = bot.check_roll()
        self.assertEqual(state, "NON_TARGET")
        self.assertEqual(trait, "non_target")
        self.assertIn("Unsupported/filler trait", summary)
        self.assertEqual(missing, ["Unsupported trait autoskip"])
        self.assertFalse(near)
        self.assertTrue(any("unsupported_trait_autoskip" in message for message in bot.messages))

    def test_specs_fast_loop_complete_supported_trait_skips_fallback(self):
        bot = FastLoopCandidateBot(
            [
                (
                    "tesseract-full-original-psm6",
                    "current spec executioner npc dmg 44.8 crit chance 3.5 crit damage 14.2",
                    "CURRENT SPEC Executioner NPC DMG 44.8 Crit Chance 3.5 Crit Damage 14.2",
                )
            ]
        )

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "GOD")
        self.assertEqual(trait, "executioner")
        self.assertIn("NPC DMG 44.8", summary)
        self.assertEqual(missing, [])
        self.assertFalse(near)
        self.assertEqual(len(bot.calls), 1)
        self.assertTrue(bot.calls[0].get("fast_loop"))
        self.assertFalse(any(call.get("fallback_only") for call in bot.calls))

    def test_specs_fast_loop_unsupported_trait_skips_fallback(self):
        bot = FastLoopCandidateBot(
            [
                (
                    "tesseract-full-original-psm6",
                    "current spec berserker damage 24.6 crit damage 14.8",
                    "CURRENT SPEC Berserker Damage 24.6 Crit Damage 14.8",
                )
            ]
        )

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "NON_TARGET")
        self.assertEqual(trait, "non_target")
        self.assertIn("berserker", summary)
        self.assertEqual(missing, ["Unsupported trait autoskip"])
        self.assertFalse(near)
        self.assertEqual(len(bot.calls), 1)
        self.assertTrue(bot.calls[0].get("fast_loop"))

    def test_specs_fast_loop_partial_supported_trait_escalates_to_primary(self):
        bot = FastLoopCandidateBot(
            [
                (
                    "tesseract-full-original-psm6",
                    "current spec executioner npc dmg 44.8",
                    "CURRENT SPEC Executioner NPC DMG 44.8",
                )
            ],
            primary_candidates=[
                (
                    "tesseract-full-original-psm6",
                    "current spec executioner npc dmg 44.8 crit chance 3.5 crit damage 14.2",
                    "CURRENT SPEC Executioner NPC DMG 44.8 Crit Chance 3.5 Crit Damage 14.2",
                )
            ],
        )

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "GOD")
        self.assertEqual(trait, "executioner")
        self.assertIn("Crit Damage 14.2", summary)
        self.assertEqual(missing, [])
        self.assertFalse(near)
        self.assertEqual(len(bot.calls), 2)
        self.assertTrue(bot.calls[0].get("fast_loop"))
        self.assertFalse(bot.calls[1].get("fast_loop", False))
        self.assertFalse(bot.calls[1].get("fallback_only", False))

    def test_specs_fast_loop_infers_bad_rampage_from_stat_structure_before_autoskip(self):
        bot = FastLoopCandidateBot(
            [
                (
                    "tesseract-full-original-psm6",
                    "current-spec. ge combo 16.8 cap.damage 2.9 critchance 3.85 critdamage 5.6",
                    "CURRENT-SPEC. ge Combo 16.8 cap.Damage 2.9 CritChance 3.85 CritDamage 5.6",
                )
            ],
            primary_candidates=[
                (
                    "tesseract-full-original-psm6",
                    "current spec phantom guard damage 5.0 range 3.0",
                    "CURRENT SPEC Phantom Guard Damage 5.0 Range 3.0",
                )
            ],
        )

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "rampage")
        self.assertIn("Combo Ramp", summary)
        self.assertIn("Damage", " ; ".join(missing))
        self.assertFalse(near)
        self.assertEqual(len(bot.calls), 1)
        self.assertFalse(any("cached_non_target" in message for message in bot.messages))
        self.assertTrue(any("Possible target mythical stat structure detected" in message for message in bot.messages))

    def test_logged_aterany_rampage_ocr_classifies_bad_instead_of_non_target(self):
        bot = FastLoopCandidateBot(
            [
                (
                    "tesseract-full-original-psm6",
                    "current-spec. ae aterany 17.5 cap.damage 17.4 ert chanice3.8 eit dantige 713",
                    "CURRENT-SPEC. ae Aterany 17.5 cap.Damage 17.4 ert chanice3.8 eit dantige 713",
                )
            ]
        )

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "rampage")
        self.assertIn("Combo Ramp 17.5", summary)
        self.assertIn("Crit Damage 7.13", summary)
        self.assertIn("Damage", " ; ".join(missing))
        self.assertFalse(near)
        self.assertFalse(any("unsupported_trait_autoskip" in message for message in bot.messages))

    def test_logged_noisy_rampage_marker_change_classifies_bad_instead_of_non_target(self):
        bot = FastLoopCandidateBot(
            [
                (
                    "tesseract-full-original-psm6",
                    "currentspec. -rampage comboramp 17.5 cap.damage r1bmcaitchance38.gtdakige736",
                    "CurrentSpec. -Rampage ComboRamp 17.5 cap.Damage r1bmcaitchance38.gtdakige736",
                )
            ]
        )

        state, trait, summary, _text, missing, near = bot.check_roll()

        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "rampage")
        self.assertIn("Combo Ramp 17.5", summary)
        self.assertIn("Damage ?", summary)
        self.assertNotIn("Damage 1", summary)
        self.assertIn("Crit Damage 7.36", summary)
        self.assertIn("Damage", " ; ".join(missing))
        self.assertFalse(near)
        self.assertFalse(any("cached_non_target" in message for message in bot.messages))

    def test_stats_ocr_early_stops_after_one_strong_spec_read(self):
        if bot_module.Image is None:
            self.skipTest("Pillow unavailable")
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["OCR_DEBUG_VERBOSE"] = False
        calls = []
        texts = [
            "CURRENT SPEC Rampage Combo Ramp 24.7 Damage 17.3 Crit Rate 2.9 Crit Damage 7.8",
            "SHOULD NOT READ SECOND PASS",
            "SHOULD NOT READ THIRD PASS",
        ]

        def fake_ocr(_img, psm=6):
            calls.append(psm)
            return texts[len(calls) - 1]

        class FakePyAutoGui:
            @staticmethod
            def screenshot(*_args, **_kwargs):
                return bot_module.Image.new("RGB", (180, 80), (20, 20, 20))

        old_pyautogui = bot_module.pyautogui
        old_pytesseract = bot_module.pytesseract
        try:
            bot_module.pyautogui = FakePyAutoGui
            bot_module.pytesseract = object()
            bot._ocr_tesseract_image = fake_ocr
            candidates = bot.get_stats_ocr_candidates(startup_fast=True)
        finally:
            bot_module.pyautogui = old_pyautogui
            bot_module.pytesseract = old_pytesseract

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(candidates), 1)
        self.assertTrue(any("OCR early stop" in message for message in messages))

    def test_stats_ocr_early_stops_after_second_read_when_first_is_partial(self):
        if bot_module.Image is None:
            self.skipTest("Pillow unavailable")
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["OCR_DEBUG_VERBOSE"] = False
        calls = []
        texts = [
            "CURRENT SPEC Rampage Damage 17.3",
            "CURRENT SPEC Rampage Combo Ramp 24.7 Damage 17.3 Crit Rate 2.9 Crit Damage 7.8",
            "SHOULD NOT READ THIRD PASS",
        ]

        def fake_ocr(_img, psm=6):
            calls.append(psm)
            return texts[len(calls) - 1]

        class FakePyAutoGui:
            @staticmethod
            def screenshot(*_args, **_kwargs):
                return bot_module.Image.new("RGB", (180, 80), (20, 20, 20))

        old_pyautogui = bot_module.pyautogui
        old_pytesseract = bot_module.pytesseract
        try:
            bot_module.pyautogui = FakePyAutoGui
            bot_module.pytesseract = object()
            bot._ocr_tesseract_image = fake_ocr
            candidates = bot.get_stats_ocr_candidates(startup_fast=True)
        finally:
            bot_module.pyautogui = old_pyautogui
            bot_module.pytesseract = old_pytesseract

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(candidates), 2)
        self.assertTrue(any("reads=2" in message for message in messages if "OCR early stop" in message))

    def test_specs_fast_loop_caches_repeated_non_target_without_fallback(self):
        bot = FastLoopCandidateBot(
            [
                (
                    "tesseract-full-original-psm6",
                    "current spec frostborn damage 24.6 crit damage 14.8",
                    "CURRENT SPEC Frostborn Damage 24.6 Crit Damage 14.8",
                )
            ],
            primary_candidates=[
                (
                    "tesseract-full-original-psm6",
                    "current spec executioner npc dmg 44.8 crit chance 3.5 crit damage 14.2",
                    "CURRENT SPEC Executioner NPC DMG 44.8 Crit Chance 3.5 Crit Damage 14.2",
                )
            ],
        )

        first = bot.check_roll()
        second = bot.check_roll()

        self.assertEqual(first[0], "NON_TARGET")
        self.assertEqual(second[0], "NON_TARGET")
        self.assertEqual([call.get("fast_loop", False) for call in bot.calls], [True, True])
        self.assertFalse(any(call.get("fallback_only") for call in bot.calls))
        self.assertTrue(any("cached_non_target" in message for message in bot.messages))

    def test_generic_current_spec_non_target_is_rollable_without_target_thresholds(self):
        bot = StubBot(
            [
                (
                    "tesseract-test",
                    "current spec phantom guard damage 5.0 range 3.0",
                    "CURRENT SPEC Phantom Guard Damage 5.0% Range 3.0%",
                )
            ]
        )
        state, trait, summary, _text, _missing, _near = bot.check_roll()
        self.assertEqual(state, "NON_TARGET")
        self.assertEqual(trait, "non_target")
        self.assertIn("phantom", summary)

    def test_unsupported_trait_names_never_trigger_alert_or_stop_classifications(self):
        unsupported_samples = [
            ("Dead Eye", "CURRENT SPEC Dead Eye Damage 30 Crit Chance 4 Crit Damage 15"),
            ("Vigor", "CURRENT SPEC Vigor Damage 30 Crit Chance 4 Crit Damage 15"),
            ("Monarch", "CURRENT SPEC Monarch Damage 30 Crit Chance 4 Crit Damage 15"),
            ("Blitz", "CURRENT SPEC Blitz Damage 30 Crit Chance 4 Crit Damage 15"),
            ("Frostborn", "CURRENT SPEC Frostborn Damage 30 Crit Chance 4 Crit Damage 15"),
        ]
        for label, raw in unsupported_samples:
            with self.subTest(label=label):
                bot = StubBot([("tesseract-test", raw.lower(), raw)])
                bot.send_webhook = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unsupported trait sent god alert"))
                bot.send_near_miss_alert = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unsupported trait sent near-miss alert"))
                bot.on_god_roll = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unsupported trait recorded god roll"))
                bot.on_near_miss = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unsupported trait recorded near miss"))

                state, trait, summary, _text, missing, near = bot.check_roll()

                self.assertEqual(state, "NON_TARGET")
                self.assertEqual(trait, "non_target")
                self.assertIn("Unsupported/filler trait", summary)
                self.assertEqual(missing, ["Unsupported trait autoskip"])
                self.assertFalse(near)

    def test_non_target_without_current_spec_marker_is_rejected_as_unreliable(self):
        bot = StubBot(
            [
                (
                    "tesseract-test",
                    "vigor damage 5.0",
                    "Vigor Damage 5.0%",
                )
            ]
        )
        state, trait, summary, _text, _missing, _near = bot.check_roll()
        self.assertEqual(state, "ROLLING")
        self.assertIsNone(trait)
        self.assertEqual(summary, "")

    def test_non_allowlisted_trait_cannot_be_promoted_by_rules(self):
        bot = self.make_bot()
        self.assertFalse(bot.is_target_trait("deadeye"))
        old_labels = bot_module.STAT_LABELS.get("deadeye")
        old_caps = bot_module.STAT_CAPS.get("deadeye")
        try:
            bot_module.STAT_LABELS["deadeye"] = ["Damage"]
            bot_module.STAT_CAPS["deadeye"] = [10.0]
            bot.rules["deadeye"] = [(5.0, 10.0)]
            bot.enabled_specs.add("deadeye")
            self.assertFalse(bot.is_target_trait("deadeye"))
        finally:
            if old_labels is None:
                bot_module.STAT_LABELS.pop("deadeye", None)
            else:
                bot_module.STAT_LABELS["deadeye"] = old_labels
            if old_caps is None:
                bot_module.STAT_CAPS.pop("deadeye", None)
            else:
                bot_module.STAT_CAPS["deadeye"] = old_caps
            bot.rules.pop("deadeye", None)

    def test_chosen_enabled_spec_normalizes_to_fortune_only(self):
        bot = self.make_bot()
        bot.set_enabled_specs({"chosen", "deadeye", "executioner"})

        self.assertEqual(bot.enabled_specs, {"fortune", "executioner"})
        self.assertTrue(bot.is_target_trait("chosen"))
        self.assertEqual(bot_module.detect_trait("Current Spec Chosen Drop 29.5 Luck 9.5"), "fortune")

    def test_markerless_strong_partial_rampage_read_is_accepted(self):
        bot = StubBot(
            [
                (
                    "tesseract-full-gray-psm6",
                    "rampage combo ramp 26.5 damage 28.4 crit rate 3.2",
                    "Rampage > Combo Ramp: 26.5%, Damage 28.4%, Crit Rate 3.2%",
                )
            ]
        )
        state, trait, summary, _text, missing, _near = bot.check_roll()
        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "rampage")
        self.assertIn("Combo Ramp 26.5", summary)
        self.assertTrue(any("Crit Damage" in item for item in missing))
        self.assertTrue(any("Marker missing but structured read accepted" in message for message in bot.messages))
        self.assertTrue(any("Partial structured read accepted | missing=Crit Damage" in message for message in bot.messages))

    def test_partial_target_mythical_confirm_window_stabilizes_rampage(self):
        bot = SequentialCandidateBot(
            [
                [
                    (
                        "transient-fragment",
                        "rampage damagei damage20.5 critdamage",
                        "Rampage DamageI>Damage20.5%, CritDamage",
                    )
                ],
                [
                    (
                        "confirm-structured",
                        "current spec rampage combo ramp 18.5 damage 20.5 crit rate 3.606 crit damage 7.5",
                        "CURRENT SPEC Rampage Combo Ramp 18.5 Damage 20.5 Crit Rate 3.606 Crit Damage 7.5",
                    )
                ],
            ]
        )

        state, trait, summary, _text, missing, _near = bot.check_roll()

        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "rampage")
        self.assertIn("Crit Damage 7.5", summary)
        self.assertFalse(any("Crit Damage: not found" in item for item in missing))
        self.assertGreaterEqual(bot.candidate_calls, 2)
        self.assertTrue(any("Specs OCR fast-loop promoted to primary route" in message for message in bot.messages))

    def test_startup_fast_check_uses_partial_target_confirm_window(self):
        bot = SequentialCandidateBot(
            [
                [
                    (
                        "startup-fragment",
                        "rampage damagei damage20.5 critdamage",
                        "Rampage DamageI>Damage20.5%, CritDamage",
                    )
                ],
                [
                    (
                        "startup-confirm",
                        "current spec rampage combo ramp 18.5 damage 20.5 crit rate 3.606 crit damage 7.5",
                        "CURRENT SPEC Rampage Combo Ramp 18.5 Damage 20.5 Crit Rate 3.606 Crit Damage 7.5",
                    )
                ],
            ]
        )
        manual_calls = []
        bot.manual_reroll_flow = lambda reason="": manual_calls.append(reason) or True
        bot.stats_changed = lambda *_args, **_kwargs: (
            True,
            "current spec rampage combo ramp 19 damage 21 crit rate 3.7 crit damage 7.8",
        )

        self.assertEqual(bot.startup_check_current_roll(), "rerolled")
        self.assertEqual(manual_calls, ["startup current bad rampage"])
        self.assertGreaterEqual(bot.candidate_calls, 2)
        self.assertTrue(any("Partial target mythical stabilized" in message for message in bot.messages))

    def test_partial_target_mythical_confirm_window_keeps_junk_rejected(self):
        bot = SequentialCandidateBot(
            [
                [
                    (
                        "transient-fragment",
                        "rampage damagei damage5.0",
                        "Rampage DamageI>Damage5.0%",
                    )
                ],
                [
                    (
                        "still-fragment",
                        "rampage damagei damage5.0",
                        "Rampage DamageI>Damage5.0%",
                    )
                ],
            ]
        )

        state, trait, summary, _text, _missing, _near = bot.check_roll()

        self.assertEqual(state, "ROLLING")
        self.assertIsNone(trait)
        self.assertEqual(summary, "")
        self.assertTrue(any("Partial target mythical did not stabilize" in message for message in bot.messages))
        self.assertTrue(any("Rejected fragmentary Rampage read" in message for message in bot.messages))

    def test_partial_target_confirm_logs_trait_drift_without_accepting_new_trait(self):
        bot = SequentialCandidateBot(
            [
                [
                    (
                        "transient-rampage-fragment",
                        "rampage damagei damage5.0",
                        "Rampage DamageI>Damage5.0%",
                    )
                ],
                [
                    (
                        "drifted-executioner",
                        "current spec executioner npc dmg 44.8 crit chance 3.9 crit damage 14.9",
                        "CURRENT SPEC Executioner NPC DMG 44.8 Crit Chance 3.9 Crit Damage 14.9",
                    )
                ],
            ]
        )

        state, trait, summary, _text, _missing, _near = bot.check_roll()

        self.assertEqual(state, "ROLLING")
        self.assertIsNone(trait)
        self.assertEqual(summary, "")
        self.assertTrue(any("partial target changed during confirm" in message for message in bot.messages))
        self.assertFalse(any("Partial target mythical did not stabilize" in message for message in bot.messages))
        self.assertTrue(any("Rejected fragmentary Rampage read" in message for message in bot.messages))

    def test_markerless_rampage_with_mangled_crit_damage_is_classified(self):
        bot = StubBot(
            [
                (
                    "tesseract-full-gray-psm6",
                    "rampage combo ramp 26.5 damage 28.4 crit chance 3.2 critdanuge 7.2",
                    "Rampage>ComboRamp:26.5%Cap,Damage 28.40%CritChance3.2%,CritDanuge7.2%",
                )
            ]
        )
        state, trait, summary, _text, _missing, _near = bot.check_roll()
        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "rampage")
        self.assertIn("Crit Damage 7.2", summary)
        self.assertTrue(any("Marker missing but structured read accepted" in message for message in bot.messages))

    def test_markerless_weak_structured_read_is_rejected(self):
        bot = StubBot(
            [
                (
                    "tesseract-full-gray-psm6",
                    "rampage combo ramp 26.5",
                    "Rampage > Combo Ramp: 26.5%",
                )
            ]
        )
        state, trait, summary, _text, _missing, _near = bot.check_roll()
        self.assertEqual(state, "ROLLING")
        self.assertIsNone(trait)
        self.assertEqual(summary, "")
        self.assertTrue(any("Rejected fragmentary Rampage read" in message for message in bot.messages))

    def test_current_spec_marker_accepts_common_ocr_variants(self):
        bot = self.make_bot()
        self.assertTrue(bot.has_current_spec_marker("CURRENT-SPEC Rampage"))
        self.assertTrue(bot.has_current_spec_marker("curent spee rampage"))

    def test_near_miss_is_recorded_when_one_stat_is_close(self):
        bot = self.make_bot()
        state, trait, summary, _text, missing, near = bot.evaluate_trait_with_values(
            "executioner",
            [44.8, 2.8, 14.7],
            "current spec executioner npc dmg 44.8 crit chance 2.8 crit damage 14.7",
        )
        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "executioner")
        self.assertIn("Crit Chance", " ".join(missing))
        self.assertIn("Crit Chance 2.8", summary)
        self.assertTrue(near)

    def test_legacy_settings_are_backed_up_and_migrated_safely(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir) as settings_path:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                json.dumps(
                    {
                        "webhook_url": "https://discord.example/hook",
                        "player_ping": "@player",
                        "use_easyocr": True,
                        "stats_region": "1,2,3,4",
                        "coords": {"auto": "11,22"},
                    }
                ),
                encoding="utf-8",
            )

            controller = BotController()
            saved = json.loads(settings_path.read_text(encoding="utf-8"))
            backups = list((Path(temp_dir) / "config" / "backups").glob("aelrith_forge_settings.legacy_backup_*.json"))

            self.assertEqual(controller.settings["settings_version"], CURRENT_SETTINGS_VERSION)
            self.assertEqual(saved["settings_version"], CURRENT_SETTINGS_VERSION)
            self.assertNotIn("webhook_url", saved)
            self.assertNotIn("player_ping", saved)
            local_webhook = json.loads(controller._webhook_settings_file().read_text(encoding="utf-8"))
            self.assertEqual(local_webhook["webhook_url"], "https://discord.example/hook")
            self.assertEqual(local_webhook["player_ping"], "@player")
            self.assertEqual(saved["coords"]["auto"], "11,22")
            self.assertEqual(saved["stats_region"], default_settings()["stats_region"])
            self.assertNotIn("use_easyocr", saved)
            self.assertTrue(backups)
            backup_payload = json.loads(backups[0].read_text(encoding="utf-8"))
            self.assertNotIn("webhook_url", backup_payload)
            self.assertNotIn("player_ping", backup_payload)

    def test_malformed_settings_are_backed_up_and_reset_to_defaults(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir) as settings_path:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text("{broken json", encoding="utf-8")

            controller = BotController()
            saved = json.loads(settings_path.read_text(encoding="utf-8"))
            backups = list((Path(temp_dir) / "config" / "backups").glob("aelrith_forge_settings.invalid_backup_*.json"))

            self.assertEqual(json.loads(json.dumps(controller._strip_webhook_settings(controller.settings))), saved)
            self.assertEqual(saved, controller._strip_webhook_settings(self.saved_default_settings()))
            self.assertTrue(backups)

    def test_controller_loads_full_power_shard_settings_from_saved_config(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir) as settings_path:
            saved = self.saved_default_settings()
            saved.update(
                {
                    "roll_domain": "powers",
                    "power_shard_region": "10,20,30,40",
                    "power_shard_alerts": True,
                    "power_shard_report_interval": 420,
                    "power_shard_low_threshold": 12000,
                    "power_shard_very_low_threshold": 7000,
                    "power_shard_critical_threshold": 1500,
                    "power_shard_empty_threshold": 5,
                    "power_shard_alert_cooldown": 2700,
                    "stop_on_empty_power_shards": True,
                    "powers_layout": {
                        "stats_region": "100,100,300,80",
                        "current_power_region": "100,100,300,80",
                        "preview_region": "100,100,300,80",
                        "auto_check_region": "110,110,30,30",
                        "confirm_check_region": "120,120,40,20",
                        "popup_region": "200,200,140,70",
                        "protected_region": "10,10,20,20",
                        "change_detection_exclusion_region": "10,10,20,20",
                        "coords": {"auto": "101,201", "roll": "102,202", "yes": "103,203"},
                    },
                }
            )
            settings_path.write_text(json.dumps(saved, indent=2), encoding="utf-8")

            controller = BotController()

            self.assertEqual(controller.settings["power_shard_region"], "10,20,30,40")
            self.assertEqual(controller.settings["power_shard_report_interval"], 420)
            self.assertEqual(controller.settings["power_shard_low_threshold"], 12000)
            self.assertEqual(controller.settings["power_shard_very_low_threshold"], 7000)
            self.assertEqual(controller.settings["power_shard_critical_threshold"], 1500)
            self.assertEqual(controller.settings["power_shard_empty_threshold"], 5)
            self.assertEqual(controller.settings["power_shard_alert_cooldown"], 2700)
            self.assertTrue(controller.settings["stop_on_empty_power_shards"])
            self.assertEqual(controller.bot.cfg["POWER_SHARD_REGION"], (10, 20, 30, 40))
            self.assertEqual(controller.bot.cfg["POWER_SHARD_REPORT_INTERVAL"], 420)
            self.assertEqual(controller.bot.cfg["POWER_SHARD_LOW_THRESHOLD"], 12000)
            self.assertEqual(controller.bot.cfg["POWER_SHARD_VERY_LOW_THRESHOLD"], 7000)
            self.assertEqual(controller.bot.cfg["POWER_SHARD_CRITICAL_THRESHOLD"], 1500)
            self.assertEqual(controller.bot.cfg["POWER_SHARD_EMPTY_THRESHOLD"], 5)
            self.assertEqual(controller.bot.cfg["POWER_SHARD_ALERT_COOLDOWN"], 2700)
            self.assertTrue(controller.bot.cfg["STOP_ON_EMPTY_POWER_SHARDS"])

    def test_manual_settings_reset_creates_backup_and_clean_defaults(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir) as settings_path:
            settings_path.write_text(
                json.dumps({"settings_version": CURRENT_SETTINGS_VERSION, "webhook_url": "old"}),
                encoding="utf-8",
            )
            controller = BotController()

            backup = controller.reset_settings()
            saved = json.loads(settings_path.read_text(encoding="utf-8"))

            self.assertIsNotNone(backup)
            self.assertTrue(Path(backup).exists())
            self.assertEqual(saved, json.loads(json.dumps(controller._strip_webhook_settings(controller.settings))))

    def test_local_webhook_settings_load_apply_and_test_webhook(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir) as settings_path:
            settings_path.write_text(
                json.dumps(controller_module.BotController.__new__(BotController).normalize_settings(default_settings()), indent=2),
                encoding="utf-8",
            )
            local_path = settings_path.parent / controller_module.WEBHOOK_SETTINGS_FILE_NAME
            local_path.write_text(
                json.dumps(
                    {
                        "webhook_url": "https://discord.example/local",
                        "player_ping": "@local",
                        "webhook_live_status_enabled": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            controller = BotController()
            self.assertEqual(controller.settings["webhook_url"], "https://discord.example/local")
            self.assertEqual(controller.settings["player_ping"], "@local")
            self.assertFalse(controller.settings["webhook_live_status_enabled"])
            self.assertEqual(controller.bot.cfg["WEBHOOK_URL"], "https://discord.example/local")

            calls = []
            controller.bot.test_webhook = lambda: calls.append(controller.bot.cfg["WEBHOOK_URL"]) or True
            updated = dict(controller.settings)
            updated["webhook_url"] = "https://discord.example/updated"
            updated["player_ping"] = "@updated"

            self.assertTrue(controller.test_webhook(updated))
            self.assertEqual(calls, ["https://discord.example/updated"])
            normal_saved = json.loads(settings_path.read_text(encoding="utf-8"))
            local_saved = json.loads(local_path.read_text(encoding="utf-8"))
            self.assertNotIn("webhook_url", normal_saved)
            self.assertNotIn("player_ping", normal_saved)
            self.assertEqual(local_saved["webhook_url"], "https://discord.example/updated")
            self.assertEqual(local_saved["player_ping"], "@updated")

    def test_safe_power_settings_backup_excludes_secrets_and_preserves_power_layout(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir):
            controller = BotController()
            settings = controller.normalize_settings(default_settings())
            settings.update(
                {
                    "roll_domain": "powers",
                    "webhook_url": "https://discord.example/api/webhooks/id/token",
                    "player_ping": "@player",
                    "power_shard_region": "10,20,30,40",
                    "powers_layout": {
                        "stats_region": "100,100,300,80",
                        "current_power_region": "100,100,300,80",
                        "preview_region": "200,200,260,70",
                        "auto_check_region": "300,300,40,40",
                        "confirm_check_region": "400,400,120,40",
                        "popup_region": "500,500,180,90",
                        "protected_region": "600,600,190,95",
                        "change_detection_exclusion_region": "600,600,190,95",
                        "coords": {"auto": "101,202", "roll": "303,404", "yes": "505,606"},
                    },
                }
            )
            controller.apply_settings(settings, save=False, announce=False)
            backup_path = Path(temp_dir) / "powers_backup.json"

            saved_path = controller.save_power_settings_backup(backup_path)
            backup = json.loads(saved_path.read_text(encoding="utf-8"))

            self.assertEqual(set(backup), {"roll_domain", "powers_layout", "enabled_powers", "powers_rules", "power_shard_region"})
            self.assertEqual(backup["roll_domain"], "powers")
            self.assertEqual(backup["power_shard_region"], "10,20,30,40")
            self.assertEqual(backup["powers_layout"]["current_power_region"], "100,100,300,80")
            self.assertEqual(backup["powers_layout"]["preview_region"], "200,200,260,70")
            self.assertEqual(backup["powers_layout"]["coords"]["yes"], "505,606")
            serialized = json.dumps(backup)
            self.assertNotIn("webhook", serialized.lower())
            self.assertNotIn("discord.example", serialized)
            self.assertNotIn("@player", serialized)

    def test_ocr_debug_file_records_parse_details(self):
        old_debug_log = bot_module.OCR_DEBUG_LOG_FILE
        old_log_dir = bot_module.LOG_DIR
        with TemporaryDirectory() as temp_dir:
            bot_module.OCR_DEBUG_LOG_FILE = Path(temp_dir) / "ocr_debug.jsonl"
            try:
                bot = self.make_bot()
                bot.cfg["OCR_DEBUG_FILE"] = True
                parsed = bot._parse_stat_ocr_candidates(
                    [
                        (
                            "tesseract-test",
                            "current spec rampage combo ramp 22.6 damage 19.1 crit chance 3.0 crit damage 6.8",
                        )
                    ],
                    bad_panel_words=[],
                )
                lines = bot_module.OCR_DEBUG_LOG_FILE.read_text(encoding="utf-8").splitlines()
            finally:
                bot_module.OCR_DEBUG_LOG_FILE = old_debug_log
                bot_module.LOG_DIR = old_log_dir

        self.assertEqual(parsed["merged_values"], [22.6, 19.1, 3.0, 6.8])
        self.assertTrue(any('"event": "ocr_parse"' in line for line in lines))
        self.assertTrue(any('"trait": "rampage"' in line for line in lines))

    def test_ocr_debug_artifact_names_include_app_version(self):
        old_pyautogui = bot_module.pyautogui
        old_debug_dir = bot_module.OCR_DEBUG_DIR
        old_debug_log = bot_module.OCR_DEBUG_LOG_FILE
        old_log_dir = bot_module.LOG_DIR
        with TemporaryDirectory() as temp_dir:
            bot_module.pyautogui = FakePyAutoGui
            bot_module.OCR_DEBUG_DIR = Path(temp_dir)
            bot_module.OCR_DEBUG_LOG_FILE = Path(temp_dir) / "ocr_debug.jsonl"
            try:
                bot = self.make_bot()
                path = Path(bot.save_ocr_debug_crop("rampage", "parse error"))
                meta_path = path.with_suffix(".json")
                self.assertTrue(path.exists())
                self.assertTrue(meta_path.exists())
            finally:
                bot_module.pyautogui = old_pyautogui
                bot_module.OCR_DEBUG_DIR = old_debug_dir
                bot_module.OCR_DEBUG_LOG_FILE = old_debug_log
                bot_module.LOG_DIR = old_log_dir

        self.assertTrue(path.name.startswith(f"{bot_module.ARTIFACT_VERSION_PREFIX}_"))
        self.assertTrue(path.name.endswith("_rampage_parse_error.png"))
        self.assertTrue(meta_path.name.startswith(f"{bot_module.ARTIFACT_VERSION_PREFIX}_"))
        self.assertTrue(meta_path.name.endswith("_rampage_parse_error.json"))

    def test_debug_artifact_cleanup_removes_generated_ocr_files_and_rotates_runtime_log(self):
        old_app_data = bot_module.APP_DATA_DIR
        old_capture_dir = bot_module.CAPTURE_DIR
        old_debug_dir = bot_module.OCR_DEBUG_DIR
        old_debug_log = bot_module.OCR_DEBUG_LOG_FILE
        old_log_dir = bot_module.LOG_DIR
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir) as _settings_path:
            root = Path(temp_dir)
            bot_module.APP_DATA_DIR = root
            bot_module.CAPTURE_DIR = root / "output" / "captures"
            bot_module.OCR_DEBUG_DIR = root / "output" / "ocr"
            bot_module.OCR_DEBUG_LOG_FILE = bot_module.OCR_DEBUG_DIR / "aelrith_forge_vtest_ocr_debug.jsonl"
            bot_module.LOG_DIR = root / "output" / "logs"
            bot_module.CAPTURE_DIR.mkdir(parents=True)
            bot_module.OCR_DEBUG_DIR.mkdir(parents=True)
            (bot_module.OCR_DEBUG_DIR / "old.png").write_bytes(b"png")
            (bot_module.OCR_DEBUG_DIR / "old.json").write_text("{}", encoding="utf-8")
            bot_module.OCR_DEBUG_LOG_FILE.write_text("debug", encoding="utf-8")
            (root / "output" / "logs" / "aelrith_forge_ocr_debug.jsonl").parent.mkdir(parents=True, exist_ok=True)
            (root / "output" / "logs" / "aelrith_forge_ocr_debug.jsonl").write_text("old", encoding="utf-8")
            (bot_module.CAPTURE_DIR / "vtest_20260416_000000_webhook_test.png").write_bytes(b"png")
            (root / "output" / "logs" / "preview_temp.png").write_bytes(b"png")
            controller_module.LOG_FILE.write_text("[]", encoding="utf-8")
            try:
                controller = BotController()
                controller.clean_debug_artifacts()
                backups = list((root / "output" / "logs").glob("aelrith_forge_logs.*.bak.json"))
                crop_removed = not (root / "output" / "ocr" / "old.png").exists()
                meta_removed = not (root / "output" / "ocr" / "old.json").exists()
                log_removed = not (root / "output" / "ocr" / "aelrith_forge_vtest_ocr_debug.jsonl").exists()
                old_log_removed = not (root / "output" / "logs" / "aelrith_forge_ocr_debug.jsonl").exists()
                screenshot_removed = not (bot_module.CAPTURE_DIR / "vtest_20260416_000000_webhook_test.png").exists()
                preview_removed = not (root / "output" / "logs" / "preview_temp.png").exists()
            finally:
                bot_module.APP_DATA_DIR = old_app_data
                bot_module.CAPTURE_DIR = old_capture_dir
                bot_module.OCR_DEBUG_DIR = old_debug_dir
                bot_module.OCR_DEBUG_LOG_FILE = old_debug_log
                bot_module.LOG_DIR = old_log_dir

        self.assertTrue(crop_removed)
        self.assertTrue(meta_removed)
        self.assertTrue(log_removed)
        self.assertTrue(old_log_removed)
        self.assertTrue(screenshot_removed)
        self.assertTrue(preview_removed)
        self.assertTrue(backups)

    def test_controller_startup_cleans_only_rotated_runtime_log_backups(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir) as _settings_path:
            root = Path(temp_dir)
            active_log = root / "output" / "logs" / "aelrith_forge_logs.json"
            old_one = root / "output" / "logs" / "aelrith_forge_logs.20260417_010000.bak.json"
            old_two = root / "output" / "logs" / "aelrith_forge_logs.previous.bak.json"
            unrelated = root / "output" / "logs" / "aelrith_forge_logs.manual.json"
            elsewhere = root / "archive"
            elsewhere.mkdir()
            archived = elsewhere / "aelrith_forge_logs.20260417_020000.bak.json"
            active_log.parent.mkdir(parents=True, exist_ok=True)
            active_log.write_text("[]", encoding="utf-8")
            old_one.write_text("old", encoding="utf-8")
            old_two.write_text("old", encoding="utf-8")
            unrelated.write_text("keep", encoding="utf-8")
            archived.write_text("keep", encoding="utf-8")

            controller = BotController()

            self.assertTrue(active_log.exists())
            self.assertFalse(old_one.exists())
            self.assertFalse(old_two.exists())
            self.assertTrue(unrelated.exists())
            self.assertTrue(archived.exists())
            self.assertTrue(any("Cleaned 2 old runtime backup logs" in entry["message"] for entry in controller.logs))

    def test_capture_artifact_names_include_app_version(self):
        old_pyautogui = bot_module.pyautogui
        old_capture_dir = bot_module.CAPTURE_DIR
        with TemporaryDirectory() as temp_dir:
            bot_module.pyautogui = FakePyAutoGui
            bot_module.CAPTURE_DIR = Path(temp_dir)
            try:
                bot = self.make_bot()
                path = Path(bot.capture_screen("webhook test"))
                self.assertTrue(path.exists())
            finally:
                bot_module.pyautogui = old_pyautogui
                bot_module.CAPTURE_DIR = old_capture_dir

        self.assertTrue(path.name.startswith(f"{bot_module.ARTIFACT_VERSION_PREFIX}_"))
        self.assertTrue(path.name.endswith("_webhook_test.png"))

    def test_diagnostic_snapshot_writes_summary_bundle(self):
        old_diag_dir = bot_module.DIAGNOSTIC_DIR
        old_pyautogui = bot_module.pyautogui
        old_pytesseract = bot_module.pytesseract
        with TemporaryDirectory() as temp_dir:
            bot_module.DIAGNOSTIC_DIR = Path(temp_dir)
            bot_module.pyautogui = FakePyAutoGui
            bot_module.pytesseract = object()
            try:
                bot = self.make_bot()
                bot.cfg["PASSIVE_SHARD_REGION"] = (10, 20, 30, 40)
                bot.cfg["POWER_SHARD_REGION"] = (50, 60, 70, 80)
                bot.last_trait_seen = "rampage"
                bot.last_important_event = "unit test event"
                bot.last_power_shard_ocr_state = {
                    "chosen": {"formatted": "201,000 (201k)", "reason": "previous power test"},
                    "attempts": [],
                }
                bot.passive_shard_ocr_attempts = lambda region=None, **_kwargs: {
                    "region": tuple(region or bot.cfg["PASSIVE_SHARD_REGION"]),
                    "ocr_region": (8, 18, 34, 44),
                    "attempts": [
                        {
                            "mode": "threshold",
                            "psm": 7,
                            "raw": "Passive Shards: 512K",
                            "normalized": "512k",
                            "parsed": 512000,
                            "formatted": "512,000 (512k)",
                            "reason": "parsed",
                        }
                    ],
                }
                bot.power_shard_ocr_attempts = lambda region=None, **_kwargs: {
                    "region": tuple(region or bot.cfg["POWER_SHARD_REGION"]),
                    "ocr_region": (48, 58, 74, 84),
                    "attempts": [
                        {
                            "mode": "threshold",
                            "psm": 7,
                            "raw": "Power Shards: 201K",
                            "normalized": "201k",
                            "parsed": 201000,
                            "formatted": "201,000 (201k)",
                            "reason": "parsed",
                        }
                    ],
                }
                bot.record_decision_chain(
                    subsystem="Classification",
                    classification="BAD",
                    classification_reason="unit test",
                    current_trait="Rampage",
                    parsed_values={"Damage": 12.3},
                )
                bot.recent_timing_events = [
                    {"time": "2026-04-24 13:01:00", "name": "manual_reroll_popup_confirm", "elapsed_ms": 123}
                ]
                bot.recent_route_budget_events = [
                    {"time": "2026-04-24 13:01:01", "name": "startup_verify_budget", "elapsed_ms": 45, "polls": 1}
                ]
                bot.last_verification_cache_stats = {
                    "context": "Initial Auto Start unit",
                    "cache_hits": 1,
                    "cache_misses": 1,
                    "polls_seen": 1,
                    "polls_planned": 2,
                }
                bot.last_startup_route_snapshot = {"route_reason": "unit_startup_route"}
                bot.last_recovery_route_snapshot = {"route_reason": "unit_recovery_route"}
                bot.auto_checkbox_read_count = 4
                bot.auto_checkbox_ambiguous_read_count = 3
                bot.last_auto_checkbox_classifier_summary = {"context": "unit", "state": "unknown"}
                path = Path(bot.capture_diagnostic_snapshot("unit failure", extra={"recent_logs": ["one"]}))
                summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
                ocr = json.loads((path / "ocr_candidates.json").read_text(encoding="utf-8"))
                shards = json.loads((path / "shards.json").read_text(encoding="utf-8"))
                power_shards = json.loads((path / "power_shards.json").read_text(encoding="utf-8"))
                passive_region_saved = (path / "passive_shard_region.png").exists()
                power_region_saved = (path / "power_shard_region.png").exists()
            finally:
                bot_module.DIAGNOSTIC_DIR = old_diag_dir
                bot_module.pyautogui = old_pyautogui
                bot_module.pytesseract = old_pytesseract

        self.assertTrue(path.name.startswith(f"{bot_module.ARTIFACT_VERSION_PREFIX}_"))
        self.assertIn("unit_failure", path.name)
        self.assertEqual(summary["event_type"], "unit failure")
        self.assertEqual(summary["last_decision_chain"]["classification"], "BAD")
        self.assertIn("power_shard_state", summary["last_decision_chain"])
        self.assertIn("recent_logs", summary["extra"])
        self.assertIn("power_shards", summary)
        self.assertEqual(summary["auto_checkbox_session"]["reads"], 4)
        self.assertEqual(summary["auto_checkbox_session"]["ambiguous_reads"], 3)
        self.assertEqual(summary["auto_checkbox_session"]["latest_classifier"]["context"], "unit")
        self.assertEqual(summary["timings"][0]["name"], "manual_reroll_popup_confirm")
        self.assertEqual(summary["verification_cache"]["cache_hits"], 1)
        self.assertEqual(summary["route_budget_timings"][0]["name"], "startup_verify_budget")
        self.assertEqual(summary["route_snapshots"]["startup"]["route_reason"], "unit_startup_route")
        self.assertEqual(summary["route_snapshots"]["recovery"]["route_reason"], "unit_recovery_route")
        self.assertEqual(summary["power_shards"]["attempts"][0]["raw"], "Power Shards: 201K")
        self.assertEqual(power_shards["attempts"][0]["parsed"], 201000)
        self.assertEqual(shards["attempts"][0]["parsed"], 512000)
        self.assertTrue(passive_region_saved)
        self.assertTrue(power_region_saved)
        self.assertEqual(summary["config"]["settings"]["POWER_SHARD_REGION"], [50, 60, 70, 80])
        self.assertTrue(summary["config"]["settings"]["POWER_SHARD_ALERTS"])
        self.assertEqual(summary["config"]["settings"]["POWER_SHARD_REPORT_INTERVAL"], 600)
        self.assertEqual(summary["config"]["settings"]["POWER_SHARD_EMPTY_THRESHOLD"], 0)
        self.assertEqual(summary["config"]["settings"]["POWER_SHARD_ALERT_COOLDOWN"], 1800)
        self.assertTrue(summary["config"]["settings"]["STOP_ON_EMPTY_POWER_SHARDS"])
        self.assertIsInstance(ocr, dict)
        self.assertIsInstance(shards, dict)
        self.assertIsInstance(power_shards, dict)

    def test_diagnostic_snapshot_retention_prunes_old_bundles(self):
        old_diag_dir = bot_module.DIAGNOSTIC_DIR
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bot_module.DIAGNOSTIC_DIR = root
            try:
                bot = self.make_bot()
                bot.cfg["DEBUG_SNAPSHOT_RETENTION_COUNT"] = 2
                for index in range(4):
                    folder = root / f"old_{index}"
                    folder.mkdir()
                    (folder / "summary.json").write_text("{}", encoding="utf-8")
                    old_time = time.time() - (100 - index)
                    folder.touch()
                    import os

                    os.utime(folder, (old_time, old_time))
                bot._prune_diagnostic_snapshots()
                remaining = sorted(path.name for path in root.iterdir() if path.is_dir())
            finally:
                bot_module.DIAGNOSTIC_DIR = old_diag_dir

        self.assertEqual(len(remaining), 2)
        self.assertEqual(remaining, ["old_2", "old_3"])

    def test_startup_manual_fallback_blocks_without_bad_roll_or_popup(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.set_roll_domain("powers")
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.cfg["AUTO_VERIFY_POLLS"] = 1
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.auto_checkbox_state = lambda: "enabled"
        bot._auto_checkbox_enabled_is_weak = lambda: False
        bot._auto_checkbox_confidence_tier = lambda: "strong_enabled"
        bot._startup_context = {"current_spec_class": "unknown", "preflight_fallback_reason": "none"}
        manual_calls = []
        bot.manual_reroll_flow = lambda *args, **_kwargs: manual_calls.append(args) or True
        bot.stats_changed = lambda baseline, context="", **_kwargs: (_ for _ in ()).throw(
            AssertionError(f"unexpected duplicate verify: {context}")
        ) if "manual fallback verify" in context else (False, baseline)

        self.assertFalse(bot.start_or_recover("Initial Auto Start"))
        self.assertEqual(bot.last_startup_result, "failed_no_roll_detected")
        self.assertEqual(manual_calls, [])
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))

    def test_extracts_power_shard_count(self):
        bot = self.make_bot()
        self.assertEqual(bot.extract_power_shards("Power Shards: 1,240"), 1240)
        self.assertEqual(bot.extract_power_shards("201K Power Shards"), 201000)
        self.assertEqual(bot.extract_power_shards("51.2k"), 51200)
        self.assertIsNone(bot.extract_power_shards("garbage"))

    def test_parse_power_shard_count_variants(self):
        value, normalized = parse_power_shard_count("Power Shards: 47,1k", infer_missing_suffix=True)
        self.assertEqual(normalized, "47.1k")
        self.assertEqual(value, 47100)
        value, normalized = parse_power_shard_count("201K Power Shards")
        self.assertEqual(normalized, "201k")
        self.assertEqual(value, 201000)
        value, normalized = parse_power_shard_count("1.37MPowerShards", previous_value=20100, infer_missing_suffix=True)
        self.assertEqual(normalized, "1.37m")
        self.assertEqual(value, 1370000)
        value, normalized = parse_power_shard_count("1,000,0001", previous_value=1370000, infer_missing_suffix=True)
        self.assertEqual(normalized, "10000001")
        self.assertIsNone(value)

    def test_power_shard_read_accepts_compact_millions_with_previous_low_value(self):
        attempts = []
        for mode in ("raw", "gray", "contrast", "threshold"):
            for psm in (7, 6):
                parsed, normalized, candidate_type = bot_module._parse_power_shard_count_detail(
                    "1.37MPowerShards",
                    previous_value=20100,
                    infer_missing_suffix=True,
                )
                attempts.append(
                    {
                        "mode": mode,
                        "psm": psm,
                        "raw": "1.37MPowerShards",
                        "normalized": normalized,
                        "parsed": parsed,
                        "formatted": bot_module.format_shard_count(parsed) if parsed is not None else "not found",
                        "reason": "parsed" if parsed is not None else "no valid shard count",
                        "candidate_type": candidate_type,
                    }
                )
        bot = PowerShardStubBot(attempts)
        bot.last_power_shards = 20100

        self.assertEqual(bot.read_power_shards(), 1370000)
        self.assertEqual(bot.last_power_shards, 1370000)
        self.assertTrue(any("Power shard OCR accepted" in message and "1.37M" in message for message in bot.messages))

    def test_power_shard_read_rejects_malformed_plain_million_count(self):
        attempts = []
        for mode in ("raw", "gray", "contrast", "threshold"):
            for psm in (7, 6):
                parsed, normalized, candidate_type = bot_module._parse_power_shard_count_detail(
                    "1,000,0001",
                    previous_value=1370000,
                    infer_missing_suffix=True,
                )
                attempts.append(
                    {
                        "mode": mode,
                        "psm": psm,
                        "raw": "1,000,0001",
                        "normalized": normalized,
                        "parsed": parsed,
                        "formatted": bot_module.format_shard_count(parsed) if parsed is not None else "not found",
                        "reason": "rejected malformed plain shard count"
                        if candidate_type == "malformed_plain_count"
                        else "no valid shard count",
                        "candidate_type": candidate_type,
                    }
                )
        bot = PowerShardStubBot(attempts)
        bot.last_power_shards = 1370000

        self.assertIsNone(bot.read_power_shards())
        self.assertEqual(bot.last_power_shards, 1370000)
        self.assertTrue(any("rejected malformed plain shard count" in message for message in bot.messages))

    def test_power_shard_reporting_and_empty_confirmation(self):
        bot = PowerShardStubBot(
            [
                {"mode": "threshold", "psm": 7, "raw": "Power Shards: 0", "normalized": "0", "parsed": 0, "formatted": "0", "reason": "strong explicit zero", "candidate_type": "plain"},
                {"mode": "contrast", "psm": 6, "raw": "0 Power Shards", "normalized": "0", "parsed": 0, "formatted": "0", "reason": "strong explicit zero", "candidate_type": "plain"},
            ]
        )
        bot.cfg["POWER_SHARD_ALERTS"] = True
        bot.cfg["STOP_ON_EMPTY_POWER_SHARDS"] = True
        bot.cfg["POWER_SHARD_REPORT_INTERVAL"] = 60

        count = bot.maybe_report_power_shards(force=True)

        self.assertEqual(count, 0)
        self.assertEqual(bot.last_power_shards_sent, 0)
        self.assertTrue(bot.should_check_power_shards_empty(count))
        self.assertTrue(bot.power_shards_empty_confirmed(count))

    def test_controller_emits_power_shard_signal(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir):
            controller = BotController()
            values = []
            controller.power_shards_changed.connect(values.append)

            controller.add_log("Power shards: 201,000 (201k)")

            self.assertEqual(values[-1], "201,000 (201k)")

    def test_live_proof_pack_exports_markdown_and_json(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir):
            controller = BotController()
            settings = controller.normalize_settings(default_settings())
            settings["roll_domain"] = "powers"
            settings["power_shard_region"] = "10,20,30,40"
            settings["powers_layout"]["stats_region"] = "100,100,300,80"
            settings["powers_layout"]["popup_region"] = "200,200,140,70"
            settings["powers_layout"]["protected_region"] = "300,300,180,80"
            settings["powers_layout"]["preview_region"] = "400,400,260,70"
            settings["powers_layout"]["current_power_region"] = "400,400,260,70"
            settings["powers_layout"]["coords"] = {"auto": "101,202", "roll": "303,404", "yes": "505,606"}
            controller.apply_settings(settings, save=False, announce=False)
            controller.bot.session_started_at = time.time() - 125
            controller.bot.session_recovery_count = 2
            controller.bot.recovery_failures = 1
            controller.bot.session_god_rolls = 1
            controller.bot.session_near_misses = 3
            controller.bot.last_important_event = "unit proof event \u00e2\u20ac\u00a6 clipped"
            controller.bot.auto_checkbox_read_count = 5
            controller.bot.auto_checkbox_ambiguous_read_count = 2
            controller.bot.manual_reroll_direct_recovery_clicks = 1
            controller.bot.last_auto_checkbox_classifier_summary = {
                "context": "Manual Reroll Auto Resume",
                "state": "unknown",
                "confidence": "ambiguous",
            }
            controller.bot.session_latest_passive_shards = 512000
            controller.bot.session_latest_power_shards = 201000
            controller.bot.last_decision_chain = {"classification": "BAD", "current_trait": "Cursebrand"}
            controller.bot.recent_timing_events = [
                {"time": "2026-04-24 13:02:00", "name": "ocr_preview_capture", "elapsed_ms": 210, "result": "completed"}
            ]
            controller.bot.recent_route_budget_events = [
                {"time": "2026-04-24 13:02:01", "name": "startup_verify_budget", "elapsed_ms": 45, "result": "confirmed", "reason": "unit"}
            ]
            controller.bot.last_verification_cache_stats = {"cache_hits": 1, "cache_misses": 1, "polls_seen": 1, "polls_planned": 2}
            controller.bot.last_startup_route_snapshot = {"route_reason": "unit_startup_route"}
            controller.bot.last_recovery_route_snapshot = {"route_reason": "unit_recovery_route"}
            controller.logs = [
                normalize_log_entry({"time": "2026-04-24 13:01:00", "level": "warn", "message": "Unexpected No-Roll Watchdog | unit \u00e2\u20ac\u00a6"}),
                normalize_log_entry({"time": "2026-04-24 13:02:00", "level": "info", "message": "Settings applied."}),
            ]
            controller.god_rolls.append(GodRollEntry("2026-04-24 13:00:00", "Cursebrand", "Damage 30"))
            controller.near_misses.append(NearMissEntry("2026-04-24 13:00:30", "Cursebrand", "Damage 29"))

            folder = Path(controller.export_live_proof_pack("manual"))
            proof_json_saved = (folder / "proof.json").exists()
            proof_markdown_saved = (folder / "proof.md").exists()
            payload = json.loads((folder / "proof.json").read_text(encoding="utf-8"))
            markdown = (folder / "proof.md").read_text(encoding="utf-8")

        self.assertTrue(folder.name.startswith(f"{bot_module.ARTIFACT_VERSION_PREFIX}_"))
        self.assertTrue(proof_json_saved)
        self.assertTrue(proof_markdown_saved)
        self.assertEqual(payload["version"], VERSION_METADATA)
        self.assertEqual(payload["trigger"], "manual")
        self.assertEqual(payload["active_domain"], "powers")
        self.assertEqual(payload["session"]["recoveries"], 2)
        self.assertEqual(payload["session"]["recovery_failures"], 1)
        self.assertEqual(payload["session"]["god_rolls"], 1)
        self.assertEqual(payload["session"]["near_misses"], 3)
        self.assertEqual(payload["decision_chain"]["classification"], "BAD")
        self.assertEqual(payload["shards"]["passive"]["current"], 512000)
        self.assertEqual(payload["shards"]["power"]["current"], 201000)
        self.assertEqual(payload["timings"][0]["name"], "ocr_preview_capture")
        self.assertEqual(payload["auto_checkbox"]["reads"], 5)
        self.assertEqual(payload["auto_checkbox"]["ambiguous_reads"], 2)
        self.assertEqual(payload["auto_checkbox"]["manual_reroll_direct_recovery_clicks"], 1)
        self.assertEqual(payload["auto_checkbox"]["latest_classifier"]["state"], "unknown")
        self.assertEqual(payload["verification_cache"]["cache_hits"], 1)
        self.assertEqual(payload["route_budget_timings"][0]["name"], "startup_verify_budget")
        self.assertEqual(payload["route_snapshots"]["startup"]["route_reason"], "unit_startup_route")
        self.assertEqual(len(payload["recent_operator_events"]), 1)
        self.assertEqual(payload["recent_history"]["god_rolls"][0]["spec"], "Cursebrand")
        self.assertIn("Live Proof Pack", markdown)
        self.assertIn("Recent Timings", markdown)
        self.assertIn("Auto Checkbox", markdown)
        self.assertIn("Recovery Visibility", markdown)
        self.assertIn("unit_startup_route", markdown)
        self.assertIn("unit proof event \u2026 clipped", markdown)
        self.assertIn("Unexpected No-Roll Watchdog | unit \u2026", markdown)
        self.assertNotIn("\u00e2\u20ac\u00a6", markdown)

    def test_high_value_terminal_stop_reason_survives_manual_stop_and_proof_export(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir):
            controller = BotController()
            controller.bot.session_started_at = time.time() - 3
            controller.bot.last_decision_chain = {
                "classification": "HIGH_VALUE",
                "current_trait": "Executioner",
            }
            controller.bot._set_terminal_stop_reason("High value roll: Executioner")
            controller.bot.stop_event.set()
            controller.bot.finish_live_status(controller.bot._resolved_stop_reason())

            folder = Path(controller.export_live_proof_pack("session_stop"))
            payload = json.loads((folder / "proof.json").read_text(encoding="utf-8"))
            markdown = (folder / "proof.md").read_text(encoding="utf-8")

        self.assertEqual(payload["session"]["last_event"], "High value roll: Executioner")
        self.assertIn("High value roll: Executioner", markdown)

    def test_manual_stop_reason_is_used_without_terminal_reason(self):
        messages = []
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot.stop_event.set()

        bot.finish_live_status(bot._resolved_stop_reason())

        self.assertEqual(bot.last_important_event, "Manual stop requested")
        self.assertTrue(any("Session stop summary | Manual stop requested" in message for message in messages))

    def test_stop_exports_live_proof_once_for_active_session(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir):
            controller = BotController()
            exported = []
            controller.export_live_proof_pack = lambda trigger="manual": exported.append(trigger) or "proof-path"
            controller.bot.running = True
            controller.bot.stop = lambda: setattr(controller.bot, "running", False)

            controller.stop()
            controller.stop()

        self.assertEqual(exported, ["session_stop"])

    def test_stop_logs_live_proof_export_failure_without_blocking(self):
        with TemporaryDirectory() as temp_dir, controller_storage(temp_dir):
            controller = BotController()
            controller.bot.running = True
            controller.bot.stop = lambda: setattr(controller.bot, "running", False)

            def fail_export(_trigger="manual"):
                raise RuntimeError("unit proof failure")

            controller.export_live_proof_pack = fail_export
            controller.stop()

            self.assertFalse(controller.bot.running)
            self.assertTrue(any("Live proof pack export failed after stop" in entry["message"] for entry in controller.logs))


if __name__ == "__main__":
    unittest.main()
