#!/usr/bin/env python3
"""One-time import of existing JSON pulls into SQLite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fitness_data.aggregate import rebuild_daily_metrics
from fitness_data.config import DATA_DIR
from fitness_data.db import db_session, init_db, set_meta, upsert_activities, upsert_wellness


def import_json(
    *,
    wellness_path: Path,
    activities_path: Path,
) -> dict[str, int]:
    init_db()

    wellness = json.loads(wellness_path.read_text(encoding="utf-8"))
    activities = json.loads(activities_path.read_text(encoding="utf-8"))

    with db_session() as conn:
        wellness_count = upsert_wellness(conn, wellness)
        activity_count = upsert_activities(conn, activities)
        set_meta(conn, "backfill_complete", "true")
        set_meta(conn, "last_sync_at", wellness[-1]["id"] if wellness else "")
        metrics_count = rebuild_daily_metrics(conn)

    return {
        "wellness_rows": wellness_count,
        "activity_rows": activity_count,
        "daily_metrics_rows": metrics_count,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import existing JSON data into SQLite.")
    parser.add_argument(
        "--wellness",
        type=Path,
        default=DATA_DIR / "wellness.json",
        help="Path to wellness.json",
    )
    parser.add_argument(
        "--activities",
        type=Path,
        default=DATA_DIR / "activities.json",
        help="Path to activities.json",
    )
    args = parser.parse_args(argv)

    if not args.wellness.exists():
        print(f"Missing wellness file: {args.wellness}", file=sys.stderr)
        return 1
    if not args.activities.exists():
        print(f"Missing activities file: {args.activities}", file=sys.stderr)
        return 1

    try:
        result = import_json(wellness_path=args.wellness, activities_path=args.activities)
    except Exception as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Imported {result['wellness_rows']} wellness rows, "
        f"{result['activity_rows']} activities, "
        f"{result['daily_metrics_rows']} daily metrics."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
