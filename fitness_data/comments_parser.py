"""Parse structured tokens from intervals.icu wellness comments field."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Comments: hlegs:yes bfast:... lunch:... din:... snack:... xmeal:... alc:2 cafe:200 ... | notes | PC: insight
FOOD_TOKEN_PREFIXES = ("bfast", "lunch", "din", "snack", "xmeal")
TOKEN_SPLIT = re.compile(
    r"\s+(?=(?:hlegs|bfast|lunch|din|snack|xmeal|alc|cafe|cfx|med|illness|temp):)",
    re.IGNORECASE,
)
HEAVY_LEGS_VALUES = frozenset({"yes", "no"})
PC_MARKER = " | PC: "

CAFFEINE_EFFECT_VALUES = frozenset({"no", "little", "yes"})


@dataclass
class ParsedComments:
    heavy_legs: bool | None = None
    food_breakfast: str | None = None
    food_lunch: str | None = None
    food_dinner: str | None = None
    food_snacks: str | None = None
    food_extra_meal: str | None = None
    alcohol: float | None = None
    caffeine: float | None = None
    caffeine_effect: str | None = None
    medication: str | None = None
    illness: str | None = None
    temperature: float | None = None
    temperature_logged_at: str | None = None
    free_text: str | None = None
    pc_insight: str | None = None


def split_notes_and_pc(free_text: str | None) -> tuple[str | None, str | None]:
    if not free_text or not free_text.strip():
        return None, None
    text = free_text.strip()
    if PC_MARKER in text:
        user, pc = text.rsplit(PC_MARKER, 1)
        return user.strip() or None, pc.strip() or None
    if text.startswith("PC: "):
        return None, text[4:].strip() or None
    return text, None


def join_notes_and_pc(user_notes: str | None, pc_insight: str | None) -> str | None:
    user = user_notes.strip() if user_notes else None
    pc = pc_insight.strip() if pc_insight else None
    if user and pc:
        return f"{user}{PC_MARKER}{pc}"
    if pc:
        return f"PC: {pc}"
    return user


def _sanitize_food_text(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    cleaned = value.strip().replace("|", "/")
    return cleaned or None


def merge_food_field(existing: str | None, new: str | None) -> str | None:
    if new is not None:
        return _sanitize_food_text(new)
    return _sanitize_food_text(existing)


def build_comments(
    *,
    heavy_legs: bool | None = None,
    food_breakfast: str | None = None,
    food_lunch: str | None = None,
    food_dinner: str | None = None,
    food_snacks: str | None = None,
    food_extra_meal: str | None = None,
    alcohol: float | None = None,
    caffeine: float | None = None,
    caffeine_effect: str | None = None,
    medication: str | None = None,
    illness: str | None = None,
    temperature: float | None = None,
    temperature_logged_at: str | None = None,
    notes: str | None = None,
    pc_insight: str | None = None,
) -> str | None:
    """Build structured comments string for intervals.icu."""
    parts: list[str] = []
    if heavy_legs is not None:
        parts.append(f"hlegs:{'yes' if heavy_legs else 'no'}")
    for prefix, value in (
        ("bfast", food_breakfast),
        ("lunch", food_lunch),
        ("din", food_dinner),
        ("snack", food_snacks),
        ("xmeal", food_extra_meal),
    ):
        text = _sanitize_food_text(value)
        if text:
            parts.append(f"{prefix}:{text}")
    if alcohol is not None:
        parts.append(f"alc:{alcohol:g}")
    if caffeine is not None:
        parts.append(f"cafe:{caffeine:g}")
    if caffeine_effect and caffeine_effect.strip().lower() in CAFFEINE_EFFECT_VALUES:
        parts.append(f"cfx:{caffeine_effect.strip().lower()}")
    if medication and medication.strip():
        parts.append(f"med:{medication.strip()}")
    if illness and illness.strip() and illness.strip().lower() not in {"none", "no"}:
        parts.append(f"illness:{illness.strip()}")
    if temperature is not None:
        temp_token = f"temp:{temperature:g}"
        if temperature_logged_at and temperature_logged_at.strip():
            temp_token += f"@{temperature_logged_at.strip()}"
        parts.append(temp_token)
    structured = " ".join(parts)
    combined_notes = join_notes_and_pc(notes, pc_insight)
    if combined_notes:
        return f"{structured} | {combined_notes}" if structured else combined_notes
    return structured or None


def parse_comments(comments: str | None) -> ParsedComments:
    """Extract structured tokens; text after ' | ' is free_text (+ optional PC insight)."""
    if not comments or not comments.strip():
        return ParsedComments()

    text = comments.strip()
    free_text: str | None = None
    if " | " in text:
        token_part, free_text = text.split(" | ", 1)
        free_text = free_text.strip() or None
    else:
        token_part = text

    user_notes, pc_insight = split_notes_and_pc(free_text)
    parsed = ParsedComments(free_text=user_notes, pc_insight=pc_insight)
    free_parts: list[str] = []

    for part in TOKEN_SPLIT.split(token_part.strip()):
        part = part.strip()
        if not part:
            continue
        lower = part.lower()
        if lower.startswith("hlegs:"):
            value = part[6:].strip().lower()
            if value == "yes":
                parsed.heavy_legs = True
            elif value == "no":
                parsed.heavy_legs = False
        elif lower.startswith("bfast:"):
            parsed.food_breakfast = _sanitize_food_text(part[6:])
        elif lower.startswith("lunch:"):
            parsed.food_lunch = _sanitize_food_text(part[6:])
        elif lower.startswith("din:"):
            parsed.food_dinner = _sanitize_food_text(part[4:])
        elif lower.startswith("snack:"):
            parsed.food_snacks = _sanitize_food_text(part[6:])
        elif lower.startswith("xmeal:"):
            parsed.food_extra_meal = _sanitize_food_text(part[6:])
        elif lower.startswith("alc:"):
            parsed.alcohol = _to_float(part[4:].strip())
        elif lower.startswith("cafe:"):
            parsed.caffeine = _to_float(part[5:].strip())
        elif lower.startswith("cfx:"):
            value = part[4:].strip().lower()
            if value in CAFFEINE_EFFECT_VALUES:
                parsed.caffeine_effect = value
        elif lower.startswith("med:"):
            parsed.medication = part[4:].strip() or None
        elif lower.startswith("illness:"):
            parsed.illness = part[8:].strip() or None
        elif lower.startswith("temp:"):
            value = part[5:].strip()
            if "@" in value:
                temp_str, time_str = value.split("@", 1)
                parsed.temperature = _to_float(temp_str.strip())
                parsed.temperature_logged_at = time_str.strip() or None
            else:
                parsed.temperature = _to_float(value)
        else:
            free_parts.append(part)

    if free_parts:
        extra = " ".join(free_parts)
        parsed.free_text = " | ".join(filter(None, [extra, parsed.free_text]))
    return parsed


def _to_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None
