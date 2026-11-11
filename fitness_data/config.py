"""Load configuration from environment variables (never commit secrets)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "fitness.db"
CHARTS_DIR = DATA_DIR / "charts"
EXCEL_PATH = DATA_DIR / "fitness_data.xlsx"


@dataclass(frozen=True)
class Settings:
    api_key: str
    athlete_id: str
    base_url: str = "https://intervals.icu/api/v1"

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(PROJECT_ROOT / ".env")

        api_key = os.getenv("INTERVALS_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "INTERVALS_API_KEY is not set. Copy .env.example to .env and add "
                "your API key from https://intervals.icu/settings"
            )

        athlete_id = os.getenv("INTERVALS_ATHLETE_ID", "0").strip() or "0"
        return cls(api_key=api_key, athlete_id=athlete_id)

