import unittest

from aelrith_forge.backend.bot import AelrithForgeBot, DEFAULT_REAL_RULES
from aelrith_forge.backend.powers import (
    POWER_DEFAULT_RULES,
    SUPPORTED_POWER_DEFINITIONS,
    extract_power_passive,
    parse_power_roll_text,
    sanitize_power_rules,
    summarize_power_values,
)


class PowerCandidateBot(AelrithForgeBot):
    def __init__(self, candidates):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.cfg["CURRENT_SPEC_MARKER_OCR"] = False
        self._candidates = list(candidates)
        self.set_roll_domain("powers")
        self.set_power_rules(POWER_DEFAULT_RULES)
        self.set_enabled_powers({"cursebrand", "colossus", "subjugator"})

    def get_stats_ocr_candidates(self, *args, **kwargs):
        if kwargs.get("fallback_only"):
            return []
        return list(self._candidates)


class SpecsCandidateBot(AelrithForgeBot):
    def __init__(self, candidates):
        self.messages = []
        super().__init__(self.messages.append, lambda *_: None)
        self.cfg["OCR_DEBUG_FILE"] = False
        self.cfg["CURRENT_SPEC_MARKER_OCR"] = False
        self._candidates = list(candidates)
        self.set_rules(DEFAULT_REAL_RULES)
        self.set_enabled_specs({"fortune", "chosen", "executioner", "rampage"})

    def get_stats_ocr_candidates(self, *args, **kwargs):
        if kwargs.get("fallback_only"):
            return []
        return list(self._candidates)


class PowersFoundationTests(unittest.TestCase):
    def test_authoritative_mythical_power_definitions(self):
        expected = {
            "cursebrand": {
                "stats": {
                    "damage": (18.0, 30.0, True),
                    "hp": (15.0, 30.0, False),
                    "crit_chance": (2.0, 4.0, True),
                    "crit_damage": (6.0, 12.0, True),
                },
                "passive": ("npc_increased_damage", "NPC increased damage", 10.0, 15.0, None, "Stacks with 2 players"),
            },
            "colossus": {
                "stats": {
                    "damage": (20.0, 34.0, True),
                    "hp": (20.0, 35.0, False),
                    "crit_chance": (1.5, 3.0, True),
                    "crit_damage": (5.0, 10.0, True),
                    "luck": (7.5, 15.0, True),
                },
                "passive": ("boss_damage_bonus", "Boss damage bonus", 15.0, 25.0, None, ""),
            },
            "subjugator": {
                "stats": {
                    "damage": (24.0, 40.0, True),
                    "hp": (24.0, 40.0, False),
                    "crit_chance": (1.75, 3.5, True),
                    "crit_damage": (6.5, 13.0, True),
                    "luck": (8.5, 17.5, True),
                },
                "passive": ("npc_movement_slow", "NPC movement slow", 20.0, 20.0, 5.0, "Cannot be stacked"),
            },
        }

        for key, expected_definition in expected.items():
            definition = SUPPORTED_POWER_DEFINITIONS[key]
            self.assertEqual(definition.rarity, "Mythical")
            stats = {stat.key: (stat.min_value, stat.max_value, stat.required) for stat in definition.stats}
            self.assertEqual(stats, expected_definition["stats"])
            passive = definition.passive
            self.assertIsNotNone(passive)
            self.assertEqual(
                (
                    passive.key,
                    passive.label,
                    passive.min_value,
                    passive.max_value,
                    passive.duration_seconds,
                    passive.note,
                ),
                expected_definition["passive"],
            )
            self.assertEqual(definition.passive_family, expected_definition["passive"][1])
            self.assertEqual(definition.passive_numeric_range, expected_definition["passive"][2:4])
            self.assertEqual(definition.passive_notes, expected_definition["passive"][5])
            self.assertEqual(passive.passive_family, expected_definition["passive"][1])
            self.assertEqual(passive.passive_numeric_range, expected_definition["passive"][2:4])
            self.assertEqual(passive.passive_notes, expected_definition["passive"][5])
            self.assertEqual(definition.rule_labels[-1], expected_definition["passive"][1])
            self.assertEqual(definition.rule_caps[-1], expected_definition["passive"][3])
            self.assertEqual(POWER_DEFAULT_RULES[key][-1], (expected_definition["passive"][3], expected_definition["passive"][3]))

    def test_legacy_power_rules_are_backfilled_with_passive_thresholds(self):
        legacy = {
            "cursebrand": [(30.0, 30.0), (30.0, 30.0), (4.0, 4.0), (12.0, 12.0)],
        }
        clean = sanitize_power_rules(legacy)
        self.assertEqual(len(clean["cursebrand"]), len(SUPPORTED_POWER_DEFINITIONS["cursebrand"].rule_targets))
        self.assertEqual(clean["cursebrand"][-1], (15.0, 15.0))

    def assertParsedValues(self, text, power_key, values, passive_label, passive_value, passive_duration=None):
        parsed = parse_power_roll_text(text)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["power"], power_key)
        self.assertEqual(parsed["power_name"], SUPPORTED_POWER_DEFINITIONS[power_key].name)
        self.assertEqual(parsed["passive_family"], passive_label)
        self.assertEqual(parsed["passive_family_key"], parsed["passive"]["family_key"])
        self.assertTrue(parsed["passive_detected"])
        self.assertAlmostEqual(parsed["passive_value"], passive_value)
        self.assertEqual(parsed["parsed_stats"], parsed["values"])
        for stat_key, expected_value in values.items():
            self.assertAlmostEqual(parsed["values"][stat_key], expected_value)
            self.assertAlmostEqual(parsed["parsed_stats"][stat_key], expected_value)
        passive = parsed["passive"]
        self.assertTrue(passive["detected"])
        self.assertEqual(passive["family_label"], passive_label)
        self.assertAlmostEqual(passive["value"], passive_value)
        if passive_duration is None:
            self.assertIsNone(passive["duration_seconds"])
            self.assertIsNone(parsed["passive_duration"])
            self.assertIsNone(parsed["passive_duration_seconds"])
        else:
            self.assertAlmostEqual(passive["duration_seconds"], passive_duration)
            self.assertEqual(parsed["passive_duration"], f"{passive_duration:g}s")
            self.assertAlmostEqual(parsed["passive_duration_seconds"], passive_duration)
        summary = summarize_power_values(parsed["power"], parsed["values"], parsed["passive"])
        self.assertIn(f"Passive {passive_label}", summary)
        return parsed

    def test_inline_power_roll_examples_parse_stats_and_passives(self):
        self.assertParsedValues(
            "Cursebrand > NPCs take +12.1% DMG, Damage 28.4%, CritChance 3.6%, HP 22.1%, CritDamage 11.4%",
            "cursebrand",
            {
                "damage": 28.4,
                "crit_chance": 3.6,
                "hp": 22.1,
                "crit_damage": 11.4,
            },
            "NPC increased damage",
            12.1,
        )
        self.assertParsedValues(
            "Colossus > +23.4% Boss DMG, Damage 22.2%, Crit Chance 1.8%, Luck 14.6%, HP 27.8%, Crit Damage 7.6%",
            "colossus",
            {
                "damage": 22.2,
                "crit_chance": 1.8,
                "luck": 14.6,
                "hp": 27.8,
                "crit_damage": 7.6,
            },
            "Boss damage bonus",
            23.4,
        )
        self.assertParsedValues(
            "Subjugator > NPC Slow 20% / 5s, Damage 38.9%, CritChance 3.1%, Luck 9.9%, HP 36.3%, CritDamage 9.3%",
            "subjugator",
            {
                "damage": 38.9,
                "crit_chance": 3.1,
                "luck": 9.9,
                "hp": 36.3,
                "crit_damage": 9.3,
            },
            "NPC movement slow",
            20.0,
            5.0,
        )

    def test_inline_power_parser_normalizes_compact_variants(self):
        variants = [
            (
                "Cursebrand>NPCs take+12.1%DMG Damage28.4 CritChance3.6 HP22.1 CritDamage11.4",
                "cursebrand",
                "NPC increased damage",
                12.1,
                {"damage": 28.4, "crit_chance": 3.6, "hp": 22.1, "crit_damage": 11.4},
            ),
            (
                "Colossus +23.4% BossDMG; Damage22.2; CritChance1.8; Luck14.6; HP27.8; CritDamage7.6",
                "colossus",
                "Boss damage bonus",
                23.4,
                {"damage": 22.2, "crit_chance": 1.8, "luck": 14.6, "hp": 27.8, "crit_damage": 7.6},
            ),
            (
                "Subjugator NPCSlow20%/5s Damage38.9 CritChance3.1 Luck9.9 HP36.3 CritDamage9.3",
                "subjugator",
                "NPC movement slow",
                20.0,
                {"damage": 38.9, "crit_chance": 3.1, "luck": 9.9, "hp": 36.3, "crit_damage": 9.3},
            ),
            (
                "Subjugator movement slowed by 20% for 5s Damage38.9 CritChance3.1 Luck9.9 HP36.3 CritDamage9.3",
                "subjugator",
                "NPC movement slow",
                20.0,
                {"damage": 38.9, "crit_chance": 3.1, "luck": 9.9, "hp": 36.3, "crit_damage": 9.3},
            ),
        ]
        for text, power_key, passive_label, passive_value, values in variants:
            with self.subTest(text=text):
                self.assertParsedValues(text, power_key, values, passive_label, passive_value, 5.0 if power_key == "subjugator" else None)

    def test_family_specific_passive_extraction(self):
        cursebrand = extract_power_passive("cursebrand", "NPCs take +13.9% DMG")
        colossus = extract_power_passive("colossus", "+23.4% Boss DMG")
        subjugator = extract_power_passive("subjugator", "NPC Slow 20% / 5s")

        self.assertEqual(cursebrand["family_key"], "npc_increased_damage")
        self.assertAlmostEqual(cursebrand["value"], 13.9)
        self.assertEqual(colossus["family_key"], "boss_damage_bonus")
        self.assertAlmostEqual(colossus["value"], 23.4)
        self.assertEqual(subjugator["family_key"], "npc_movement_slow")
        self.assertAlmostEqual(subjugator["value"], 20.0)
        self.assertAlmostEqual(subjugator["duration_seconds"], 5.0)

    def test_power_candidate_keeps_structured_passive_fields(self):
        bot = PowerCandidateBot([
            (
                "tesseract-full-original-psm6",
                "Cursebrand > NPCs take +12.1% DMG, Damage 28.4%, CritChance 3.6%, HP 22.1%, CritDamage 11.4%",
                "Cursebrand > NPCs take +12.1% DMG, Damage 28.4%, CritChance 3.6%, HP 22.1%, CritDamage 11.4%",
            )
        ])
        parsed, fallback_text = bot._parse_power_candidates(bot.get_stats_ocr_candidates())
        self.assertFalse(fallback_text)
        self.assertEqual(parsed["power_name"], "Cursebrand")
        self.assertEqual(parsed["passive_family"], "NPC increased damage")
        self.assertAlmostEqual(parsed["passive_value"], 12.1)
        self.assertIsNone(parsed["passive_duration"])
        self.assertEqual(parsed["parsed_stats"], parsed["values"])
        self.assertAlmostEqual(parsed["parsed_stats"]["damage"], 28.4)

    def test_hp_is_optional_for_power_matches(self):
        bot = PowerCandidateBot([
            (
                "tesseract-full-original-psm6",
                "Current Power Cursebrand NPCs take +15% DMG Damage 30 Crit Chance 4 Crit Damage 12",
                "Current Power Cursebrand NPCs take +15% DMG Damage 30 Crit Chance 4 Crit Damage 12",
            )
        ])
        bot.set_power_rules(
            sanitize_power_rules(
                {
                    "cursebrand": [(30.0, 30.0), (30.0, 30.0), (4.0, 4.0), (12.0, 12.0)],
                    "colossus": POWER_DEFAULT_RULES["colossus"],
                    "subjugator": POWER_DEFAULT_RULES["subjugator"],
                }
            )
        )
        state, trait, summary, _text, missing, near = bot.check_roll()
        self.assertEqual(state, "GOD")
        self.assertEqual(trait, "cursebrand")
        self.assertIn("HP (optional) ?", summary)
        self.assertFalse(missing)
        self.assertFalse(near)

    def test_low_hp_does_not_block_power_matches(self):
        bot = PowerCandidateBot([
            (
                "tesseract-full-original-psm6",
                "Colossus > +23.4% Boss DMG, Damage 34, Crit Chance 3, Luck 15, HP 1, Crit Damage 10",
                "Colossus > +23.4% Boss DMG, Damage 34, Crit Chance 3, Luck 15, HP 1, Crit Damage 10",
            )
        ])
        bot.set_power_rules(
            sanitize_power_rules(
                {
                    "cursebrand": POWER_DEFAULT_RULES["cursebrand"],
                    "colossus": [(34.0, 34.0), (35.0, 35.0), (3.0, 3.0), (10.0, 10.0), (15.0, 15.0), (23.0, 25.0)],
                    "subjugator": POWER_DEFAULT_RULES["subjugator"],
                }
            )
        )
        state, trait, summary, _text, missing, near = bot.check_roll()
        self.assertEqual(state, "GOD")
        self.assertEqual(trait, "colossus")
        self.assertIn("HP (optional) 1", summary)
        self.assertIn("Passive Boss damage bonus 23.4", summary)
        self.assertFalse(missing)
        self.assertFalse(near)

    def test_passive_threshold_blocks_when_configured_target_is_missed(self):
        bot = PowerCandidateBot([
            (
                "tesseract-full-original-psm6",
                "Cursebrand > NPCs take +12.1% DMG, Damage 30, CritChance 4, CritDamage 12",
                "Cursebrand > NPCs take +12.1% DMG, Damage 30, CritChance 4, CritDamage 12",
            )
        ])
        state, trait, summary, _text, missing, near = bot.check_roll()
        self.assertEqual(state, "BAD")
        self.assertEqual(trait, "cursebrand")
        self.assertIn("Passive NPC increased damage 12.1", summary)
        self.assertTrue(any("NPC increased damage" in item for item in missing))
        self.assertTrue(near)

    def test_unsupported_power_is_classified_as_reroll_required(self):
        bot = PowerCandidateBot([
            (
                "tesseract-full-original-psm6",
                "Current Power Berserker Damage 22 Crit Chance 2 Crit Damage 9",
                "Current Power Berserker Damage 22 Crit Chance 2 Crit Damage 9",
            )
        ])
        state, trait, summary, _text, missing, near = bot.check_roll()
        self.assertEqual(state, "DISABLED")
        self.assertEqual(trait, "non_target_power")
        self.assertIn("manual reroll required", summary.lower())
        self.assertEqual(missing, ["Unsupported power"])
        self.assertFalse(near)

    def test_specs_classification_still_works_unchanged(self):
        bot = SpecsCandidateBot([
            (
                "tesseract-full-original-psm6",
                "Current Spec Fortune Chosen Drop 30 Luck 10",
                "Current Spec Fortune Chosen Drop 30 Luck 10",
            )
        ])
        state, trait, summary, _text, _missing, _near = bot.check_roll(allow_fallback=False)
        self.assertEqual(state, "GOD")
        self.assertEqual(trait, "fortune")
        self.assertIn("Drop 30", summary)


if __name__ == "__main__":
    unittest.main()
