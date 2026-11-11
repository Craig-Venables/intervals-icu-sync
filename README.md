# intervals-icu-sync

Pull training and wellness data from [intervals.icu](https://intervals.icu) into a local SQLite database, Excel workbook, and optional HTML dashboard.

Credentials and downloaded data stay on your machine. They are gitignored and are not part of this repository.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your intervals.icu API key.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `INTERVALS_API_KEY` | Yes | API key from [intervals.icu settings](https://intervals.icu/settings) (Developer Settings). |
| `INTERVALS_ATHLETE_ID` | No | Athlete ID (for example `iXXXXXX`). Leave blank or `0` to use the athlete linked to the API key. |

Get the key from intervals.icu → Settings → Developer Settings. Do not commit `.env`.

## Usage

All commands write under `data/` (created automatically, gitignored).

### Daily sync (recommended)

Downloads recent wellness and activity records into SQLite, rebuilds daily metrics, and writes `data/fitness_data.xlsx` plus `data/charts/dashboard.html`.

```bash
python sync_daily.py
```

Options:

- `--backfill` — pull history from 2020 instead of the rolling 21-day window (use this the first time).
- `--skip-charts` — update the database and spreadsheet only.
- `--push-insights` — after sync, write short analysis notes back to wellness comments on intervals.icu.
- `--insight-days N` — number of recent days to push insights for (default: 7).

### JSON pull

Save a date range as JSON and CSV (no database):

```bash
python pull.py --oldest 2025-01-01 --newest 2025-12-31
```

`--out DIR` changes the output directory (default: `data/`). `--no-wellness` skips wellness records.

### Import an existing JSON pull into SQLite

```bash
python import_json.py --wellness data/wellness.json --activities data/activities.json
```

### Analyse one day

Fetches activity streams for a local calendar date and writes a report under `data/session_reports/`:

```bash
python analyse_day.py --date 2026-11-11
python analyse_day.py --date 2026-11-11 --download-fit
```

`--download-fit` also saves original FIT files under `data/fits/`.

### Charts only

```bash
python -m fitness_data
```

## Outputs

All of the following are local and gitignored:

- `data/fitness.db` — SQLite database
- `data/fitness_data.xlsx` — one row per day
- `data/charts/dashboard.html` — interactive charts
- `data/activities.json`, `data/wellness.json`, `data/activities.csv` — from `pull.py`
- `data/session_reports/` and `data/fits/` — from `analyse_day.py`

## Security

Never commit `.env`, API keys, athlete IDs with real values, or anything under `data/`.
