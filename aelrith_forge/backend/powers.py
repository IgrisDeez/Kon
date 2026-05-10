from __future__ import annotations

from dataclasses import dataclass
import difflib
import re
from typing import Iterable

from .normalization import normalize_ocr_text


@dataclass(frozen=True)
class PowerStatDefinition:
    key: str
    label: str
    min_value: float
    max_value: float
    required: bool = True
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class PowerPassiveDefinition:
    key: str
    label: str
    min_value: float | None = None
    max_value: float | None = None
    duration_seconds: float | None = None
    aliases: tuple[str, ...] = ()
    note: str = ""

    @property
    def passive_family(self) -> str:
        return self.label

    @property
    def passive_numeric_range(self) -> tuple[float, float] | None:
        if self.min_value is None or self.max_value is None:
            return None
        return (self.min_value, self.max_value)

    @property
    def passive_notes(self) -> str:
        return self.note


@dataclass(frozen=True)
class PowerRuleTarget:
    key: str
    label: str
    max_value: float
    required: bool = True
    source: str = "stat"


@dataclass(frozen=True)
class PowerDefinition:
    key: str
    name: str
    rarity: str
    aliases: tuple[str, ...]
    stats: tuple[PowerStatDefinition, ...]
    passive: PowerPassiveDefinition | None = None
    passive_text: str = ""
    passive_note: str = ""

    @property
    def stat_order(self) -> list[str]:
        return [stat.key for stat in self.stats]

    @property
    def stat_labels(self) -> list[str]:
        return [stat.label for stat in self.stats]

    @property
    def stat_caps(self) -> list[float]:
        return [stat.max_value for stat in self.stats]

    @property
    def required_stat_keys(self) -> list[str]:
        return [stat.key for stat in self.stats if stat.required]

    @property
    def passive_family(self) -> str:
        return self.passive.passive_family if self.passive else ""

    @property
    def passive_numeric_range(self) -> tuple[float, float] | None:
        return self.passive.passive_numeric_range if self.passive else None

    @property
    def passive_notes(self) -> str:
        if self.passive and self.passive.passive_notes:
            return self.passive.passive_notes
        return self.passive_note

    @property
    def rule_targets(self) -> tuple[PowerRuleTarget, ...]:
        targets = [
            PowerRuleTarget(stat.key, stat.label, stat.max_value, stat.required, "stat")
            for stat in self.stats
        ]
        if self.passive and self.passive.max_value is not None:
            targets.append(PowerRuleTarget("passive", self.passive.label, self.passive.max_value, True, "passive"))
        return tuple(targets)

    @property
    def rule_labels(self) -> list[str]:
        return [target.label for target in self.rule_targets]

    @property
    def rule_caps(self) -> list[float]:
        return [target.max_value for target in self.rule_targets]


POWER_STAT_ALIASES = {
    "damage": ("damage", "dmg", "danage", "damarge"),
    "hp": ("hp", "health", "health points"),
    "crit_chance": (
        "crit chance",
        "critical chance",
        "crit rate",
        "critical rate",
        "critchance",
        "critrate",
        "crit chancee",
        "crit cance",
        "crit oance",
        "crit chanee",
    ),
    "crit_damage": (
        "crit damage",
        "critical damage",
        "crit dmg",
        "critdmg",
        "critdamage",
        "crit danage",
        "crit darmage",
    ),
    "luck": ("luck",),
}

POWER_STAT_CANONICAL_LABELS = {
    "damage": "Damage",
    "hp": "HP",
    "crit_chance": "Crit Chance",
    "crit_damage": "Crit Damage",
    "luck": "Luck",
}

SUPPORTED_POWER_DEFINITIONS: dict[str, PowerDefinition] = {
    "cursebrand": PowerDefinition(
        key="cursebrand",
        name="Cursebrand",
        rarity="Mythical",
        aliases=("cursebrand", "curse brand", "cursbrand", "cursebramd"),
        stats=(
            PowerStatDefinition("damage", "Damage", 18.0, 30.0, True, POWER_STAT_ALIASES["damage"]),
            PowerStatDefinition("hp", "HP", 15.0, 30.0, False, POWER_STAT_ALIASES["hp"]),
            PowerStatDefinition("crit_chance", "Crit Chance", 2.0, 4.0, True, POWER_STAT_ALIASES["crit_chance"]),
            PowerStatDefinition("crit_damage", "Crit Damage", 6.0, 12.0, True, POWER_STAT_ALIASES["crit_damage"]),
        ),
        passive=PowerPassiveDefinition(
            key="npc_increased_damage",
            label="NPC increased damage",
            min_value=10.0,
            max_value=15.0,
            aliases=("npc increased damage", "npcs take damage", "npc take damage", "npc damage taken"),
            note="Stacks with 2 players",
        ),
        passive_text="NPCs take 10-15% increased damage after hit",
        passive_note="Stacks with 2 players",
    ),
    "colossus": PowerDefinition(
        key="colossus",
        name="Colossus",
        rarity="Mythical",
        aliases=("colossus", "colosus", "coiossus", "colossas"),
        stats=(
            PowerStatDefinition("damage", "Damage", 20.0, 34.0, True, POWER_STAT_ALIASES["damage"]),
            PowerStatDefinition("hp", "HP", 20.0, 35.0, False, POWER_STAT_ALIASES["hp"]),
            PowerStatDefinition("crit_chance", "Crit Chance", 1.5, 3.0, True, POWER_STAT_ALIASES["crit_chance"]),
            PowerStatDefinition("crit_damage", "Crit Damage", 5.0, 10.0, True, POWER_STAT_ALIASES["crit_damage"]),
            PowerStatDefinition("luck", "Luck", 7.5, 15.0, True, POWER_STAT_ALIASES["luck"]),
        ),
        passive=PowerPassiveDefinition(
            key="boss_damage_bonus",
            label="Boss damage bonus",
            min_value=15.0,
            max_value=25.0,
            aliases=("boss damage bonus", "boss damage", "boss dmg"),
        ),
        passive_text="15-25% boss damage",
    ),
    "subjugator": PowerDefinition(
        key="subjugator",
        name="Subjugator",
        rarity="Mythical",
        aliases=("subjugator", "subjugat0r", "subjagator", "subjugatcr"),
        stats=(
            PowerStatDefinition("damage", "Damage", 24.0, 40.0, True, POWER_STAT_ALIASES["damage"]),
            PowerStatDefinition("hp", "HP", 24.0, 40.0, False, POWER_STAT_ALIASES["hp"]),
            PowerStatDefinition("crit_chance", "Crit Chance", 1.75, 3.5, True, POWER_STAT_ALIASES["crit_chance"]),
            PowerStatDefinition("crit_damage", "Crit Damage", 6.5, 13.0, True, POWER_STAT_ALIASES["crit_damage"]),
            PowerStatDefinition("luck", "Luck", 8.5, 17.5, True, POWER_STAT_ALIASES["luck"]),
        ),
        passive=PowerPassiveDefinition(
            key="npc_movement_slow",
            label="NPC movement slow",
            min_value=20.0,
            max_value=20.0,
            duration_seconds=5.0,
            aliases=("npc movement slow", "npc slow", "movement slowed", "slow"),
            note="Cannot be stacked",
        ),
        passive_text="NPC movement slowed by 20% for 5s",
        passive_note="Cannot be stacked",
    ),
}

POWER_DISPLAY_NAMES = {key: definition.name for key, definition in SUPPORTED_POWER_DEFINITIONS.items()}

POWER_DEFAULT_RULES = {
    key: [(target.max_value, target.max_value) for target in definition.rule_targets]
    for key, definition in SUPPORTED_POWER_DEFINITIONS.items()
}


def power_display_name(key: str | None) -> str:
    if not key:
        return "Unknown Power"
    definition = SUPPORTED_POWER_DEFINITIONS.get(key)
    if definition:
        return definition.name
    return str(key).replace("_", " ").title()


def all_power_stat_aliases() -> dict[str, tuple[str, ...]]:
    aliases = {}
    for definition in SUPPORTED_POWER_DEFINITIONS.values():
        for stat in definition.stats:
            aliases[stat.key] = tuple(stat.aliases or POWER_STAT_ALIASES.get(stat.key, (stat.label.lower(),)))
    return aliases


def default_power_layout_settings() -> dict:
    return {
        "stats_region": "0,0,0,0",
        "current_power_region": "0,0,0,0",
        "preview_region": "0,0,0,0",
        "auto_check_region": "0,0,0,0",
        "confirm_check_region": "0,0,0,0",
        "popup_region": "0,0,0,0",
        "protected_region": "0,0,0,0",
        "change_detection_exclusion_region": "0,0,0,0",
        "coords": {
            "auto": "0,0",
            "roll": "0,0",
            "yes": "0,0",
        },
    }


def default_power_settings() -> dict:
    return {
        "enabled_powers": {key: True for key in SUPPORTED_POWER_DEFINITIONS},
        "powers_rules": sanitize_power_rules(POWER_DEFAULT_RULES),
        "powers_layout": default_power_layout_settings(),
    }


def sanitize_power_rules(rules: dict | None) -> dict[str, list[tuple[float, float]]]:
    clean: dict[str, list[tuple[float, float]]] = {}
    incoming = rules or {}
    for key, definition in SUPPORTED_POWER_DEFINITIONS.items():
        provided = list(incoming.get(key, []) or [])
        clean_ranges: list[tuple[float, float]] = []
        for index, target in enumerate(definition.rule_targets):
            fallback = POWER_DEFAULT_RULES[key][index]
            try:
                low, high = provided[index]
                low = float(low)
                high = float(high)
            except Exception:
                low, high = fallback
            low = max(0.0, min(low, target.max_value))
            high = max(0.0, min(high, target.max_value))
            if low > high:
                high = low
            clean_ranges.append((round(low, 2), round(high, 2)))
        clean[key] = clean_ranges
    return clean


def power_rule_labels() -> dict[str, list[str]]:
    return {key: definition.rule_labels for key, definition in SUPPORTED_POWER_DEFINITIONS.items()}


def power_rule_caps() -> dict[str, list[float]]:
    return {key: definition.rule_caps for key, definition in SUPPORTED_POWER_DEFINITIONS.items()}


def power_required_indexes(power_key: str) -> list[int]:
    definition = SUPPORTED_POWER_DEFINITIONS[power_key]
    return [index for index, target in enumerate(definition.rule_targets) if target.required]


def power_optional_indexes(power_key: str) -> list[int]:
    definition = SUPPORTED_POWER_DEFINITIONS[power_key]
    return [index for index, target in enumerate(definition.rule_targets) if not target.required]


def normalize_power_text(text: str) -> str:
    normalized = normalize_ocr_text(text)
    replacements = {
        "curse bramd": "cursebrand",
        "curse brand": "cursebrand",
        "colosus": "colossus",
        "coiossus": "colossus",
        "subjagator": "subjugator",
        "subjugat0r": "subjugator",
        "subjugatcr": "subjugator",
        "criticalchance": "critical chance",
        "critchance": "crit chance",
        "critrate": "crit rate",
        "criticaldamage": "critical damage",
        "critdamage": "crit damage",
        "critdmg": "crit damage",
        "bossdmg": "boss damage",
        "boss dmg": "boss damage",
        "npcslow": "npc slow",
        "crit cance": "crit chance",
        "crit oance": "crit chance",
        "crit chanee": "crit chance",
        "crit danage": "crit damage",
        "crit darmage": "crit damage",
        "dmg": "damage",
    }
    for wrong, right in replacements.items():
        normalized = normalized.replace(wrong, right)
    compact_aliases = {
        "critchance": "crit chance",
        "critdamage": "crit damage",
        "critdmg": "crit damage",
        "bossdamage": "boss damage",
        "bossdmg": "boss damage",
        "npcslow": "npc slow",
    }
    for compact, spaced in sorted(compact_aliases.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = re.sub(re.escape(compact), f" {spaced} ", normalized)
    normalized = re.sub(r"(?<=[a-z])(?=\d)", " ", normalized)
    normalized = re.sub(r"(?<=\d)(?=[a-z])", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def detect_supported_power(text: str) -> str | None:
    cleaned = normalize_power_text(text)
    if not cleaned:
        return None
    compact = re.sub(r"[^a-z0-9]+", "", cleaned)
    for key, definition in SUPPORTED_POWER_DEFINITIONS.items():
        if any(alias in cleaned or alias.replace(" ", "") in compact for alias in definition.aliases):
            return key
    words = re.findall(r"[a-z]{5,}", cleaned)
    alias_pairs = [
        (alias.replace(" ", ""), key)
        for key, definition in SUPPORTED_POWER_DEFINITIONS.items()
        for alias in definition.aliases
        if len(alias.replace(" ", "")) >= 5
    ]
    compact_aliases = [alias for alias, _key in alias_pairs]
    for word in words:
        match = difflib.get_close_matches(word.replace(" ", ""), compact_aliases, n=1, cutoff=0.75)
        if match:
            matched_alias = match[0]
            for alias, key in alias_pairs:
                if alias == matched_alias:
                    return key
    return None


def _iter_numbers(text: str) -> list[float]:
    numbers = []
    for match in re.findall(r"(?<![a-zA-Z0-9])\d+(?:\.\d+)?(?![a-zA-Z0-9])", text):
        try:
            numbers.append(float(match))
        except Exception:
            pass
    return numbers


def _extract_value_after_alias(text: str, aliases: Iterable[str], max_value: float) -> float | None:
    for alias in aliases:
        alias_text = normalize_power_text(alias)
        pattern = r"\b" + re.escape(alias_text).replace(r"\ ", r"\s+") + r"\b[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)"
        match = re.search(pattern, text)
        if not match:
            continue
        try:
            value = float(match.group(1))
        except Exception:
            continue
        if 0.0 <= value <= max_value + 0.1:
            return value
    return None


def _empty_passive(power_key: str, text: str = "") -> dict:
    passive = SUPPORTED_POWER_DEFINITIONS[power_key].passive
    return {
        "family_key": passive.key if passive else "",
        "family_label": passive.label if passive else "",
        "fragment": "",
        "value": None,
        "duration_seconds": None,
        "definition_min": passive.min_value if passive else None,
        "definition_max": passive.max_value if passive else None,
        "definition_duration_seconds": passive.duration_seconds if passive else None,
        "note": passive.note if passive else "",
        "detected": False,
        "source_text": text,
    }


def _passive_result(power_key: str, text: str, fragment: str, value: float | None, duration: float | None = None) -> dict:
    result = _empty_passive(power_key, text)
    passive = SUPPORTED_POWER_DEFINITIONS[power_key].passive
    if duration is None and passive and passive.duration_seconds is not None:
        duration = passive.duration_seconds
    result.update(
        {
            "fragment": fragment.strip(),
            "value": value,
            "duration_seconds": duration,
            "detected": bool(fragment or value is not None or duration is not None),
        }
    )
    return result


def extract_power_passive(power_key: str, text: str) -> dict:
    cleaned = normalize_power_text(text)
    if power_key not in SUPPORTED_POWER_DEFINITIONS:
        return {}
    if power_key == "cursebrand":
        patterns = (
            r"(npcs?\s+take\s+([0-9]+(?:\.[0-9]+)?)\s*(?:damage|dmg))",
            r"(npcs?.{0,18}?([0-9]+(?:\.[0-9]+)?)\s*(?:damage|dmg))",
        )
        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if match:
                return _passive_result(power_key, cleaned, match.group(1), float(match.group(2)))
    elif power_key == "colossus":
        patterns = (
            r"(([0-9]+(?:\.[0-9]+)?)\s*boss\s+(?:damage|dmg))",
            r"(boss\s+(?:damage|dmg)[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?))",
        )
        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if match:
                return _passive_result(power_key, cleaned, match.group(1), float(match.group(2)))
    elif power_key == "subjugator":
        patterns = (
            r"((?:npc\s+)?slow\s+([0-9]+(?:\.[0-9]+)?)\s*(?:[a-z ]{0,8})\s+([0-9]+(?:\.[0-9]+)?)\s*s)",
            r"((?:npc\s+)?slow[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?))",
        )
        for pattern in patterns:
            match = re.search(pattern, cleaned)
            if match:
                duration = float(match.group(3)) if len(match.groups()) >= 3 and match.group(3) else None
                return _passive_result(power_key, cleaned, match.group(1), float(match.group(2)), duration)
    return _empty_passive(power_key, cleaned)


def _strip_power_passive_text(power_key: str, cleaned: str) -> str:
    if power_key == "cursebrand":
        cleaned = re.sub(r"npcs?\s+take\s+[0-9]+(?:\.[0-9]+)?\s*(?:damage|dmg)", " ", cleaned)
        cleaned = re.sub(r"npcs?.{0,18}?[0-9]+(?:\.[0-9]+)?\s*(?:damage|dmg)", " ", cleaned)
    elif power_key == "colossus":
        cleaned = re.sub(r"[0-9]+(?:\.[0-9]+)?\s*boss\s+(?:damage|dmg)", " ", cleaned)
        cleaned = re.sub(r"boss\s+(?:damage|dmg)[^0-9]{0,12}[0-9]+(?:\.[0-9]+)?", " ", cleaned)
    elif power_key == "subjugator":
        cleaned = re.sub(r"(?:npc\s+)?slow\s+[0-9]+(?:\.[0-9]+)?(?:\s+[0-9]+(?:\.[0-9]+)?\s*s)?", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_power_values(power_key: str, text: str) -> dict[str, float | None]:
    cleaned = normalize_power_text(text)
    stat_text = _strip_power_passive_text(power_key, cleaned)
    definition = SUPPORTED_POWER_DEFINITIONS[power_key]
    values: dict[str, float | None] = {stat.key: None for stat in definition.stats}
    rows = [row.strip() for row in re.split(r"[\r\n|]+", stat_text) if row and row.strip()]
    if stat_text and stat_text not in rows:
        rows.append(stat_text)
    for stat in definition.stats:
        aliases = stat.aliases or POWER_STAT_ALIASES.get(stat.key, (stat.label.lower(),))
        for row in rows:
            value = _extract_value_after_alias(row, aliases, stat.max_value)
            if value is not None:
                values[stat.key] = value
                break
        if values[stat.key] is None:
            value = _extract_value_after_alias(stat_text, aliases, stat.max_value)
            if value is not None:
                values[stat.key] = value
    if all(value is None for value in values.values()):
        numbers = _iter_numbers(stat_text)
        for stat, value in zip(definition.stats, numbers):
            if 0.0 <= value <= stat.max_value + 0.1:
                values[stat.key] = value
    return values


def parse_power_roll_text(text: str) -> dict | None:
    power_key = detect_supported_power(text)
    if not power_key:
        return None
    cleaned = normalize_power_text(text)
    values = extract_power_values(power_key, text)
    passive = extract_power_passive(power_key, text)
    passive_duration_seconds = passive.get("duration_seconds")
    passive_duration = f"{float(passive_duration_seconds):g}s" if passive_duration_seconds is not None else None
    return {
        "power": power_key,
        "power_name": power_display_name(power_key),
        "normalized_text": cleaned,
        "values": values,
        "parsed_stats": values,
        "passive": passive,
        "passive_family": passive.get("family_label") or "",
        "passive_family_key": passive.get("family_key") or "",
        "passive_value": passive.get("value"),
        "passive_duration": passive_duration,
        "passive_duration_seconds": passive_duration_seconds,
        "passive_detected": bool(passive.get("detected")),
        "passive_fragment": passive.get("fragment") or "",
        "passive_numeric_range": (
            (passive.get("definition_min"), passive.get("definition_max"))
            if passive.get("definition_min") is not None and passive.get("definition_max") is not None
            else None
        ),
        "passive_notes": passive.get("note") or "",
    }


def _format_passive_summary(passive: dict | None) -> str:
    if not passive or not passive.get("detected"):
        return ""
    label = passive.get("family_label") or "Passive"
    value = passive.get("value")
    duration = passive.get("duration_seconds")
    parts = [f"Passive {label}"]
    if value is not None:
        parts.append(f"{float(value):g}")
    if duration is not None:
        parts.append(f"{float(duration):g}s")
    return " ".join(parts)


def summarize_power_values(power_key: str, values: dict[str, float | None], passive: dict | None = None) -> str:
    definition = SUPPORTED_POWER_DEFINITIONS[power_key]
    pieces = []
    passive_summary = _format_passive_summary(passive)
    if passive_summary:
        pieces.append(passive_summary)
    for stat in definition.stats:
        value = values.get(stat.key)
        suffix = " (optional)" if not stat.required else ""
        if value is None:
            pieces.append(f"{stat.label}{suffix} ?")
        else:
            pieces.append(f"{stat.label}{suffix} {value:g}")
    return " | ".join(pieces)


def _power_target_value(target: PowerRuleTarget, values: dict[str, float | None], passive: dict | None = None) -> float | None:
    if target.source == "passive":
        if not passive or not passive.get("detected"):
            return None
        value = passive.get("value")
        try:
            return float(value) if value is not None else None
        except Exception:
            return None
    value = values.get(target.key)
    try:
        return float(value) if value is not None else None
    except Exception:
        return None


def evaluate_power(
    power_key: str,
    values: dict[str, float | None],
    rules: dict[str, list[tuple[float, float]]],
    passive: dict | None = None,
) -> tuple[list[tuple[float, float, bool]], list[str]]:
    definition = SUPPORTED_POWER_DEFINITIONS[power_key]
    configured = list(rules.get(power_key, POWER_DEFAULT_RULES[power_key]))
    matched = []
    missing = []
    for index, target in enumerate(definition.rule_targets):
        low, high = configured[index]
        value = _power_target_value(target, values, passive)
        ok = value is not None and low <= value <= high
        matched.append((low, high, ok))
        if target.required and not ok:
            got = f"{value:g}" if value is not None else "not found"
            missing.append(f"{target.label}: {got} -> {low:g}-{high:g}")
    return matched, missing


def power_score(
    power_key: str,
    values: dict[str, float | None],
    rules: dict[str, list[tuple[float, float]]],
    passive: dict | None = None,
) -> float:
    definition = SUPPORTED_POWER_DEFINITIONS[power_key]
    configured = list(rules.get(power_key, POWER_DEFAULT_RULES[power_key]))
    contributions = []
    for index, target in enumerate(definition.rule_targets):
        if not target.required:
            continue
        low, high = configured[index]
        value = _power_target_value(target, values, passive)
        if value is None:
            contributions.append(0.0)
            continue
        if low <= value <= high:
            contributions.append(1.0)
            continue
        cap = max(target.max_value, 1.0)
        if value < low:
            contributions.append(max(0.0, 1.0 - ((low - value) / cap)))
        else:
            contributions.append(max(0.0, 1.0 - ((value - high) / cap)))
    if not contributions:
        return 0.0
    return round((sum(contributions) / len(contributions)) * 100.0, 2)


def power_near_miss(
    power_key: str,
    values: dict[str, float | None],
    rules: dict[str, list[tuple[float, float]]],
    passive: dict | None = None,
) -> bool:
    definition = SUPPORTED_POWER_DEFINITIONS[power_key]
    configured = list(rules.get(power_key, POWER_DEFAULT_RULES[power_key]))
    required = [target for target in definition.rule_targets if target.required]
    if not required:
        return False
    close_hits = 0
    for index, target in enumerate(definition.rule_targets):
        if not target.required:
            continue
        low, high = configured[index]
        value = _power_target_value(target, values, passive)
        if value is None:
            continue
        if low <= value <= high:
            close_hits += 1
            continue
        margin = 0.35 if target.max_value <= 4.0 else 1.0
        if min(abs(value - low), abs(value - high)) <= margin:
            close_hits += 1
    return close_hits >= max(1, len(required) - 1)
