"""Incremental sync from intervals.icu into SQLite."""

from __future__ import annotations

from datetime import date, timedelta

from fitness_data.config import Settings
from fitness_data.db import (
    db_session,
    get_meta,
    init_db,
    set_meta,
    upsert_activities,
    upsert_wellness,
)
from fitness_data.intervals_client import IntervalsClient

BACKFILL_START = date(2020, 1, 1)
ROLLING_DAYS = 21


def sync(
    *,
    settings: Settings | None = None,
    force_backfill: bool = False,
) -> dict[str, int | str]:
    settings = settings or Settings.from_env()
    init_db()
    client = IntervalsClient(settings)
    today = date.today()

    with db_session() as conn:
        backfill_done = get_meta(conn, "backfill_complete", "false") == "true"
        if force_backfill or not backfill_done:
            oldest = BACKFILL_START
        else:
            oldest = today - timedelta(days=ROLLING_DAYS)

        wellness = client.list_wellness(oldest=oldest, newest=today)
        activities = client.list_activities(oldest=oldest, newest=today)

        wellness_count = upsert_wellness(conn, wellness)
        activity_count = upsert_activities(conn, activities)

        set_meta(conn, "last_sync_at", today.isoformat())
        set_meta(conn, "last_sync_oldest", oldest.isoformat())
        if not backfill_done:
            set_meta(conn, "backfill_complete", "true")

    return {
        "oldest": oldest.isoformat(),
        "newest": today.isoformat(),
        "wellness_rows": wellness_count,
        "activity_rows": activity_count,
    }
