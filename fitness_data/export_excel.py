"""Export SQLite fitness data to a spreadsheet (one row per day)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from fitness_data.config import DB_PATH, EXCEL_PATH

DAILY_EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("date", "Date"),
    ("resting_hr", "Resting HR (bpm)"),
    ("hrv", "HRV"),
    ("sleep_hours", "Sleep (hours)"),
    ("sleep_score", "Sleep score"),
    ("steps", "Steps"),
    ("calories", "Calories"),
    ("vo2max", "VO2 max"),
    ("daily_tss", "Daily TSS"),
    ("atl", "ATL"),
    ("ctl", "CTL"),
    ("workout_count", "Workouts"),
    ("body_temp_c", "Body temp (°C)"),
    ("body_temp_logged_at", "Temp logged at"),
    ("soreness", "Soreness (1-10)"),
    ("heavy_legs", "Heavy legs (1=yes, 0=no)"),
    ("food_breakfast", "Breakfast"),
    ("food_lunch", "Lunch"),
    ("food_dinner", "Dinner"),
    ("food_snacks", "Snacks"),
    ("food_extra_meal", "Extra meal (training)"),
    ("mood", "Mood (1-10)"),
    ("energy", "Energy (1-10)"),
    ("fatigue", "Fatigue (1-10)"),
    ("stress", "Stress (1-10)"),
    ("caffeine", "Caffeine (mg)"),
    ("caffeine_effect", "Caffeine effect"),
    ("hydration_liters", "Hydration (L)"),
    ("alcohol", "Alcohol (units)"),
    ("medication", "Supplements"),
    ("illness", "Illness"),
    ("notes", "Notes"),
]

ACTIVITY_EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("activity_date", "Date"),
    ("name", "Activity"),
    ("type", "Type"),
    ("icu_training_load", "TSS"),
    ("calories", "Calories"),
    ("moving_time", "Moving time (sec)"),
    ("distance", "Distance (m)"),
]


def _load_table(conn: sqlite3.Connection, table: str) -> pd.DataFrame:
    return pd.read_sql_query(f"SELECT * FROM {table}", conn)


def _prepare_sheet(df: pd.DataFrame, columns: list[tuple[str, str]]) -> pd.DataFrame:
    out = pd.DataFrame()
    for source, label in columns:
        if source in df.columns:
            out[label] = df[source]
        else:
            out[label] = None
    return out


def export_to_excel(
    db_path: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    """Write daily metrics + activities to an Excel workbook."""
    db = db_path or DB_PATH
    out = output_path or EXCEL_PATH
    out.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db)
    try:
        daily_raw = _load_table(conn, "daily_metrics")
        activities_raw = _load_table(conn, "activities")
    finally:
        conn.close()

    daily = _prepare_sheet(daily_raw, DAILY_EXPORT_COLUMNS)
    if not daily.empty and "Date" in daily.columns:
        daily["Date"] = pd.to_datetime(daily["Date"], errors="coerce")
        daily = daily.sort_values("Date")

    activities = _prepare_sheet(activities_raw, ACTIVITY_EXPORT_COLUMNS)
    if not activities.empty and "Date" in activities.columns:
        activities["Date"] = pd.to_datetime(activities["Date"], errors="coerce")
        activities = activities.sort_values(["Date", "Activity"])

    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        daily.to_excel(writer, sheet_name="Daily", index=False)
        activities.to_excel(writer, sheet_name="Activities", index=False)

        for sheet_name in ("Daily", "Activities"):
            ws = writer.sheets[sheet_name]
            ws.freeze_panes = "A2"
            for column in ws.columns:
                max_len = 0
                col_letter = column[0].column_letter
                for cell in column:
                    if cell.value is not None:
                        max_len = max(max_len, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 40)

    return out


def main() -> int:
    path = export_to_excel()
    print(f"Excel export saved -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
