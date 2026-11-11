"""Build daily_metrics from wellness and activity tables."""

from __future__ import annotations

import sqlite3

from fitness_data.comments_parser import parse_comments
from fitness_data.db import db_session, init_db, upsert_daily_metrics


def rebuild_daily_metrics(conn: sqlite3.Connection | None = None) -> int:
    sql = """
        SELECT
            w.date AS date,
            w.resting_hr,
            w.hrv,
            CASE WHEN w.sleep_secs IS NOT NULL THEN w.sleep_secs / 3600.0 END AS sleep_hours,
            w.sleep_score,
            w.steps,
            COALESCE(w.kcal_consumed, a.activity_calories) AS calories,
            w.vo2max,
            COALESCE(a.daily_tss, 0) AS daily_tss,
            w.atl,
            w.ctl,
            COALESCE(a.workout_count, 0) AS workout_count,
            w.soreness,
            w.mood,
            w.motivation AS energy,
            w.fatigue,
            w.stress,
            w.hydration AS hydration_liters,
            w.comments
        FROM wellness w
        LEFT JOIN (
            SELECT
                activity_date,
                SUM(COALESCE(icu_training_load, 0)) AS daily_tss,
                SUM(COALESCE(calories, 0)) AS activity_calories,
                COUNT(*) AS workout_count
            FROM activities
            GROUP BY activity_date
        ) a ON a.activity_date = w.date
        ORDER BY w.date
    """
    if conn is None:
        init_db()
        with db_session() as session:
            return _execute_rebuild(session, sql)

    return _execute_rebuild(conn, sql)


def _execute_rebuild(conn: sqlite3.Connection, sql: str) -> int:
    rows = [dict(row) for row in conn.execute(sql).fetchall()]
    enriched = [_enrich_row(row) for row in rows]
    if not enriched:
        return 0
    return upsert_daily_metrics(conn, enriched)


def _enrich_row(row: dict) -> dict:
    parsed = parse_comments(row.pop("comments", None))
    row["heavy_legs"] = (
        1.0 if parsed.heavy_legs is True else 0.0 if parsed.heavy_legs is False else None
    )
    row["food_breakfast"] = parsed.food_breakfast
    row["food_lunch"] = parsed.food_lunch
    row["food_dinner"] = parsed.food_dinner
    row["food_snacks"] = parsed.food_snacks
    row["food_extra_meal"] = parsed.food_extra_meal
    row["alcohol"] = parsed.alcohol
    row["caffeine"] = parsed.caffeine
    row["caffeine_effect"] = parsed.caffeine_effect
    row["medication"] = parsed.medication
    row["illness"] = parsed.illness
    row["notes"] = parsed.free_text
    row["body_temp_c"] = parsed.temperature
    row["body_temp_logged_at"] = parsed.temperature_logged_at
    return row
