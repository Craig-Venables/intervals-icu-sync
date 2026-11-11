#!/usr/bin/env python3
"""Analyse a day's activities from intervals.icu streams (pace/HR drift/power)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fitness_data.config import DATA_DIR, Settings
from fitness_data.intervals_client import IntervalsClient
from fitness_data.session_analysis import analyse_activity_from_streams, format_report_text


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _activity_local_date(activity: dict[str, Any]) -> date | None:
    for key in ("start_date_local", "start_date", "date"):
        raw = activity.get(key)
        if not raw:
            continue
        text = str(raw)
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            continue
    return None


def _load_activities(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return []


def _ensure_activities_for_day(
    client: IntervalsClient,
    day: date,
    activities_path: Path,
) -> list[dict[str, Any]]:
    activities = _load_activities(activities_path)
    day_acts = [a for a in activities if _activity_local_date(a) == day]
    if day_acts:
        return day_acts

    # Pull a small window around the day and merge/replace local cache
    oldest = day - timedelta(days=1)
    newest = day + timedelta(days=1)
    print(f"No local activities for {day}; pulling {oldest}..{newest}...", file=sys.stderr)
    fetched = client.list_activities(oldest=oldest, newest=newest)
    # Merge by id into existing cache
    by_id = {str(a.get("id")): a for a in activities if a.get("id") is not None}
    for a in fetched:
        if a.get("id") is not None:
            by_id[str(a["id"])] = a
    merged = list(by_id.values())
    activities_path.parent.mkdir(parents=True, exist_ok=True)
    activities_path.write_text(json.dumps(merged, indent=2, default=str), encoding="utf-8")
    return [a for a in merged if _activity_local_date(a) == day]


def analyse_day(
    *,
    day: date,
    download_fit: bool,
    data_dir: Path,
) -> list[dict[str, Any]]:
    settings = Settings.from_env()
    client = IntervalsClient(settings)

    activities_path = data_dir / "activities.json"
    day_acts = _ensure_activities_for_day(client, day, activities_path)
    # Chronological
    day_acts = sorted(
        day_acts,
        key=lambda a: str(a.get("start_date_local") or a.get("start_date") or ""),
    )

    fits_dir = data_dir / "fits"
    reports_dir = data_dir / "session_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    reports: list[dict[str, Any]] = []
    if not day_acts:
        print(f"No activities found for {day.isoformat()}")
        out = {
            "date": day.isoformat(),
            "athlete_id": settings.athlete_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "activities": [],
        }
        (reports_dir / f"{day.isoformat()}.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8"
        )
        return []

    for activity in day_acts:
        aid = activity.get("id")
        name = activity.get("name") or aid
        print(f"\n=== {name} ({aid}) ===")
        try:
            streams = client.get_streams(aid)
        except Exception as exc:  # noqa: BLE001 — surface per-activity failures
            print(f"Failed to fetch streams: {exc}", file=sys.stderr)
            continue

        report = analyse_activity_from_streams(activity, streams)
        text = format_report_text(report)
        print(text)
        report["report_text"] = text

        if download_fit:
            dest = fits_dir / f"{aid}.fit"
            try:
                path = client.download_fit(aid, dest)
                report["fit_path"] = str(path)
                print(f"(saved FIT -> {path})")
            except Exception as exc:  # noqa: BLE001
                print(f"FIT download failed: {exc}", file=sys.stderr)
                report["fit_path"] = None
                report["fit_error"] = str(exc)

        reports.append(report)

    payload = {
        "date": day.isoformat(),
        "athlete_id": settings.athlete_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "activities": reports,
    }
    out_path = reports_dir / f"{day.isoformat()}.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path} ({len(reports)} activities)")
    return reports


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Analyse a day's intervals.icu activities (streams: pace, HR drift, power)."
    )
    parser.add_argument(
        "--date",
        type=_parse_date,
        default=date.today(),
        help="Local calendar date YYYY-MM-DD (default: today)",
    )
    parser.add_argument(
        "--download-fit",
        action="store_true",
        help="Also archive original FIT under data/fits/{activity_id}.fit",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Data directory (default: data/)",
    )
    args = parser.parse_args(argv)

    analyse_day(day=args.date, download_fit=args.download_fit, data_dir=args.data_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
