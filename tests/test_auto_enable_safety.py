import unittest

from aelrith_forge.backend.bot import AelrithForgeBot


class AutoEnableSafetyTests(unittest.TestCase):
    def make_bot(self, messages):
        bot = AelrithForgeBot(messages.append, lambda *_: None)
        bot.cfg["OCR_DEBUG_FILE"] = False
        bot._interruptible_sleep = lambda *_args, **_kwargs: True
        return bot

    def test_unknown_nonstartup_validation_confirms_disabled_before_click(self):
        messages = []
        bot = self.make_bot(messages)
        states = iter(["unknown", "unknown", "unknown", "disabled"])
        bot.auto_checkbox_state = lambda: next(states, "disabled")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        result = bot.ensure_auto_enabled("Unit Recovery", allow_uncertain_enable=True)

        self.assertEqual(result, "clicked")
        self.assertEqual(len(clicks), 1)
        self.assertEqual(clicks[0][0][1], "Unit Recovery")
        self.assertTrue(any("validation confirmed Auto is off, enabling now" in message for message in messages))

    def test_unknown_nonstartup_validation_does_not_speculatively_toggle(self):
        messages = []
        bot = self.make_bot(messages)
        states = iter(["unknown", "unknown", "unknown", "unknown"])
        bot.auto_checkbox_state = lambda: next(states, "unknown")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        result = bot.ensure_auto_enabled("Unit Recovery", allow_uncertain_enable=True)

        self.assertEqual(result, "uncertain")
        self.assertEqual(clicks, [])
        self.assertTrue(any("skipping speculative checkbox click" in message for message in messages))

    def test_manual_reroll_weak_enabled_lean_uses_compact_resume_state(self):
        messages = []
        bot = self.make_bot(messages)
        calls = {"reads": 0}

        def fake_auto_state():
            calls["reads"] += 1
            bot.last_auto_checkbox_state = {
                "state": "unknown",
                "reason": "weak or wide-only enabled checkbox samples",
                "samples": [
                    {"label": "base", "state": "enabled", "reason": "base alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.03, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.06, "blue_ratio": 0.0}}},
                    {"label": "wide", "state": "enabled", "reason": "wide alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.02, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.07, "blue_ratio": 0.0}}},
                    {"label": "tight", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {"inner": {}, "alt_inner": {}}},
                ],
            }
            return "unknown"

        bot.auto_checkbox_state = fake_auto_state

        result = bot.ensure_auto_enabled("Manual Reroll Auto Resume", allow_uncertain_enable=False)

        self.assertEqual(result, "weak_enabled")
        self.assertEqual(calls["reads"], 1)
        self.assertTrue(any("leans enabled" in message for message in messages))

    def test_manual_reroll_compact_verify_accepts_refresh_after_popup_clear(self):
        messages = []
        bot = self.make_bot(messages)
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None

        def fake_stats_changed(_baseline, context="Rolling activity", **_kwargs):
            self.assertIn("Compact Verify", context)
            bot.last_recovery_verify_details = {
                "reason": "current_spec_marker_changed",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "current_spec_marker_changed"
            bot.last_recovery_verify_unreadable = False
            return True, "current spec critdamagei critdamage1.3"

        bot.stats_changed = fake_stats_changed

        result = bot._compact_manual_reroll_resume_verify(
            "current spec rampage combo ramp 25.6 damage 15.0 crit chance 3.8 crit damage 6.9",
            {"compact_verify_polls": 2, "compact_verify_poll_delay": 0.03, "compact_verify_abandon_on_weak_samples": 1},
            popup_recently_cleared=True,
        )

        self.assertTrue(result)
        self.assertTrue(any("compact resume verify confirmed rolling activity" in message for message in messages))

    def test_manual_reroll_recovery_uses_short_popup_cleared_guard_profile(self):
        messages = []
        bot = self.make_bot(messages)
        states = iter(["unknown", "disabled"])
        bot.auto_checkbox_state = lambda: next(states, "disabled")
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        stats_calls = []

        def fake_stats_changed(_baseline, context="Rolling activity", **kwargs):
            stats_calls.append((context, kwargs))
            if "ambiguous checkbox guard" in context:
                bot.last_recovery_verify_details = {
                    "reason": "none",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "none"
                return False, _baseline
            if " verify" in context:
                bot.last_recovery_verify_details = {
                    "reason": "popup_confirmed_mid_polling",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "popup_confirmed_mid_polling"
                return True, "current spec luckii luck4.3"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        result = bot._attempt_auto_reenable_once(
            "Manual Reroll Auto Resume Recovery",
            "current spec rampage combo ramp 25.6 damage 15.0 crit chance 3.8 crit damage 6.9",
            trait="rampage",
            state="BAD",
            verify_signal="manual_reroll_auto_reenable",
            force_click_on_ambiguous=True,
            popup_recently_cleared=True,
        )

        self.assertTrue(result)
        guard_context, guard_kwargs = stats_calls[0]
        self.assertIn("ambiguous checkbox guard", guard_context)
        self.assertEqual(guard_kwargs["polls_override"], 1)
        self.assertEqual(guard_kwargs["poll_delay_override"], 0.03)
        self.assertEqual(guard_kwargs["psm_sequence_override"], (6,))
        self.assertTrue(guard_kwargs["initial_popup_known_false"])
        self.assertFalse(guard_kwargs["post_popup_check_enabled"])
        self.assertTrue(guard_kwargs["fast_popup_checks"])
        verify_context, verify_kwargs = stats_calls[1]
        self.assertIn(" verify", verify_context)
        self.assertTrue(verify_kwargs["initial_popup_known_false"])
        self.assertFalse(verify_kwargs["post_popup_check_enabled"])
        self.assertTrue(verify_kwargs["fast_popup_checks"])
        self.assertEqual(len(clicks), 1)

    def test_manual_reroll_recovery_unknown_state_runs_guard_before_controlled_click(self):
        messages = []
        bot = self.make_bot(messages)
        states = iter(["unknown", "unknown"])
        bot.auto_checkbox_state = lambda: next(states, "unknown")
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        stats_calls = []

        def fake_stats_changed(_baseline, context="Rolling activity", **kwargs):
            stats_calls.append((context, kwargs))
            bot.last_recovery_verify_details = {
                "reason": "none",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "none"
            return False, _baseline

        bot.stats_changed = fake_stats_changed

        result = bot._attempt_auto_reenable_once(
            "Manual Reroll Auto Resume Recovery",
            "current power colossus damage 22.2 crit chance 1.8 luck 14.6 hp 27.8 crit damage 7.6",
            trait="colossus",
            state="BAD",
            verify_signal="manual_reroll_auto_reenable",
            force_click_on_ambiguous=True,
        )

        self.assertFalse(result)
        self.assertEqual(len(stats_calls), 2)
        self.assertIn("ambiguous checkbox guard", stats_calls[0][0])
        self.assertIn(" verify", stats_calls[1][0])
        self.assertEqual(len(clicks), 1)
        self.assertEqual(clicks[0][0][1], "Manual Reroll Auto Resume Recovery Auto Re-enable")

    def test_manual_reroll_recovery_direct_unknown_click_skips_guard_detour(self):
        messages = []
        bot = self.make_bot(messages)
        bot.auto_checkbox_state = lambda: "unknown"
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        stats_calls = []

        def fake_stats_changed(_baseline, context="Rolling activity", **kwargs):
            stats_calls.append((context, kwargs))
            bot.last_recovery_verify_details = {
                "reason": "stat_numbers_changed",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "stat_numbers_changed"
            return True, "current power colossus damage 24.2 crit chance 2.1 luck 14.6 hp 28.8"

        bot.stats_changed = fake_stats_changed

        result = bot._attempt_auto_reenable_once(
            "Manual Reroll Auto Resume Recovery",
            "current power colossus damage 22.2 crit chance 1.8 luck 14.6 hp 27.8 crit damage 7.6",
            trait="colossus",
            state="BAD",
            verify_signal="manual_reroll_auto_reenable",
            force_click_on_ambiguous=True,
            direct_click_on_forced_unknown=True,
        )

        self.assertTrue(result)
        self.assertEqual(len(stats_calls), 1)
        self.assertIn(" verify", stats_calls[0][0])
        self.assertEqual(len(clicks), 1)
        self.assertEqual(clicks[0][0][1], "Manual Reroll Auto Resume Recovery Auto Re-enable")
        self.assertTrue(any("optimized manual reroll unknown checkbox path" in message for message in messages))

    def test_manual_reroll_recovery_rejects_weak_trait_change_and_clicks_once(self):
        messages = []
        bot = self.make_bot(messages)
        states = iter(["unknown", "unknown"])
        bot.auto_checkbox_state = lambda: next(states, "unknown")
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            if "ambiguous checkbox guard" in context:
                bot.last_recovery_verify_details = {
                    "reason": "trait_changed:rampage",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "trait_changed:rampage"
                return True, "damageii damage"
            bot.last_recovery_verify_details = {
                "reason": "popup_confirmed_mid_polling",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "popup_confirmed_mid_polling"
            return True, "damageii damage"

        bot.stats_changed = fake_stats_changed
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None

        result = bot._attempt_auto_reenable_once(
            "Manual Reroll Auto Resume Recovery",
            "executioner below 50 hp 41.1 dmg 2.0 crit damage 11.3",
            trait="executioner",
            state="BAD",
            verify_signal="manual_reroll_auto_reenable",
            force_click_on_ambiguous=True,
        )

        self.assertTrue(result)
        self.assertEqual(len(clicks), 1)
        self.assertTrue(any("weak rolling evidence rejected for ambiguous checkbox guard" in message for message in messages))
        self.assertTrue(any("auto re-enable attempt sent" in message for message in messages))

    def test_manual_reroll_recovery_skips_click_when_guard_has_real_activity_support(self):
        messages = []
        bot = self.make_bot(messages)
        bot.auto_checkbox_state = lambda: "unknown"
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            bot.last_recovery_verify_details = {
                "reason": "popup_confirmed_mid_polling",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "popup_confirmed_mid_polling"
            return True, "damageii damage"

        bot.stats_changed = fake_stats_changed
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None

        result = bot._attempt_auto_reenable_once(
            "Manual Reroll Auto Resume Recovery",
            "executioner below 50 hp 41.1 dmg 2.0 crit damage 11.3",
            trait="executioner",
            state="BAD",
            verify_signal="manual_reroll_auto_reenable",
            force_click_on_ambiguous=True,
        )

        self.assertTrue(result)
        self.assertEqual(clicks, [])
        self.assertTrue(any("skipped auto re-enable on ambiguous checkbox state because rolling evidence returned" in message for message in messages))



    def test_watchdog_weak_enabled_uses_compact_verify_before_click(self):
        messages = []
        bot = self.make_bot(messages)
        calls = {"reads": 0}

        def fake_auto_state():
            calls["reads"] += 1
            bot.last_auto_checkbox_state = {
                "state": "unknown",
                "reason": "weak or wide-only enabled checkbox samples",
                "samples": [
                    {"label": "base", "state": "enabled", "reason": "base alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.03, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.06, "blue_ratio": 0.0}}},
                    {"label": "wide", "state": "enabled", "reason": "wide alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.02, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.07, "blue_ratio": 0.0}}},
                    {"label": "tight", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {"inner": {}, "alt_inner": {}}},
                ],
            }
            return "unknown"

        bot.auto_checkbox_state = fake_auto_state
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        contexts = []

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            contexts.append((context, kwargs))
            if "weak-enabled compact verify" in context:
                bot.last_recovery_verify_details = {
                    "reason": "stats_ocr_unreliable_after_ui_flow:watchdog_ambiguous_guard",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "stats_ocr_unreliable_after_ui_flow:watchdog_ambiguous_guard"
                return True, baseline
            if "ambiguous checkbox confirm" in context:
                raise AssertionError("weak-enabled watchdog path should not use ambiguous checkbox confirm")
            if "Unexpected No-Roll Watchdog verify" in context:
                bot.last_recovery_verify_details = {
                    "reason": "popup_confirmed_mid_polling",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "popup_confirmed_mid_polling"
                return True, "current spec rampage combo ramp 20 damage 20"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        result = bot.unexpected_not_rolling_watchdog(
            "current-spec critdamagei critdamage2.5",
            "NON_TARGET",
            "critdamagei",
            idle_for=4.0,
            popup_known_clear=True,
            banner_known_clear=True,
            stage="suspicion",
            allow_early=True,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(len(clicks), 1)
        self.assertTrue(any("weak-enabled compact verify" in context for context, _ in contexts))
        self.assertFalse(any("ambiguous checkbox confirm" in context for context, _ in contexts))
        self.assertTrue(any("reason=weak_enabled_compact_verify_failed" in message for message in messages))

    def test_watchdog_dead_weak_enabled_fast_path_skips_compact_verify_and_recheck(self):
        messages = []
        bot = self.make_bot(messages)
        calls = {"reads": 0}

        def fake_auto_state():
            calls["reads"] += 1
            bot.last_auto_checkbox_state = {
                "state": "unknown",
                "reason": "weak or wide-only enabled checkbox samples",
                "samples": [
                    {"label": "base", "state": "enabled", "reason": "base alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.03, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.06, "blue_ratio": 0.0}}},
                    {"label": "wide", "state": "enabled", "reason": "wide alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.02, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.07, "blue_ratio": 0.0}}},
                    {"label": "tight", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {"inner": {}, "alt_inner": {}}},
                ],
            }
            return "unknown"

        bot.auto_checkbox_state = fake_auto_state
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        bot.last_recovery_verify_details = {
            "reason": "weak_non_improving_dead_phase",
            "signal_sources": ["ocr", "popup", "banner", "image_change"],
            "image_changed_samples": 0,
            "max_change_score": 0.0,
            "weak_samples": 1,
            "classification": "not_rolling",
            "exit_reason": "weak_non_improving_dead_phase",
        }
        bot.last_recovery_reason = "weak_non_improving_dead_phase"

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            if "weak-enabled compact verify" in context:
                raise AssertionError("dead weak-enabled fast path should skip compact verify")
            if "final recheck" in context:
                raise AssertionError("dead weak-enabled fast path should skip final recheck")
            if "Unexpected No-Roll Watchdog verify" in context:
                bot.last_recovery_verify_details = {
                    "reason": "popup_confirmed_mid_polling",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "popup_confirmed_mid_polling"
                return True, "current spec rampage combo ramp 20 damage 20"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        result = bot.unexpected_not_rolling_watchdog(
            "current-spec damagei damage 6.99",
            "NON_TARGET",
            "damagei",
            idle_for=3.0,
            popup_known_clear=True,
            banner_known_clear=True,
            stage="suspicion",
            allow_early=True,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(calls["reads"], 1)
        self.assertEqual(len(clicks), 1)
        self.assertTrue(any("fast dead-screen weak-enabled path accepted" in message for message in messages))
        self.assertTrue(any("reason=weak_enabled_dead_fast_path" in message for message in messages))

    def test_watchdog_ambiguous_recheck_to_weak_enabled_recovers_stale_non_target(self):
        messages = []
        bot = self.make_bot(messages)
        calls = {"reads": 0}

        def fake_auto_state():
            calls["reads"] += 1
            if calls["reads"] == 1:
                bot.last_auto_checkbox_state = {
                    "state": "unknown",
                    "reason": "all checkbox samples ambiguous",
                    "samples": [
                        {"label": "base", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {"inner": {}, "alt_inner": {}}},
                        {"label": "wide", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {"inner": {}, "alt_inner": {}}},
                        {"label": "tight", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {"inner": {}, "alt_inner": {}}},
                    ],
                }
                return "unknown"
            bot.last_auto_checkbox_state = {
                "state": "unknown",
                "reason": "weak or wide-only enabled checkbox samples",
                "samples": [
                    {"label": "base", "state": "enabled", "reason": "base alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.03, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.06, "blue_ratio": 0.0}}},
                    {"label": "wide", "state": "enabled", "reason": "wide alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.02, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.07, "blue_ratio": 0.0}}},
                    {"label": "tight", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {"inner": {}, "alt_inner": {}}},
                ],
            }
            return "unknown"

        bot.auto_checkbox_state = fake_auto_state
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        contexts = []

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            contexts.append(context)
            if "ambiguous checkbox confirm" in context:
                bot.last_recovery_verify_details = {
                    "reason": "weak_non_improving_dead_phase",
                    "exit_reason": "weak_non_improving_dead_phase",
                    "signal_sources": [],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                    "weak_samples": 1,
                }
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_reason = "weak_non_improving_dead_phase"
                return False, baseline
            if "Unexpected No-Roll Watchdog verify" in context:
                bot.last_recovery_verify_details = {
                    "reason": "popup_confirmed_mid_polling",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "popup_confirmed_mid_polling"
                return True, "current spec rampage combo ramp 20 damage 20"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        result = bot.unexpected_not_rolling_watchdog(
            "current-spec critdamagei critdamage2.5",
            "NON_TARGET",
            "critdamagei",
            idle_for=8.0,
            popup_known_clear=True,
            banner_known_clear=True,
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(calls["reads"], 2)
        self.assertEqual(len(clicks), 1)
        self.assertEqual(clicks[0][0][1], "Unexpected No-Roll Watchdog Auto Re-enable")
        self.assertTrue(any("ambiguous checkbox confirm" in context for context in contexts))
        self.assertTrue(any("watchdog_non_target_stale_auto_reclick_allowed" in message for message in messages))
        self.assertEqual(
            bot.last_recovery_route_snapshot["support_signals"],
            ["non_target_stale_proof", "bounded_auto_reenable"],
        )

    def test_watchdog_off_panel_ambiguous_state_skips_recovery_click(self):
        messages = []
        bot = self.make_bot(messages)
        states = iter(["unknown", "unknown"])

        def fake_auto_state():
            state = next(states, "unknown")
            bot.last_auto_checkbox_state = {
                "state": state,
                "reason": "all checkbox samples ambiguous",
                "samples": [
                    {"label": "base", "state": "unknown", "reason": "broad blue background rejected", "metrics": {"inner": {}, "alt_inner": {}}},
                    {"label": "wide", "state": "unknown", "reason": "broad blue background rejected", "metrics": {"inner": {}, "alt_inner": {}}},
                    {"label": "tight", "state": "unknown", "reason": "broad blue background rejected", "metrics": {"inner": {}, "alt_inner": {}}},
                ],
            }
            return state

        bot.auto_checkbox_state = fake_auto_state
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        contexts = []

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            contexts.append(context)
            if "ambiguous checkbox confirm" in context:
                bot.last_recovery_verify_state = "not_rolling"
                bot.last_recovery_verify_details = {"reason": "no_material_change", "signal_sources": []}
                bot.last_recovery_reason = "no_material_change"
                return False, baseline
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        result = bot.unexpected_not_rolling_watchdog(
            "iy oa",
            "ROLLING",
            None,
            idle_for=8.0,
            popup_known_clear=True,
            banner_known_clear=True,
        )

        self.assertEqual(result, "skipped")
        self.assertEqual(clicks, [])
        self.assertEqual(contexts, ["Unexpected No-Roll Watchdog ambiguous checkbox confirm"])
        self.assertEqual(bot.last_recovery_route_snapshot["route_reason"], "ambiguous_checkbox_no_activity")
        self.assertTrue(any("suppressed ambiguous checkbox click" in message for message in messages))

    def test_watchdog_weak_enabled_compact_verify_can_restore_without_click(self):
        messages = []
        bot = self.make_bot(messages)

        def fake_auto_state():
            bot.last_auto_checkbox_state = {
                "state": "unknown",
                "reason": "weak or wide-only enabled checkbox samples",
                "samples": [
                    {"label": "base", "state": "enabled", "reason": "base alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.03, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.06, "blue_ratio": 0.0}}},
                    {"label": "wide", "state": "enabled", "reason": "wide alt-inner accent signal", "metrics": {"inner": {"green_ratio": 0.02, "blue_ratio": 0.0}, "alt_inner": {"green_ratio": 0.07, "blue_ratio": 0.0}}},
                    {"label": "tight", "state": "unknown", "reason": "ambiguous checkbox crop", "metrics": {"inner": {}, "alt_inner": {}}},
                ],
            }
            return "unknown"

        bot.auto_checkbox_state = fake_auto_state
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            if "weak-enabled compact verify" not in context:
                raise AssertionError(f"unexpected stats_changed context: {context}")
            bot.last_recovery_verify_details = {
                "reason": "popup_confirmed_mid_polling",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "popup_confirmed_mid_polling"
            return True, "current spec rampage combo ramp 20 damage 20"

        bot.stats_changed = fake_stats_changed

        result = bot.unexpected_not_rolling_watchdog(
            "current-spec critdamagei critdamage2.5",
            "NON_TARGET",
            "critdamagei",
            idle_for=4.0,
            popup_known_clear=True,
            banner_known_clear=True,
            stage="suspicion",
            allow_early=True,
        )

        self.assertEqual(result, "restored")
        self.assertEqual(clicks, [])
        self.assertTrue(any("weak-enabled compact verify confirmed rolling activity" in message for message in messages))

    def test_watchdog_rejects_weak_trait_change_without_blind_click(self):
        messages = []
        bot = self.make_bot(messages)
        states = iter(["unknown", "unknown"])
        bot.auto_checkbox_state = lambda: next(states, "unknown")
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            if "ambiguous checkbox confirm" in context:
                bot.last_recovery_verify_details = {
                    "reason": "multi_source_trait_changed:rampage",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "multi_source_trait_changed:rampage"
                return True, "current spec rampage combo ramp 20 damage 20"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        result = bot.unexpected_not_rolling_watchdog(
            "current-spec critdamagei critdamage2.5",
            "NON_TARGET",
            "critdamagei",
            idle_for=4.0,
            popup_known_clear=True,
            banner_known_clear=True,
            stage="suspicion",
            allow_early=True,
        )

        self.assertEqual(result, "skipped")
        self.assertEqual(clicks, [])
        self.assertTrue(any("weak rolling evidence rejected for ambiguous checkbox guard" in message for message in messages))
        self.assertTrue(any("suppressed ambiguous checkbox click" in message for message in messages))

    def test_watchdog_skips_click_when_guard_has_real_activity_support(self):
        messages = []
        bot = self.make_bot(messages)
        bot.auto_checkbox_state = lambda: "unknown"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            if "ambiguous checkbox confirm" not in context:
                raise AssertionError(f"unexpected stats_changed context: {context}")
            bot.last_recovery_verify_details = {
                "reason": "popup_confirmed_mid_polling",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "popup_confirmed_mid_polling"
            return True, "current spec rampage combo ramp 20 damage 20"

        bot.stats_changed = fake_stats_changed

        result = bot.unexpected_not_rolling_watchdog(
            "current-spec critdamagei critdamage2.5",
            "NON_TARGET",
            "critdamagei",
            idle_for=4.0,
            popup_known_clear=True,
            banner_known_clear=True,
            stage="suspicion",
            allow_early=True,
        )

        self.assertEqual(result, "restored")
        self.assertEqual(clicks, [])
        self.assertTrue(any("skipped ambiguous checkbox recovery because rolling evidence returned during guard" in message for message in messages))

    def test_startup_rejects_trait_only_confirmation_and_blocks_guarded_click(self):
        messages = []
        bot = self.make_bot(messages)
        bot.cfg["AUTO_VERIFY_DELAY"] = 0.0
        bot.ocr_region = lambda *_args, **_kwargs: "baseline"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.auto_checkbox_state = lambda: "unknown"
        bot._record_recovery_duration = lambda *_args, **_kwargs: None
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))

        def fake_stats_changed(_baseline, context="Rolling activity", **_kwargs):
            if "preflight rolling check" in context:
                bot.last_recovery_verify_details = {
                    "reason": "current_spec_marker_changed",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "current_spec_marker_changed"
                bot.last_recovery_verify_state = "rolling"
                bot.last_recovery_verify_unreadable = False
                return True, "current-spec damageii damage12.2"
            if "guarded startup verify" in context:
                bot.last_recovery_verify_details = {
                    "reason": "popup_confirmed_mid_polling",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "popup_confirmed_mid_polling"
                bot.last_recovery_verify_state = "rolling"
                bot.last_recovery_verify_unreadable = False
                return True, "current spec rampage combo ramp 20 damage 20"
            if "auto verify" in context:
                bot.last_recovery_verify_details = {
                    "reason": "trait_changed:rampage",
                    "signal_sources": ["ocr", "popup", "banner", "image_change"],
                    "image_changed_samples": 0,
                    "max_change_score": 0.0,
                }
                bot.last_recovery_reason = "trait_changed:rampage"
                bot.last_recovery_verify_state = "rolling"
                bot.last_recovery_verify_unreadable = False
                return True, "damageii damage"
            raise AssertionError(f"unexpected stats_changed context: {context}")

        bot.stats_changed = fake_stats_changed

        result = bot.start_or_recover("Initial Auto Start")

        self.assertFalse(result)
        self.assertEqual(bot.last_startup_result, "failed_no_roll_detected")
        self.assertEqual(clicks, [])
        self.assertTrue(any("marker-only or weak rolling evidence rejected | phase=primary | reason=trait_changed:rampage" in message for message in messages))
        self.assertTrue(any("startup_auto_click_blocked_non_bad_current_roll" in message for message in messages))


    def test_watchdog_recovery_stage_uses_bounded_fast_verify_profile(self):
        messages = []
        bot = self.make_bot(messages)
        bot.auto_checkbox_state = lambda: "disabled"
        bot.popup_active = lambda *_args, **_kwargs: False
        bot.banner_active = lambda: False
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        bot.click = lambda *args, **kwargs: None
        verify_calls = []

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            verify_calls.append((context, kwargs))
            bot.last_recovery_verify_details = {
                "reason": "popup_confirmed_mid_polling",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "popup_confirmed_mid_polling"
            return True, "current spec rampage combo ramp 20 damage 20"

        bot.stats_changed = fake_stats_changed

        result = bot.unexpected_not_rolling_watchdog(
            "current-spec critdamagei critdamage2.5",
            "NON_TARGET",
            "critdamagei",
            idle_for=6.2,
            popup_known_clear=True,
            banner_known_clear=True,
            stage="recovery",
        )

        self.assertEqual(result, "recovered")
        self.assertEqual(len(verify_calls), 1)
        context, kwargs = verify_calls[0]
        self.assertIn("Unexpected No-Roll Watchdog verify", context)
        self.assertEqual(kwargs["polls_override"], 3)
        self.assertEqual(kwargs["poll_delay_override"], 0.04)
        self.assertEqual(kwargs["unreadable_fast_fail_polls"], 2)
        self.assertEqual(kwargs["psm_sequence_override"], (6, 7, 6))

    def test_manual_reroll_reenable_uses_faster_transition_profile(self):
        messages = []
        bot = self.make_bot(messages)
        bot.auto_checkbox_state = lambda: "disabled"
        bot.clear_recovery_failures = lambda *_args, **_kwargs: None
        clicks = []
        bot.click = lambda *args, **kwargs: clicks.append((args, kwargs))
        verify_calls = []

        def fake_stats_changed(baseline, context="Rolling activity", **kwargs):
            verify_calls.append((context, kwargs))
            bot.last_recovery_verify_details = {
                "reason": "popup_confirmed_mid_polling",
                "signal_sources": ["ocr", "popup", "banner", "image_change"],
                "image_changed_samples": 0,
                "max_change_score": 0.0,
            }
            bot.last_recovery_reason = "popup_confirmed_mid_polling"
            return True, "current spec rampage combo ramp 20 damage 20"

        bot.stats_changed = fake_stats_changed

        result = bot._attempt_auto_reenable_once(
            "Manual Reroll Auto Resume Recovery",
            "executioner below 50 hp 41.1 dmg 2.0 crit damage 11.3",
            trait="executioner",
            state="BAD",
            verify_signal="manual_reroll_auto_reenable",
            force_click_on_ambiguous=True,
        )

        self.assertTrue(result)
        self.assertEqual(len(clicks), 1)
        self.assertEqual(clicks[0][1]["settle"], 0.10)
        self.assertEqual(len(verify_calls), 1)
        context, kwargs = verify_calls[0]
        self.assertIn("Manual Reroll Auto Resume Recovery verify", context)
        self.assertEqual(kwargs["polls_override"], 2)
        self.assertEqual(kwargs["poll_delay_override"], 0.03)

    def test_watchdog_default_suspicion_timeout_is_tighter_but_bounded(self):
        bot = self.make_bot([])
        bot.cfg["STUCK_TIMEOUT"] = 6.0
        self.assertAlmostEqual(bot._watchdog_suspicion_timeout(), 2.88, places=2)

if __name__ == "__main__":
    unittest.main()
