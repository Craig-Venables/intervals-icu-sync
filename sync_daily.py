#!/usr/bin/env python3
"""Daily pipeline: sync intervals.icu -> SQLite -> charts."""

from __future__ import annotations

import argparse
import sys

from fitness_data.aggregate import rebuild_daily_metrics
from fitness_data.charts import generate_charts
from fitness_data.export_excel import export_to_excel
from fitness_data.sync import sync


def run(*, force_backfill: bool = False, skip_charts: bool = False, push_insights: bool = False, insight_days: int = 7) -> None:
    print("Syncing from intervals.icu...")
    sync_result = sync(force_backfill=force_backfill)
    print(
        f"  {sync_result['wellness_rows']} wellness rows, "
        f"{sync_result['activity_rows']} activities "
        f"({sync_result['oldest']} to {sync_result['newest']})"
    )

    print("Rebuilding daily metrics...")
    metrics_count = rebuild_daily_metrics()
    print(f"  {metrics_count} daily metric rows")

    print("Exporting Excel...")
    excel_path = export_to_excel()
    print(f"  Spreadsheet saved -> {excel_path}")

    if skip_charts:
        print("Skipping chart generation.")
    else:
        print("Generating dashboard...")
        chart_path = generate_charts()
        print(f"  Dashboard saved -> {chart_path}")

    if push_insights:
        from fitness_data.pc_insights import push_recent_insights

        print(f"Pushing PC insights to intervals.icu (last {insight_days} days)...")
        count = push_recent_insights(days=insight_days)
        print(f"  {count} insight(s) pushed to wellness comments on intervals.icu")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync intervals.icu data, update database, and regenerate charts."
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Force full backfill from 2020 instead of rolling 21-day window",
    )
    parser.add_argument(
        "--skip-charts",
        action="store_true",
        help="Sync and aggregate only; do not regenerate dashboard",
    )
    parser.add_argument(
        "--push-insights",
        action="store_true",
        help="After sync, push short analysis notes to wellness comments on intervals.icu",
    )
    parser.add_argument(
        "--insight-days",
        type=int,
        default=7,
        help="Days of history to push insights for (default: 7)",
    )
    args = parser.parse_args(argv)

    try:
        run(
            force_backfill=args.backfill,
            skip_charts=args.skip_charts,
            push_insights=args.push_insights,
            insight_days=args.insight_days,
        )
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Daily sync failed: {exc}", file=sys.stderr)
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
