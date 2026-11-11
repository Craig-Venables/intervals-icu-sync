"""Push dashboard insights back onto wellness records on intervals.icu."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from fitness_data.comments_parser import build_comments, parse_comments
from fitness_data.config import DB_PATH
from fitness_data.intervals_client import IntervalsClient
from fitness_data.wellness_merge import merge_wellness_entry


def push_insight(day: date, message: str, *, client: IntervalsClient | None = None) -> None:
    """Write a read-only insight onto a day's wellness record on intervals.icu."""
    api = client or IntervalsClient()
    existing = api.get_wellness(day) or {}
    parsed = parse_comments(existing.get("comments"))
    payload = merge_wellness_entry(
        existing,
        notes=parsed.free_text,
        pc_insight=message.strip(),
    )
    if not payload:
        payload = {"comments": build_comments(pc_insight=message.strip())}
    api.update_wellness(day, payload)


def generate_insight(conn: sqlite3.Connection, day: date) -> str | None:
    """Build a short insight string from daily_metrics for one day."""
    row = conn.execute(
        """
        SELECT date, atl, ctl, hrv, resting_hr, fatigue, stress, daily_tss, sleep_hours
        FROM daily_metrics
        WHERE date = ?
        """,
        (day.isoformat(),),
    ).fetchone()
    if row is None:
        return None

    parts: list[str] = []
    if row["atl"] is not None and row["ctl"] is not None:
        ratio = row["atl"] / row["ctl"] if row["ctl"] else None
        if ratio is not None and ratio > 1.3:
            parts.append(f"ATL/CTL {ratio:.2f} — fatigue load elevated")
        elif row["atl"] is not None:
            parts.append(f"ATL {row['atl']:.0f}, CTL {row['ctl']:.0f}")

    if row["hrv"] is not None:
        avg_row = conn.execute(
            """
            SELECT AVG(hrv) AS avg_hrv
            FROM daily_metrics
            WHERE date <= ? AND date >= ? AND hrv IS NOT NULL
            """,
            (day.isoformat(), (day - timedelta(days=13)).isoformat()),
        ).fetchone()
        if avg_row and avg_row["avg_hrv"]:
            delta_pct = ((row["hrv"] - avg_row["avg_hrv"]) / avg_row["avg_hrv"]) * 100
            if delta_pct <= -10:
                parts.append(f"HRV {row['hrv']:.0f} ({delta_pct:+.0f}% vs 14d avg)")
            elif delta_pct >= 10:
                parts.append(f"HRV {row['hrv']:.0f} ({delta_pct:+.0f}% vs 14d avg — good recovery)")

    if row["fatigue"] is not None and row["fatigue"] >= 7:
        parts.append(f"Logged fatigue {row['fatigue']:.0f}/10")
    if row["stress"] is not None and row["stress"] >= 7:
        parts.append(f"Logged stress {row['stress']:.0f}/10")

    if not parts:
        return None
    return ". ".join(parts) + "."


def push_recent_insights(
    days: int = 7,
    *,
    db_path=DB_PATH,
    client: IntervalsClient | None = None,
) -> int:
    """Generate and push insights for the last N days that have metrics."""
    api = client or IntervalsClient()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    pushed = 0
    try:
        today = date.today()
        for offset in range(1, days + 1):
            day = today - timedelta(days=offset)
            insight = generate_insight(conn, day)
            if insight:
                push_insight(day, insight, client=api)
                pushed += 1
    finally:
        conn.close()
    return pushed
