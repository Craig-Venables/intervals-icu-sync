"""SQLite storage for wellness, activities, and daily metrics."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fitness_data.config import DB_PATH

WELLNESS_COLUMNS = [
    ("soreness", "REAL"),
    ("mood", "REAL"),
    ("fatigue", "REAL"),
    ("motivation", "REAL"),
    ("stress", "REAL"),
    ("injury", "REAL"),
    ("hydration", "REAL"),
    ("comments", "TEXT"),
]

DAILY_METRICS_COLUMNS = [
    ("soreness", "REAL"),
    ("heavy_legs", "REAL"),
    ("food_breakfast", "TEXT"),
    ("food_lunch", "TEXT"),
    ("food_dinner", "TEXT"),
    ("food_snacks", "TEXT"),
    ("food_extra_meal", "TEXT"),
    ("mood", "REAL"),
    ("energy", "REAL"),
    ("fatigue", "REAL"),
    ("stress", "REAL"),
    ("hydration_liters", "REAL"),
    ("alcohol", "REAL"),
    ("caffeine", "REAL"),
    ("caffeine_effect", "TEXT"),
    ("medication", "TEXT"),
    ("illness", "TEXT"),
    ("notes", "TEXT"),
    ("body_temp_c", "REAL"),
    ("body_temp_logged_at", "TEXT"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wellness (
    date TEXT PRIMARY KEY,
    resting_hr REAL,
    hrv REAL,
    hrv_sdnn REAL,
    sleep_secs REAL,
    sleep_score REAL,
    sleep_quality REAL,
    steps REAL,
    kcal_consumed REAL,
    vo2max REAL,
    ctl REAL,
    atl REAL,
    ramp_rate REAL,
    soreness REAL,
    mood REAL,
    fatigue REAL,
    motivation REAL,
    stress REAL,
    injury REAL,
    hydration REAL,
    comments TEXT,
    updated_at TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS activities (
    id TEXT PRIMARY KEY,
    start_date_local TEXT NOT NULL,
    activity_date TEXT NOT NULL,
    name TEXT,
    type TEXT,
    icu_training_load REAL,
    calories REAL,
    moving_time REAL,
    distance REAL,
    icu_atl REAL,
    icu_ctl REAL,
    updated_at TEXT,
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(activity_date);

CREATE TABLE IF NOT EXISTS daily_metrics (
    date TEXT PRIMARY KEY,
    resting_hr REAL,
    hrv REAL,
    sleep_hours REAL,
    sleep_score REAL,
    steps REAL,
    calories REAL,
    vo2max REAL,
    daily_tss REAL,
    atl REAL,
    ctl REAL,
    workout_count INTEGER,
    soreness REAL,
    heavy_legs REAL,
    food_breakfast TEXT,
    food_lunch TEXT,
    food_dinner TEXT,
    food_snacks TEXT,
    food_extra_meal TEXT,
    mood REAL,
    energy REAL,
    fatigue REAL,
    stress REAL,
    hydration_liters REAL,
    alcohol REAL,
    caffeine REAL,
    medication TEXT,
    illness TEXT,
    notes TEXT,
    body_temp_c REAL,
    body_temp_logged_at TEXT
);

CREATE TABLE IF NOT EXISTS user_journal (
    date TEXT PRIMARY KEY,
    soreness INTEGER,
    mood INTEGER,
    energy INTEGER,
    alcohol REAL,
    caffeine REAL,
    hydration REAL,
    illness TEXT,
    medication TEXT,
    notes TEXT
);
"""


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Path | None = None) -> None:
    with db_session(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate_columns(conn, "wellness", WELLNESS_COLUMNS)
        _migrate_columns(conn, "daily_metrics", DAILY_METRICS_COLUMNS)


def _migrate_columns(
    conn: sqlite3.Connection,
    table: str,
    columns: list[tuple[str, str]],
) -> None:
    existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    for name, col_type in columns:
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_wellness(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> int:
    sql = """
        INSERT INTO wellness (
            date, resting_hr, hrv, hrv_sdnn, sleep_secs, sleep_score, sleep_quality,
            steps, kcal_consumed, vo2max, ctl, atl, ramp_rate,
            soreness, mood, fatigue, motivation, stress, injury, hydration, comments,
            updated_at, raw_json
        ) VALUES (
            :date, :resting_hr, :hrv, :hrv_sdnn, :sleep_secs, :sleep_score, :sleep_quality,
            :steps, :kcal_consumed, :vo2max, :ctl, :atl, :ramp_rate,
            :soreness, :mood, :fatigue, :motivation, :stress, :injury, :hydration, :comments,
            :updated_at, :raw_json
        )
        ON CONFLICT(date) DO UPDATE SET
            resting_hr = excluded.resting_hr,
            hrv = excluded.hrv,
            hrv_sdnn = excluded.hrv_sdnn,
            sleep_secs = excluded.sleep_secs,
            sleep_score = excluded.sleep_score,
            sleep_quality = excluded.sleep_quality,
            steps = excluded.steps,
            kcal_consumed = excluded.kcal_consumed,
            vo2max = excluded.vo2max,
            ctl = excluded.ctl,
            atl = excluded.atl,
            ramp_rate = excluded.ramp_rate,
            soreness = excluded.soreness,
            mood = excluded.mood,
            fatigue = excluded.fatigue,
            motivation = excluded.motivation,
            stress = excluded.stress,
            injury = excluded.injury,
            hydration = excluded.hydration,
            comments = excluded.comments,
            updated_at = excluded.updated_at,
            raw_json = excluded.raw_json
    """
    rows = [_wellness_row(record) for record in records]
    conn.executemany(sql, rows)
    return len(rows)


def _wellness_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "date": record["id"],
        "resting_hr": record.get("restingHR"),
        "hrv": record.get("hrv") or record.get("hrvSDNN"),
        "hrv_sdnn": record.get("hrvSDNN"),
        "sleep_secs": record.get("sleepSecs"),
        "sleep_score": record.get("sleepScore"),
        "sleep_quality": record.get("sleepQuality"),
        "steps": record.get("steps"),
        "kcal_consumed": record.get("kcalConsumed"),
        "vo2max": record.get("vo2max"),
        "ctl": record.get("ctl"),
        "atl": record.get("atl"),
        "ramp_rate": record.get("rampRate"),
        "soreness": record.get("soreness"),
        "mood": record.get("mood"),
        "fatigue": record.get("fatigue"),
        "motivation": record.get("motivation"),
        "stress": record.get("stress"),
        "injury": record.get("injury"),
        "hydration": record.get("hydration") or record.get("hydrationVolume"),
        "comments": record.get("comments"),
        "updated_at": record.get("updated") or _utc_now(),
        "raw_json": json.dumps(record, default=str),
    }


def upsert_activities(conn: sqlite3.Connection, records: list[dict[str, Any]]) -> int:
    sql = """
        INSERT INTO activities (
            id, start_date_local, activity_date, name, type,
            icu_training_load, calories, moving_time, distance,
            icu_atl, icu_ctl, updated_at, raw_json
        ) VALUES (
            :id, :start_date_local, :activity_date, :name, :type,
            :icu_training_load, :calories, :moving_time, :distance,
            :icu_atl, :icu_ctl, :updated_at, :raw_json
        )
        ON CONFLICT(id) DO UPDATE SET
            start_date_local = excluded.start_date_local,
            activity_date = excluded.activity_date,
            name = excluded.name,
            type = excluded.type,
            icu_training_load = excluded.icu_training_load,
            calories = excluded.calories,
            moving_time = excluded.moving_time,
            distance = excluded.distance,
            icu_atl = excluded.icu_atl,
            icu_ctl = excluded.icu_ctl,
            updated_at = excluded.updated_at,
            raw_json = excluded.raw_json
    """
    rows = [_activity_row(record) for record in records]
    conn.executemany(sql, rows)
    return len(rows)


def _activity_row(record: dict[str, Any]) -> dict[str, Any]:
    start_local = record.get("start_date_local") or ""
    activity_date = start_local[:10] if start_local else ""
    return {
        "id": str(record["id"]),
        "start_date_local": start_local,
        "activity_date": activity_date,
        "name": record.get("name"),
        "type": record.get("type"),
        "icu_training_load": record.get("icu_training_load"),
        "calories": record.get("calories"),
        "moving_time": record.get("moving_time"),
        "distance": record.get("distance"),
        "icu_atl": record.get("icu_atl"),
        "icu_ctl": record.get("icu_ctl"),
        "updated_at": record.get("icu_sync_date") or _utc_now(),
        "raw_json": json.dumps(record, default=str),
    }


def upsert_daily_metrics(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> int:
    sql = """
        INSERT INTO daily_metrics (
            date, resting_hr, hrv, sleep_hours, sleep_score, steps,
            calories, vo2max, daily_tss, atl, ctl, workout_count,
            soreness, heavy_legs, food_breakfast, food_lunch, food_dinner, food_snacks,
            food_extra_meal, mood, energy, fatigue, stress, hydration_liters,
            alcohol, caffeine, caffeine_effect, medication, illness, notes,
            body_temp_c, body_temp_logged_at
        ) VALUES (
            :date, :resting_hr, :hrv, :sleep_hours, :sleep_score, :steps,
            :calories, :vo2max, :daily_tss, :atl, :ctl, :workout_count,
            :soreness, :heavy_legs, :food_breakfast, :food_lunch, :food_dinner,
            :food_snacks, :food_extra_meal, :mood, :energy, :fatigue, :stress,
            :hydration_liters,
            :alcohol, :caffeine, :caffeine_effect, :medication, :illness, :notes,
            :body_temp_c, :body_temp_logged_at
        )
        ON CONFLICT(date) DO UPDATE SET
            resting_hr = excluded.resting_hr,
            hrv = excluded.hrv,
            sleep_hours = excluded.sleep_hours,
            sleep_score = excluded.sleep_score,
            steps = excluded.steps,
            calories = excluded.calories,
            vo2max = excluded.vo2max,
            daily_tss = excluded.daily_tss,
            atl = excluded.atl,
            ctl = excluded.ctl,
            workout_count = excluded.workout_count,
            soreness = excluded.soreness,
            heavy_legs = excluded.heavy_legs,
            food_breakfast = excluded.food_breakfast,
            food_lunch = excluded.food_lunch,
            food_dinner = excluded.food_dinner,
            food_snacks = excluded.food_snacks,
            food_extra_meal = excluded.food_extra_meal,
            mood = excluded.mood,
            energy = excluded.energy,
            fatigue = excluded.fatigue,
            stress = excluded.stress,
            hydration_liters = excluded.hydration_liters,
            alcohol = excluded.alcohol,
            caffeine = excluded.caffeine,
            caffeine_effect = excluded.caffeine_effect,
            medication = excluded.medication,
            illness = excluded.illness,
            notes = excluded.notes,
            body_temp_c = excluded.body_temp_c,
            body_temp_logged_at = excluded.body_temp_logged_at
    """
    conn.executemany(sql, rows)
    return len(rows)
