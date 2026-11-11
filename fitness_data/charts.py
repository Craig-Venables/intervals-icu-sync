"""Generate interactive fatigue dashboard charts."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from fitness_data.config import CHARTS_DIR, DB_PATH

PERIODS: dict[str, int] = {
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "60d": 60,
}

METRICS: list[tuple[str, str]] = [
    ("resting_hr", "Resting HR (bpm)"),
    ("hrv", "HRV"),
    ("sleep_hours", "Sleep (hours)"),
    ("sleep_score", "Sleep Score"),
    ("steps", "Steps"),
    ("calories", "Calories"),
    ("vo2max", "VO2 Max"),
    ("daily_tss", "Daily TSS"),
    ("atl", "ATL (fatigue)"),
    ("ctl", "CTL (fitness)"),
    ("soreness", "Soreness (1-10)"),
    ("heavy_legs", "Heavy legs"),
    ("mood", "Mood (1-10)"),
    ("energy", "Energy (1-10)"),
    ("fatigue", "Fatigue (1-10)"),
    ("stress", "Stress (1-10)"),
    ("caffeine", "Caffeine"),
    ("hydration_liters", "Hydration (L)"),
    ("alcohol", "Alcohol (units)"),
    ("body_temp_c", "Body temp (°C)"),
]

METRIC_GROUPS: dict[str, list[str]] = {
    "recovery": ["resting_hr", "hrv", "sleep_hours", "sleep_score", "body_temp_c"],
    "activity": ["steps", "calories", "vo2max"],
    "load": ["daily_tss", "atl", "ctl"],
    "subjective": ["soreness", "heavy_legs", "mood", "energy", "fatigue", "stress"],
    "lifestyle": ["caffeine", "hydration_liters", "alcohol"],
}

MULTI_AXIS_GROUPS: list[tuple[str, list[str]]] = [
    ("y", ["resting_hr", "hrv", "body_temp_c"]),
    ("y2", ["sleep_hours", "sleep_score"]),
    ("y3", ["steps", "calories"]),
    ("y4", ["daily_tss", "atl", "ctl"]),
    ("y5", ["soreness", "heavy_legs", "mood", "energy", "fatigue", "stress"]),
    ("y6", ["caffeine", "hydration_liters", "alcohol"]),
]

COLORS = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
]

CORRELATION_METRICS: list[str] = [key for key, _ in METRICS] + ["workout_count"]

MIN_CORR_PAIRS = 5
TOP_SCATTER_PAIRS = 6


def load_daily_metrics(db_path: Path | None = None) -> pd.DataFrame:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    df = pd.read_sql_query("SELECT * FROM daily_metrics ORDER BY date", conn)
    conn.close()
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    return df


def _slice_period(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty:
        return df
    end = df["date"].max()
    start = end - timedelta(days=days - 1)
    return df[df["date"] >= start].copy()


def _label_map() -> dict[str, str]:
    return dict(METRICS)


def build_stacked_figure(df: pd.DataFrame, period_label: str) -> go.Figure:
    labels = _label_map()
    fig = make_subplots(
        rows=len(METRICS),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=[labels[key] for key, _ in METRICS],
    )
    for i, (key, _) in enumerate(METRICS, start=1):
        if key not in df.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=df[key],
                mode="lines+markers",
                name=labels[key],
                legendgroup=key,
                line={"color": COLORS[(i - 1) % len(COLORS)], "width": 2},
                marker={"size": 4},
                connectgaps=False,
            ),
            row=i,
            col=1,
        )
    fig.update_layout(
        height=280 * len(METRICS),
        title=f"Stacked view — {period_label}",
        showlegend=False,
        margin={"t": 60, "b": 40},
    )
    fig.update_xaxes(title_text="Date", row=len(METRICS), col=1)
    return fig


def _normalize_series(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return series
    lo, hi = valid.min(), valid.max()
    if hi == lo:
        return series.apply(lambda v: 50.0 if pd.notna(v) else None)
    return (series - lo) / (hi - lo) * 100


def build_normalized_figure(df: pd.DataFrame, period_label: str) -> go.Figure:
    labels = _label_map()
    fig = go.Figure()
    for i, (key, label) in enumerate(METRICS):
        if key not in df.columns:
            continue
        fig.add_trace(
            go.Scatter(
                x=df["date"],
                y=_normalize_series(df[key]),
                mode="lines+markers",
                name=label,
                legendgroup=key,
                line={"color": COLORS[i % len(COLORS)], "width": 2},
                marker={"size": 5},
                connectgaps=False,
            )
        )
    fig.update_layout(
        title=f"Normalized overlay — {period_label}",
        xaxis_title="Date",
        yaxis_title="Percent of period range (0–100%)",
        height=700,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        hovermode="x unified",
    )
    return fig


def build_multiaxis_figure(df: pd.DataFrame, period_label: str) -> go.Figure:
    labels = _label_map()
    fig = go.Figure()
    axis_titles = {
        "y": "HR / HRV",
        "y2": "Sleep",
        "y3": "Steps / Calories",
        "y4": "Load",
    }
    color_idx = 0
    for axis_name, keys in MULTI_AXIS_GROUPS:
        for key in keys:
            if key not in df.columns:
                continue
            trace_kwargs: dict[str, Any] = {
                "x": df["date"],
                "y": df[key],
                "mode": "lines+markers",
                "name": labels[key],
                "legendgroup": key,
                "line": {"color": COLORS[color_idx % len(COLORS)], "width": 2},
                "marker": {"size": 4},
                "connectgaps": False,
            }
            if axis_name != "y":
                trace_kwargs["yaxis"] = axis_name
            fig.add_trace(go.Scatter(**trace_kwargs))
            color_idx += 1

    fig.update_layout(
        title=f"Multi-axis view — {period_label}",
        xaxis={"title": "Date"},
        yaxis={"title": axis_titles["y"], "side": "left"},
        yaxis2={
            "title": axis_titles["y2"],
            "overlaying": "y",
            "side": "right",
            "anchor": "free",
            "position": 0.95,
        },
        yaxis3={
            "title": axis_titles["y3"],
            "overlaying": "y",
            "side": "right",
            "anchor": "free",
            "position": 1.0,
        },
        yaxis4={
            "title": axis_titles["y4"],
            "overlaying": "y",
            "side": "left",
            "anchor": "free",
            "position": 0.0,
        },
        yaxis5={
            "title": "Subjective",
            "overlaying": "y",
            "side": "right",
            "anchor": "free",
            "position": 0.88,
        },
        yaxis6={
            "title": "Lifestyle",
            "overlaying": "y",
            "side": "left",
            "anchor": "free",
            "position": 0.08,
        },
        height=700,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
        hovermode="x unified",
        margin={"r": 140, "l": 100},
    )
    return fig


def _figure_html(fig: go.Figure) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": True})


def _numeric_metric_frame(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in CORRELATION_METRICS if c in df.columns]
    return df[cols].apply(pd.to_numeric, errors="coerce")


def _pair_count(series_a: pd.Series, series_b: pd.Series) -> int:
    mask = series_a.notna() & series_b.notna()
    return int(mask.sum())


def compute_correlation_matrix(
    df: pd.DataFrame,
    *,
    lag_days: int = 0,
    min_pairs: int = MIN_CORR_PAIRS,
) -> pd.DataFrame:
    """Pearson r. lag_days=1 correlates each metric on day t-1 with metrics on day t."""
    numeric = _numeric_metric_frame(df)
    if numeric.empty:
        return pd.DataFrame()

    if lag_days == 0:
        return numeric.corr(method="pearson", min_periods=min_pairs)

    lagged = numeric.shift(lag_days)
    cols = list(numeric.columns)
    matrix = pd.DataFrame(index=cols, columns=cols, dtype=float)
    for row_key in cols:
        for col_key in cols:
            matrix.loc[row_key, col_key] = lagged[row_key].corr(
                numeric[col_key], min_periods=min_pairs
            )
    return matrix


def _top_pairs_with_counts(
    df: pd.DataFrame,
    corr: pd.DataFrame,
    *,
    n: int = TOP_SCATTER_PAIRS,
    lag_days: int = 0,
) -> list[tuple[str, str, float, int]]:
    numeric = _numeric_metric_frame(df)
    pairs: list[tuple[str, str, float, int]] = []
    cols = list(corr.columns)
    for i, key_a in enumerate(cols):
        for key_b in cols[i + 1 :]:
            r = corr.loc[key_a, key_b]
            if pd.isna(r):
                continue
            if lag_days:
                count = _pair_count(numeric[key_a].shift(lag_days), numeric[key_b])
            else:
                count = _pair_count(numeric[key_a], numeric[key_b])
            if count < MIN_CORR_PAIRS:
                continue
            pairs.append((key_a, key_b, float(r), count))
    pairs.sort(key=lambda item: abs(item[2]), reverse=True)
    return pairs[:n]


def build_correlation_heatmap(
    df: pd.DataFrame,
    period_label: str,
    *,
    lag_days: int = 0,
) -> go.Figure:
    corr = compute_correlation_matrix(df, lag_days=lag_days)
    labels = _label_map()
    labels["workout_count"] = "Workouts"
    if corr.empty:
        return go.Figure().update_layout(title="No numeric data for correlations")

    names = [labels.get(key, key) for key in corr.columns]
    z = corr.values
    text = [[f"{val:.2f}" if pd.notna(val) else "" for val in row] for row in z]

    if lag_days:
        title = f"Next-day correlations — {period_label} (row = yesterday, column = today)"
    else:
        title = f"Same-day correlations — {period_label}"

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=names,
            y=names,
            zmin=-1,
            zmax=1,
            colorscale="RdBu_r",
            colorbar={"title": "Pearson r"},
            text=text,
            texttemplate="%{text}",
            hovertemplate="%{y} vs %{x}<br>r = %{z:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        title=title,
        height=max(520, 28 * len(names) + 180),
        xaxis={"tickangle": -45, "side": "bottom"},
        yaxis={"autorange": "reversed"},
        margin={"b": 140, "l": 140, "t": 80},
    )
    return fig


def build_scatter_pairs_figure(
    df: pd.DataFrame,
    pairs: list[tuple[str, str, float, int]],
    period_label: str,
    *,
    lag_days: int = 0,
) -> go.Figure:
    labels = _label_map()
    labels["workout_count"] = "Workouts"
    numeric = _numeric_metric_frame(df)
    dates = df["date"] if "date" in df.columns else None

    if not pairs:
        fig = go.Figure()
        fig.update_layout(
            title=f"Strongest pairs — {period_label} (need ≥{MIN_CORR_PAIRS} overlapping days)",
            annotations=[
                {
                    "text": "Not enough overlapping data yet for scatter plots.",
                    "xref": "paper",
                    "yref": "paper",
                    "x": 0.5,
                    "y": 0.5,
                    "showarrow": False,
                    "font": {"size": 14},
                }
            ],
            height=320,
        )
        return fig

    cols = min(3, len(pairs))
    rows = (len(pairs) + cols - 1) // cols
    subtitles = []
    for key_a, key_b, r, count in pairs:
        lag_note = f", lag {lag_days}d" if lag_days else ""
        subtitles.append(
            f"{labels.get(key_a, key_a)} vs {labels.get(key_b, key_b)} "
            f"(r={r:+.2f}, n={count}{lag_note})"
        )

    fig = make_subplots(
        rows=rows,
        cols=cols,
        subplot_titles=subtitles,
        horizontal_spacing=0.08,
        vertical_spacing=0.12,
    )

    for idx, (key_a, key_b, r, _count) in enumerate(pairs):
        row = idx // cols + 1
        col = idx % cols + 1
        x_series = numeric[key_a]
        y_series = numeric[key_b]
        if lag_days:
            x_series = x_series.shift(lag_days)
        mask = x_series.notna() & y_series.notna()
        hover = dates[mask].dt.strftime("%Y-%m-%d").tolist() if dates is not None else None

        fig.add_trace(
            go.Scatter(
                x=x_series[mask],
                y=y_series[mask],
                mode="markers",
                marker={"size": 8, "color": COLORS[idx % len(COLORS)], "opacity": 0.75},
                text=hover,
                hovertemplate=(
                    f"{labels.get(key_a, key_a)}=%{{x}}<br>"
                    f"{labels.get(key_b, key_b)}=%{{y}}<br>"
                    "%{text}<extra></extra>"
                ),
                showlegend=False,
            ),
            row=row,
            col=col,
        )
        if mask.sum() >= 2:
            coeffs = np_polyfit_safe(x_series[mask], y_series[mask])
            if coeffs is not None:
                x_line = pd.Series([x_series[mask].min(), x_series[mask].max()])
                y_line = coeffs[0] * x_line + coeffs[1]
                fig.add_trace(
                    go.Scatter(
                        x=x_line,
                        y=y_line,
                        mode="lines",
                        line={"color": "#495057", "width": 1, "dash": "dash"},
                        showlegend=False,
                        hoverinfo="skip",
                    ),
                    row=row,
                    col=col,
                )

    lag_title = " (yesterday → today)" if lag_days else ""
    fig.update_layout(
        title=f"Strongest correlations{lag_title} — {period_label}",
        height=280 * rows + 80,
        showlegend=False,
    )
    return fig


def np_polyfit_safe(x: pd.Series, y: pd.Series) -> tuple[float, float] | None:
    try:
        import numpy as np

        if len(x) < 2 or x.std() == 0:
            return None
        slope, intercept = np.polyfit(x.astype(float), y.astype(float), 1)
        return float(slope), float(intercept)
    except Exception:
        return None


def _correlation_summary_table(
    pairs: list[tuple[str, str, float, int]],
    *,
    lag_days: int = 0,
) -> str:
    labels = _label_map()
    labels["workout_count"] = "Workouts"
    if not pairs:
        return (
            '<p class="corr-note">No strong pairs yet — log more overlapping days '
            f"(need at least {MIN_CORR_PAIRS} days with both metrics).</p>"
        )

    rows_html = []
    for key_a, key_b, r, count in pairs:
        direction = "positive" if r > 0 else "negative"
        strength = "strong" if abs(r) >= 0.6 else "moderate" if abs(r) >= 0.4 else "mild"
        if lag_days:
            desc = (
                f"Yesterday's <strong>{labels.get(key_a, key_a)}</strong> vs "
                f"today's <strong>{labels.get(key_b, key_b)}</strong>"
            )
        else:
            desc = (
                f"<strong>{labels.get(key_a, key_a)}</strong> vs "
                f"<strong>{labels.get(key_b, key_b)}</strong>"
            )
        rows_html.append(
            f"<tr><td>{desc}</td>"
            f'<td class="r-{direction}">{r:+.2f}</td>'
            f"<td>{strength}</td><td>{count}</td></tr>"
        )

    lag_hdr = " (yesterday → today)" if lag_days else ""
    return f"""
    <div class="corr-summary">
      <h3>Top relationships{lag_hdr}</h3>
      <table class="corr-table">
        <thead>
          <tr><th>Metrics</th><th>r</th><th>Strength</th><th>Days</th></tr>
        </thead>
        <tbody>
          {"".join(rows_html)}
        </tbody>
      </table>
      <p class="corr-note">Pearson correlation on days where both metrics are logged.
      Same-day view finds patterns within a day; next-day view tests if yesterday's
      sleep, load, alcohol, etc. relates to today's recovery scores.</p>
    </div>
    """


FOOD_COLUMNS: list[tuple[str, str]] = [
    ("food_breakfast", "Breakfast"),
    ("food_lunch", "Lunch"),
    ("food_dinner", "Dinner"),
    ("food_snacks", "Snacks"),
    ("food_extra_meal", "Extra meal"),
]


def build_food_summary_section(df: pd.DataFrame, period_label: str) -> str:
    """HTML table of rough food intake for days in the period."""
    if df.empty:
        return '<p class="corr-note">No food logs in this period yet.</p>'

    cols = [key for key, _ in FOOD_COLUMNS if key in df.columns]
    if not cols:
        return '<p class="corr-note">No food logs in this period yet.</p>'

    mask = df[cols].notna().any(axis=1)
    food_df = df.loc[mask, ["date"] + cols].sort_values("date", ascending=False)
    if food_df.empty:
        return '<p class="corr-note">No food logs in this period yet.</p>'

    labels = dict(FOOD_COLUMNS)
    rows_html = []
    for _, row in food_df.iterrows():
        day = row["date"]
        day_str = day.date().isoformat() if hasattr(day, "date") else str(day)[:10]
        cells = "".join(
            f"<td>{_escape_html(row.get(key))}</td>"
            for key, _ in FOOD_COLUMNS
            if key in cols
        )
        rows_html.append(f"<tr><td>{day_str}</td>{cells}</tr>")

    headers = "".join(
        f"<th>{labels[key]}</th>" for key, _ in FOOD_COLUMNS if key in cols
    )
    return f"""
    <div class="corr-summary food-summary">
      <h3>Food log — {period_label}</h3>
      <p class="corr-note">Rough intake logged in wellness comments (breakfast, lunch, dinner, snacks, extra meal on training days).</p>
      <table class="corr-table food-table">
        <thead>
          <tr><th>Date</th>{headers}</tr>
        </thead>
        <tbody>
          {"".join(rows_html)}
        </tbody>
      </table>
    </div>
    """


def _escape_html(value: object) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_correlations_section(df: pd.DataFrame, period_label: str) -> str:
    """HTML block: same-day heatmap, next-day heatmap, tables, scatter plots."""
    same_corr = compute_correlation_matrix(df, lag_days=0)
    lag_corr = compute_correlation_matrix(df, lag_days=1)
    same_pairs = _top_pairs_with_counts(df, same_corr, lag_days=0)
    lag_pairs = _top_pairs_with_counts(df, lag_corr, lag_days=1)

    parts = [
        _correlation_summary_table(same_pairs, lag_days=0),
        _figure_html(build_correlation_heatmap(df, period_label, lag_days=0)),
        _figure_html(build_scatter_pairs_figure(df, same_pairs, period_label, lag_days=0)),
        _correlation_summary_table(lag_pairs, lag_days=1),
        _figure_html(build_correlation_heatmap(df, period_label, lag_days=1)),
        _figure_html(build_scatter_pairs_figure(df, lag_pairs, period_label, lag_days=1)),
    ]
    return "\n".join(parts)


def write_dashboard(df: pd.DataFrame, out_path: Path | None = None) -> Path:
    out_path = out_path or CHARTS_DIR / "dashboard.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    panels: dict[str, dict[str, str]] = {}
    for period_key, days in PERIODS.items():
        sliced = _slice_period(df, days)
        panels[period_key] = {
            "stacked": _figure_html(build_stacked_figure(sliced, period_key)),
            "normalized": _figure_html(build_normalized_figure(sliced, period_key)),
            "multiaxis": _figure_html(build_multiaxis_figure(sliced, period_key)),
            "correlations": build_correlations_section(sliced, period_key),
            "food": build_food_summary_section(sliced, period_key),
        }

    html = _dashboard_template(panels, df)
    out_path.write_text(html, encoding="utf-8")
    return out_path


def _dashboard_template(panels: dict[str, dict[str, str]], df: pd.DataFrame) -> str:
    date_range = ""
    if not df.empty:
        date_range = (
            f"{df['date'].min().date()} to {df['date'].max().date()} "
            f"({len(df)} days)"
        )

    period_buttons = "".join(
        f'<button class="tab period-tab{" active" if key == "7d" else ""}" '
        f'data-period="{key}">{key}</button>'
        for key in PERIODS
    )
    view_buttons = """
        <button class="tab view-tab active" data-view="stacked">Stacked</button>
        <button class="tab view-tab" data-view="normalized">Normalized</button>
        <button class="tab view-tab" data-view="multiaxis">Multi-axis</button>
        <button class="tab view-tab" data-view="correlations">Correlations</button>
        <button class="tab view-tab" data-view="food">Food log</button>
    """

    group_toggles = """
        <button class="tab group-tab" data-group="recovery">Recovery</button>
        <button class="tab group-tab" data-group="activity">Activity</button>
        <button class="tab group-tab" data-group="load">Load</button>
        <button class="tab group-tab" data-group="subjective">Subjective</button>
        <button class="tab group-tab" data-group="lifestyle">Lifestyle</button>
        <button class="tab utility-tab" id="show-all-btn">Show all</button>
        <button class="tab utility-tab" id="hide-all-btn">Hide all</button>
    """

    metric_checkboxes = "".join(
        f'<label class="metric-label">'
        f'<input type="checkbox" class="metric-toggle" data-metric="{key}" checked> '
        f'{label}</label>'
        for key, label in METRICS
    )

    groups_json = json.dumps(METRIC_GROUPS)

    chart_divs = []
    for period_key, views in panels.items():
        for view_key, chart_html in views.items():
            active = "active" if period_key == "7d" and view_key == "stacked" else ""
            chart_divs.append(
                f'<div class="chart-panel {active}" '
                f'data-period="{period_key}" data-view="{view_key}">\n{chart_html}\n</div>'
            )

    chart_body = "\n".join(chart_divs)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Fatigue Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      margin: 0;
      padding: 1rem 1.5rem 2rem;
      background: #f8f9fa;
      color: #212529;
    }}
    h1 {{ margin: 0 0 0.25rem; font-size: 1.5rem; }}
    .subtitle {{ color: #6c757d; margin-bottom: 1rem; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 1rem; margin-bottom: 0.75rem; }}
    .control-group {{ display: flex; flex-wrap: wrap; gap: 0.35rem; align-items: center; }}
    .control-label {{ font-weight: 600; margin-right: 0.25rem; }}
    .tab {{
      border: 1px solid #ced4da;
      background: white;
      padding: 0.4rem 0.85rem;
      border-radius: 6px;
      cursor: pointer;
      font-size: 0.9rem;
    }}
    .tab.active {{
      background: #0d6efd;
      color: white;
      border-color: #0d6efd;
    }}
    .utility-tab {{ background: #e9ecef; }}
    .metric-panel {{
      background: white;
      border-radius: 8px;
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      border: 1px solid #dee2e6;
    }}
    .metric-panel h2 {{
      margin: 0 0 0.5rem;
      font-size: 0.95rem;
      font-weight: 600;
    }}
    .metric-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1.25rem;
    }}
    .metric-label {{
      font-size: 0.875rem;
      cursor: pointer;
      user-select: none;
    }}
    .metric-label input {{ margin-right: 0.25rem; }}
    .chart-panel {{ display: none; background: white; border-radius: 8px; padding: 0.5rem; }}
    .chart-panel.active {{ display: block; }}
    .chart-panel[data-view="correlations"] {{
      padding: 1rem 1.25rem 1.5rem;
    }}
    .corr-summary {{
      margin: 1.25rem 0 0.75rem;
    }}
    .corr-summary h3 {{
      margin: 0 0 0.5rem;
      font-size: 1rem;
      font-weight: 600;
    }}
    .corr-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
      margin-bottom: 0.5rem;
    }}
    .corr-table th, .corr-table td {{
      border: 1px solid #dee2e6;
      padding: 0.45rem 0.65rem;
      text-align: left;
    }}
    .corr-table th {{
      background: #f1f3f5;
      font-weight: 600;
    }}
    .corr-table td.r-positive {{ color: #c92a2a; font-weight: 600; }}
    .corr-table td.r-negative {{ color: #1864ab; font-weight: 600; }}
    .corr-note {{
      color: #6c757d;
      font-size: 0.8125rem;
      margin: 0.35rem 0 1rem;
      line-height: 1.45;
    }}
    .metric-panel.hidden {{ display: none; }}
    .food-table td {{ max-width: 14rem; word-wrap: break-word; vertical-align: top; }}
    .food-summary {{ margin-top: 0; }}
  </style>
</head>
<body>
  <h1>Fatigue Dashboard</h1>
  <p class="subtitle">Data range: {date_range}</p>
  <div class="controls">
    <div class="control-group">
      <span class="control-label">Period:</span>
      {period_buttons}
    </div>
    <div class="control-group">
      <span class="control-label">View:</span>
      {view_buttons}
    </div>
    <div class="control-group">
      <span class="control-label">Groups:</span>
      {group_toggles}
    </div>
  </div>
  <div class="metric-panel" id="metric-panel">
    <h2>Show / hide metrics</h2>
    <div class="metric-grid">
      {metric_checkboxes}
    </div>
  </div>
  <div id="charts">
    {chart_body}
  </div>
  <script>
    const METRIC_GROUPS = {groups_json};
    let currentPeriod = "7d";
    let currentView = "stacked";

    function hiddenMetrics() {{
      return new Set(
        [...document.querySelectorAll(".metric-toggle:not(:checked)")]
          .map(cb => cb.dataset.metric)
      );
    }}

    function applyMetricVisibility() {{
      const hidden = hiddenMetrics();
      document.querySelectorAll(".chart-panel").forEach(panel => {{
        const plotDiv = panel.querySelector(".plotly-graph-div");
        if (!plotDiv || !plotDiv.data) return;
        const visible = plotDiv.data.map(trace => {{
          const key = trace.legendgroup;
          return key && hidden.has(key) ? false : true;
        }});
        Plotly.restyle(plotDiv, {{ visible }});
      }});
    }}

    function setGroupVisibility(groupKey, show) {{
      const keys = METRIC_GROUPS[groupKey] || [];
      document.querySelectorAll(".metric-toggle").forEach(cb => {{
        if (keys.includes(cb.dataset.metric)) {{
          cb.checked = show;
        }}
      }});
      applyMetricVisibility();
    }}

    function toggleGroup(groupKey) {{
      const keys = METRIC_GROUPS[groupKey] || [];
      const checkboxes = [...document.querySelectorAll(".metric-toggle")]
        .filter(cb => keys.includes(cb.dataset.metric));
      const allOn = checkboxes.every(cb => cb.checked);
      setGroupVisibility(groupKey, !allOn);
    }}

    function showPanel() {{
      document.querySelectorAll(".chart-panel").forEach(el => {{
        el.classList.toggle(
          "active",
          el.dataset.period === currentPeriod && el.dataset.view === currentView
        );
      }});
      document.querySelectorAll(".period-tab").forEach(el => {{
        el.classList.toggle("active", el.dataset.period === currentPeriod);
      }});
      document.querySelectorAll(".view-tab").forEach(el => {{
        el.classList.toggle("active", el.dataset.view === currentView);
      }});
      document.getElementById("metric-panel").classList.toggle(
        "hidden",
        currentView === "correlations" || currentView === "food"
      );
      if (currentView !== "correlations" && currentView !== "food") {{
        applyMetricVisibility();
      }}
      window.dispatchEvent(new Event("resize"));
    }}

    document.querySelectorAll(".period-tab").forEach(btn => {{
      btn.addEventListener("click", () => {{
        currentPeriod = btn.dataset.period;
        showPanel();
      }});
    }});
    document.querySelectorAll(".view-tab").forEach(btn => {{
      btn.addEventListener("click", () => {{
        currentView = btn.dataset.view;
        showPanel();
      }});
    }});
    document.querySelectorAll(".group-tab").forEach(btn => {{
      btn.addEventListener("click", () => toggleGroup(btn.dataset.group));
    }});
    document.getElementById("show-all-btn").addEventListener("click", () => {{
      document.querySelectorAll(".metric-toggle").forEach(cb => {{ cb.checked = true; }});
      applyMetricVisibility();
    }});
    document.getElementById("hide-all-btn").addEventListener("click", () => {{
      document.querySelectorAll(".metric-toggle").forEach(cb => {{ cb.checked = false; }});
      applyMetricVisibility();
    }});
    document.querySelectorAll(".metric-toggle").forEach(cb => {{
      cb.addEventListener("change", applyMetricVisibility);
    }});
    showPanel();
  </script>
</body>
</html>
"""


def generate_charts(db_path: Path | None = None, out_path: Path | None = None) -> Path:
    df = load_daily_metrics(db_path)
    if df.empty:
        raise ValueError("No daily metrics found. Run sync and aggregate first.")
    return write_dashboard(df, out_path)
