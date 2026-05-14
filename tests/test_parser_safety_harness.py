import pytest

from aelrith_forge.backend.bot import (
    AelrithForgeBot,
    DEFAULT_REAL_RULES,
    detect_rollable_non_target_trait,
    detect_trait,
    normalize_text,
    parse_passive_shard_count,
    parse_power_shard_count,
    sanitize_rules,
)
from aelrith_forge.backend.normalization import normalize_stat_tokens
from aelrith_forge.backend.powers import (
    POWER_DEFAULT_RULES,
    evaluate_power,
    parse_power_roll_text,
    power_near_miss,
    sanitize_power_rules,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Current Spec Ranpage Damage 29 Crit Chance 3 Crit Damage 9", "rampage"),
        ("Current Spec Rarnpage Combo Ramp 22 Damage 29 Crit Rate 3 Crit Damage 9", "rampage"),
        ("rampage combo ramp 22 damage 29 crit chance 3 crit damage 9", "rampage"),
    ],
)
def test_detect_trait_rampage_ocr_aliases(raw, expected):
    assert detect_trait(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Current Spec Fortune Chosen Drop 29.5 Luck 9.5", "fortune"),
        ("Current Spec Chosen Drop 29.5 Luck 9.5", "fortune"),
        ("Current Spec Executioner NPC DMG 44 Crit Chance 2 Crit Damage 10", "executioner"),
    ],
)
def test_detect_trait_supported_allowlist(raw, expected):
    assert detect_trait(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Current Spec Dead Eye Damage 1", "non_target"),
        ("Current Spec Vigor HP 1", "non_target"),
    ],
)
def test_detect_rollable_non_target_trait(raw, expected):
    assert detect_rollable_non_target_trait(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "CURRENT-SPEC. CritDamageI>CritDamage2.1%",
        "CURRENT-SPEC. CritChanceII>CritChance0.7%",
        "CURRENT-SPEC. DamageI>Damage14.6%",
    ],
)
def test_generic_non_target_rejects_glued_stat_fragments(raw):
    bot = AelrithForgeBot(lambda *_: None, lambda *_: None)

    assert bot._generic_rollable_non_target_from_text(raw) is None


@pytest.mark.parametrize(
    "raw",
    [
        "DamageI>Damage6.8%",
        "CritDamageI>CritDamage2.1%",
        "CritChanceII>CritChance0.7%",
    ],
)
def test_detect_trait_rejects_glued_stat_fragments(raw):
    assert detect_trait(raw) is None


def test_generic_non_target_redacts_unsupported_trait_names():
    bot = AelrithForgeBot(lambda *_: None, lambda *_: None)

    assert bot._generic_rollable_non_target_from_text("Current Spec Frostborn Damage 12.5") == "non_target"


@pytest.mark.parametrize(
    "raw",
    [
        "Current Spec Dead Eye Damage 1",
        "Current Spec Vigor HP 1",
        "Current Spec Monarch Damage 1",
        "Current Spec Blitz Damage 1",
        "Current Spec Frostborn Damage 12.5",
    ],
)
def test_unsupported_traits_do_not_detect_as_supported(raw):
    assert detect_trait(raw) is None


@pytest.mark.parametrize(
    ("raw", "expected_fragment"),
    [
        ("danage", "damage"),
        ("crit darmage", "crit damage"),
        ("crit danage", "crit damage"),
        ("ait chance", "crit chance"),
        ("crit cance", "crit chance"),
        ("ranpage", "rampage"),
        ("rarnpage", "rampage"),
    ],
)
def test_normalize_text_repairs_common_ocr_typos(raw, expected_fragment):
    assert expected_fragment in normalize_text(raw)


def test_normalize_stat_tokens_keeps_rampage_damage_labels_distinct():
    normalized = normalize_stat_tokens(
        "Ranpage Combo Ramp 26.5 Danage 28.4 Crit Cance 3.2 Crit Darmage 7.2"
    )

    assert "combo_ramp" in normalized
    assert "damage" in normalized
    assert "crit_rate" in normalized
    assert "crit_damage" in normalized
    assert normalized.index("damage") < normalized.index("crit_rate") < normalized.index("crit_damage")


def test_sanitize_rules_preserves_current_rampage_four_stat_shape():
    clean = sanitize_rules(
        {
            "rampage": [(15.0, 30.0), (29.0, 30.0), (3.0, 4.0), (9.0, 10.0)],
        }
    )

    assert clean["rampage"] == [(15.0, 30.0), (29.0, 30.0), (3.0, 4.0), (9.0, 10.0)]


def test_sanitize_rules_migrates_legacy_rampage_three_range_config():
    clean = sanitize_rules(
        {
            "rampage": [(19.3, 30.0), (3.0, 4.0), (9.0, 10.0)],
        }
    )

    assert clean["rampage"] == [DEFAULT_REAL_RULES["rampage"][0], (19.3, 30.0), (3.0, 4.0), (9.0, 10.0)]


@pytest.mark.parametrize(
    ("raw", "expected", "expected_normalized"),
    [
        ("71k", 71000, "71k"),
        ("71.0k", 71000, "71.0k"),
        ("71,0k", 71000, "71.0k"),
        ("71000", 71000, "71000"),
    ],
)
def test_parse_passive_shard_count_variants(raw, expected, expected_normalized):
    value, normalized = parse_passive_shard_count(raw)

    assert value == expected
    assert normalized == expected_normalized


def test_parse_passive_shard_previous_value_guard_keeps_high_value():
    value, normalized = parse_passive_shard_count("71k", previous_value=710000)

    assert value == 710000
    assert normalized == "71k"


@pytest.mark.parametrize(
    ("raw", "expected", "expected_normalized"),
    [
        ("Power Shards: 71k", 71000, "71k"),
        ("Power Shards: 71,0k", 71000, "71.0k"),
        ("Power Shards: 71000", 71000, "71000"),
    ],
)
def test_parse_power_shard_count_variants(raw, expected, expected_normalized):
    value, normalized = parse_power_shard_count(raw)

    assert value == expected
    assert normalized == expected_normalized


@pytest.mark.parametrize(
    ("raw", "power", "values", "passive_family", "passive_value", "duration"),
    [
        (
            "Cursebrand NPCs take +12.1% DMG Damage 28.4 Crit Chance 3.6 Crit Damage 11.4",
            "cursebrand",
            {"damage": 28.4, "hp": None, "crit_chance": 3.6, "crit_damage": 11.4},
            "NPC increased damage",
            12.1,
            None,
        ),
        (
            "Colossus +23.4% Boss DMG Damage 22.2 Crit Chance 1.8 Luck 14.6 Crit Damage 7.6",
            "colossus",
            {"damage": 22.2, "hp": None, "crit_chance": 1.8, "crit_damage": 7.6, "luck": 14.6},
            "Boss damage bonus",
            23.4,
            None,
        ),
        (
            "Subjugator NPC Slow 20% / 5s Damage 38.9 Crit Chance 3.1 Luck 9.9 Crit Damage 9.3",
            "subjugator",
            {"damage": 38.9, "hp": None, "crit_chance": 3.1, "crit_damage": 9.3, "luck": 9.9},
            "NPC movement slow",
            20.0,
            5.0,
        ),
    ],
)
def test_parse_power_roll_text_supported_mythical_examples(raw, power, values, passive_family, passive_value, duration):
    parsed = parse_power_roll_text(raw)

    assert parsed is not None
    assert parsed["power"] == power
    assert parsed["values"] == values
    assert parsed["passive_family"] == passive_family
    assert parsed["passive_value"] == pytest.approx(passive_value)
    assert parsed["passive_duration_seconds"] == duration
    assert parsed["passive_detected"] is True


def test_evaluate_power_accepts_missing_optional_hp_when_required_targets_match():
    parsed = parse_power_roll_text(
        "Cursebrand NPCs take +15% DMG Damage 30 Crit Chance 4 Crit Damage 12"
    )
    rules = sanitize_power_rules(POWER_DEFAULT_RULES)

    matched, missing = evaluate_power(parsed["power"], parsed["values"], rules, parsed["passive"])

    assert missing == []
    assert matched[1] == (30.0, 30.0, False)


def test_evaluate_power_accepts_low_optional_hp_when_required_targets_match():
    parsed = parse_power_roll_text(
        "Colossus +25% Boss DMG Damage 34 HP 1 Crit Chance 3 Crit Damage 10 Luck 15"
    )
    rules = sanitize_power_rules(POWER_DEFAULT_RULES)

    matched, missing = evaluate_power(parsed["power"], parsed["values"], rules, parsed["passive"])

    assert missing == []
    assert matched[1] == (35.0, 35.0, False)


def test_power_near_miss_flags_close_required_roll_only():
    rules = sanitize_power_rules(POWER_DEFAULT_RULES)
    near = parse_power_roll_text(
        "Cursebrand NPCs take +15% DMG Damage 30 Crit Chance 4 Crit Damage 11.8"
    )
    bad = parse_power_roll_text(
        "Cursebrand NPCs take +10% DMG Damage 20 Crit Chance 2 Crit Damage 6"
    )

    assert power_near_miss(near["power"], near["values"], rules, near["passive"]) is True
    assert power_near_miss(bad["power"], bad["values"], rules, bad["passive"]) is False
