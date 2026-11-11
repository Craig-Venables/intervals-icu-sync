#!/usr/bin/env python3
"""Pull activities and wellness data from intervals.icu into local JSON files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

from fitness_data.config import DATA_DIR, Settings
from fitness_data.intervals_client import IntervalsClient


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def pull(
    *,
    oldest: date,
    newest: date,
    out_dir: Path,
    include_wellness: bool,
) -> None:
    settings = Settings.from_env()
    client = IntervalsClient(settings)

    print("Verifying API connection...")
    athlete = client.get_athlete()
    athlete_name = athlete.get("name") or athlete.get("id") or settings.athlete_id
    print(f"Connected as: {athlete_name}")

    print(f"Fetching activities from {oldest} to {newest}...")
    activities = client.list_activities(oldest=oldest, newest=newest)
    activities_path = out_dir / "activities.json"
    _write_json(activities_path, activities)
    print(f"Saved {len(activities)} activities -> {activities_path}")

    csv_path = out_dir / "activities.csv"
    csv_path.write_text(
        client.download_activities_csv(oldest=oldest, newest=newest),
        encoding="utf-8",
    )
    print(f"Saved activities CSV -> {csv_path}")

    if include_wellness:
        print(f"Fetching wellness from {oldest} to {newest}...")
        wellness = client.list_wellness(oldest=oldest, newest=newest)
        wellness_path = out_dir / "wellness.json"
        _write_json(wellness_path, wellness)
        print(f"Saved {len(wellness)} wellness records -> {wellness_path}")

    meta = {
        "athlete_id": settings.athlete_id,
        "athlete_name": athlete_name,
        "oldest": oldest.isoformat(),
        "newest": newest.isoformat(),
        "activity_count": len(activities),
    }
    _write_json(out_dir / "pull_metadata.json", meta)
    print("Done.")


def main(argv: list[str] | None = None) -> int:
    today = date.today()
    default_oldest = today - timedelta(days=365)

    parser = argparse.ArgumentParser(
        description="Pull Garmin/training data from intervals.icu (stored locally, not committed)."
    )
    parser.add_argument(
        "--oldest",
        type=_parse_date,
        default=default_oldest,
        help=f"Start date YYYY-MM-DD (default: {default_oldest})",
    )
    parser.add_argument(
        "--newest",
        type=_parse_date,
        default=today,
        help=f"End date YYYY-MM-DD (default: {today})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DATA_DIR,
        help=f"Output directory (default: {DATA_DIR})",
    )
    parser.add_argument(
        "--no-wellness",
        action="store_true",
        help="Skip wellness data (sleep, HRV, fatigue, etc.)",
    )
    args = parser.parse_args(argv)

    if args.oldest > args.newest:
        print("Error: --oldest must be on or before --newest", file=sys.stderr)
        return 1

    try:
        pull(
            oldest=args.oldest,
            newest=args.newest,
            out_dir=args.out,
            include_wellness=not args.no_wellness,
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Pull failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
