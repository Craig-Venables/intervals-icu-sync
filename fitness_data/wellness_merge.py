"""Merge wellness log updates into existing day records."""

from __future__ import annotations

from fitness_data.comments_parser import (
    ParsedComments,
    build_comments,
    merge_food_field,
    parse_comments,
)


def split_med_list(value: str | None) -> list[str]:
    if not value or not value.strip():
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def merge_medications(existing: str | None, *new_items: str | None) -> str | None:
    seen: dict[str, str] = {}
    for item in split_med_list(existing):
        seen[item.lower()] = item
    for raw in new_items:
        if not raw:
            continue
        for item in split_med_list(raw):
            seen[item.lower()] = item
    if not seen:
        return None
    return ", ".join(seen.values())


def merge_notes(existing: str | None, new_note: str | None) -> str | None:
    if not new_note or not new_note.strip():
        return existing.strip() if existing else None
    note = new_note.strip()
    if not existing or not existing.strip():
        return note
    if note.lower() in existing.lower():
        return existing.strip()
    return f"{existing.strip()} | {note}"


def merge_optional_int(existing: int | None, new: int | None) -> int | None:
    if new is not None and 1 <= new <= 10:
        return new
    return existing


def merge_additive(existing: float | None, to_add: float | None) -> float | None:
    if to_add is not None and to_add > 0:
        return (existing or 0.0) + to_add
    return existing


def merge_replace(existing: float | None, new: float | None) -> float | None:
    if new is not None:
        return new
    return existing


def merge_text(existing: str | None, new: str | None) -> str | None:
    if new and new.strip():
        return new.strip()
    return existing.strip() if existing else None


def merge_heavy_legs(existing: bool | None, new: bool | None) -> bool | None:
    if new is not None:
        return new
    return existing


def merge_wellness_entry(
    existing_record: dict | None,
    *,
    soreness: int | None = None,
    heavy_legs: bool | None = None,
    food_breakfast: str | None = None,
    food_lunch: str | None = None,
    food_dinner: str | None = None,
    food_snacks: str | None = None,
    food_extra_meal: str | None = None,
    mood: int | None = None,
    energy: int | None = None,
    fatigue: int | None = None,
    stress: int | None = None,
    hydration: float | None = None,
    hydration_add: float | None = None,
    alcohol: float | None = None,
    alcohol_add: float | None = None,
    caffeine: float | None = None,
    caffeine_add: float | None = None,
    caffeine_effect: str | None = None,
    medication: str | None = None,
    medication_add: str | None = None,
    illness: str | None = None,
    temperature: float | None = None,
    temperature_logged_at: str | None = None,
    notes: str | None = None,
    notes_add: str | None = None,
    pc_insight: str | None = None,
) -> dict:
    """Build merged wellness PUT payload from existing intervals.icu record + updates."""
    existing = existing_record or {}
    parsed = parse_comments(existing.get("comments"))

    merged_meds = merge_medications(parsed.medication, medication, medication_add)
    merged_alcohol = merge_additive(parsed.alcohol, alcohol_add)
    if alcohol is not None:
        merged_alcohol = alcohol
    merged_caffeine = merge_additive(parsed.caffeine, caffeine_add)
    if caffeine is not None:
        merged_caffeine = caffeine

    existing_hydration = existing.get("hydration") or existing.get("hydrationVolume")
    merged_hydration = merge_additive(
        float(existing_hydration) if existing_hydration is not None else None,
        hydration_add,
    )
    if hydration is not None:
        merged_hydration = hydration

    merged_temperature = merge_replace(parsed.temperature, temperature)
    if temperature is not None and temperature != parsed.temperature:
        merged_temperature_at = temperature_logged_at
    else:
        merged_temperature_at = parsed.temperature_logged_at

    comments = build_comments(
        heavy_legs=merge_heavy_legs(parsed.heavy_legs, heavy_legs),
        food_breakfast=merge_food_field(parsed.food_breakfast, food_breakfast),
        food_lunch=merge_food_field(parsed.food_lunch, food_lunch),
        food_dinner=merge_food_field(parsed.food_dinner, food_dinner),
        food_snacks=merge_food_field(parsed.food_snacks, food_snacks),
        food_extra_meal=merge_food_field(parsed.food_extra_meal, food_extra_meal),
        alcohol=merged_alcohol,
        caffeine=merged_caffeine,
        caffeine_effect=merge_text(parsed.caffeine_effect, caffeine_effect),
        medication=merged_meds,
        illness=merge_text(parsed.illness, illness),
        temperature=merged_temperature,
        temperature_logged_at=merged_temperature_at,
        notes=merge_notes(parsed.free_text, notes_add or notes),
        pc_insight=pc_insight if pc_insight is not None else parsed.pc_insight,
    )

    payload: dict = {}

    field_map = {
        "soreness": merge_optional_int(existing.get("soreness"), soreness),
        "mood": merge_optional_int(existing.get("mood"), mood),
        "motivation": merge_optional_int(existing.get("motivation"), energy),
        "fatigue": merge_optional_int(existing.get("fatigue"), fatigue),
        "stress": merge_optional_int(existing.get("stress"), stress),
    }
    for key, value in field_map.items():
        if value is not None:
            payload[key] = value
    if merged_hydration is not None:
        payload["hydration"] = merged_hydration
    if comments:
        payload["comments"] = comments

    return payload
