from __future__ import annotations

import difflib
import re


STAT_ALIASES = {
    "combo_ramp": [
        "combo ramp",
        "combo",
        "cobo ramp",
        "combo ratup",
        "combo ranp",
        "ramp combo",
        "rampage combo ramp",
        "rampage combo",
    ],
    "damage": [
        "damage",
        "damarge",
        "danage",
        "dmg",
        "cap damage",
        "capdamage",
        "damage cap",
        "daiage",
        "dalage",
        "dalliage",
        "daniage",
        "dainage",
        "dauiage",
        "dalleee",
        "damne",
        "datese",
        "rampage damage",
    ],
    "crit_rate": [
        "crit rate",
        "crit chance",
        "critrate",
        "critchance",
        "ait ance",
        "ait chance",
        "ait cance",
        "ait oance",
        "ait onance",
        "uit ance",
        "uit chance",
        "uit cance",
        "uit oance",
        "uit onance",
        "ccrit chance",
        "crit oance",
        "crit cance",
        "ert chanice",
        "bmcaitchance",
        "crit chanoe",
        "crit chanee",
        "crit rata",
        "critical rate",
        "critical chance",
    ],
    "crit_damage": [
        "crit damage",
        "critdamage",
        "crit dmg",
        "critdmg",
        "crit danuge",
        "critdanuge",
        "crit danage",
        "crit darmaee",
        "crit darmage",
        "grit damage",
        "gritdamage",
        "git damare",
        "gitdamare",
        "ciit daitage",
        "ciitdaitage",
        "gilt danere",
        "giltdanere",
        "git damage",
        "iit damage",
        "iitdamage",
        "gait damage",
        "gaitdamage",
        "qit damage",
        "eit dantige",
        "gtdakige",
        "critical damage",
    ],
    "drop": [
        "drop",
        "drop chance",
        "fortune chosen",
        "fortunechosen",
        "fortune chosen drop",
    ],
    "luck": [
        "luck",
    ],
    "npc_damage": [
        "npc dmg",
        "npcdmg",
        "npc damage",
        "npcdamage",
        "executioner npc dmg",
        "executioner npc damage",
        "hp dmg",
        "below 50 hp dmg",
    ],
}

STAT_CANONICAL_LABELS = {
    "combo_ramp": "Combo Ramp",
    "damage": "Damage",
    "crit_rate": "Crit Rate",
    "crit_damage": "Crit Damage",
    "drop": "Drop",
    "luck": "Luck",
    "npc_damage": "NPC DMG",
}

_ALIAS_TO_KEY = {
    alias: key
    for key, aliases in STAT_ALIASES.items()
    for alias in aliases
}


def normalize_ocr_text(text: str) -> str:
    text = (text or "").lower().replace(",", ".")
    text = re.sub(r"[%+*`~!@#$^&_=\\/<>{}\[\]\"']", " ", text)
    text = text.replace("|", " ").replace(":", " ").replace(";", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def remove_symbols(text: str) -> str:
    return re.sub(r"[^a-z0-9. ]+", " ", normalize_ocr_text(text))


def canonical_stat_key(raw_label: str, cutoff: float = 0.72) -> str | None:
    cleaned = remove_symbols(raw_label)
    if not cleaned:
        return None

    if cleaned in _ALIAS_TO_KEY:
        return _ALIAS_TO_KEY[cleaned]

    for alias, key in sorted(_ALIAS_TO_KEY.items(), key=lambda item: len(item[0]), reverse=True):
        if alias in cleaned or cleaned in alias:
            return key

    match = difflib.get_close_matches(cleaned, _ALIAS_TO_KEY.keys(), n=1, cutoff=cutoff)
    return _ALIAS_TO_KEY[match[0]] if match else None


def normalize_stat_tokens(text: str) -> str:
    cleaned = normalize_ocr_text(text)
    compact_aliases = {
        alias.replace(" ", ""): alias
        for alias in _ALIAS_TO_KEY
        if " " in alias and len(alias.replace(" ", "")) >= 6
    }
    for compact, spaced in sorted(compact_aliases.items(), key=lambda item: len(item[0]), reverse=True):
        cleaned = re.sub(re.escape(compact), f" {spaced} ", cleaned)
    cleaned = re.sub(r"(?<=[a-z_])(?=\d)", " ", cleaned)
    cleaned = re.sub(r"(?<=\d)(?=[a-z_])", " ", cleaned)
    for alias in sorted(_ALIAS_TO_KEY, key=len, reverse=True):
        key = _ALIAS_TO_KEY[alias]
        pattern = r"\b" + re.escape(alias).replace(r"\ ", r"\s+") + r"\b"
        cleaned = re.sub(pattern, key, cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
