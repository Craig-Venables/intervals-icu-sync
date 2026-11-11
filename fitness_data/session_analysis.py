"""Pure-function session analysis from intervals.icu activity streams."""

from __future__ import annotations

from typing import Any


def _finite(values: list[Any]) -> list[float]:
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f:  # NaN
            continue
        out.append(f)
    return out


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _safe_get_list(streams: dict[str, list[Any]], key: str) -> list[Any]:
    val = streams.get(key)
    return val if isinstance(val, list) else []


def _fmt_pace(seconds_per_km: float | None) -> str | None:
    if seconds_per_km is None or seconds_per_km <= 0 or seconds_per_km > 3600:
        return None
    total = int(round(seconds_per_km))
    return f"{total // 60}:{total % 60:02d}/km"


def _fmt_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "?"
    s = int(round(float(seconds)))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{sec:02d}s"
    return f"{m}m{sec:02d}s"


def _activity_type(summary: dict[str, Any]) -> str:
    return str(summary.get("type") or summary.get("sport") or "Workout")


def _is_run(atype: str) -> bool:
    return atype.lower() in {"run", "virtualrun", "trailrun", "walk", "hike"}


def _is_ride(atype: str) -> bool:
    return atype.lower() in {"ride", "virtualride", "gravelride", "mountainbikeride", "ebikeride"}


def _is_swim(atype: str) -> bool:
    return "swim" in atype.lower()


def _aligned_series(
    streams: dict[str, list[Any]], keys: list[str]
) -> dict[str, list[Any]]:
    series = {k: _safe_get_list(streams, k) for k in keys}
    lengths = [len(v) for v in series.values() if v]
    if not lengths:
        return series
    n = min(lengths)
    return {k: (v[:n] if v else []) for k, v in series.items()}



def _pause_gap_threshold(time_s: list[Any]) -> float:
    """Seconds between samples that count as an auto-pause (not smart-recording)."""
    deltas: list[float] = []
    for i in range(len(time_s) - 1):
        try:
            d = float(time_s[i + 1] or 0) - float(time_s[i] or 0)
        except (TypeError, ValueError):
            continue
        if 0 < d < 30:
            deltas.append(d)
    if not deltas:
        return 15.0
    deltas.sort()
    median = deltas[len(deltas) // 2]
    # Smart recording on rides often has 2–6s steps; true pauses are much larger.
    return max(15.0, median * 5.0)


def _km_splits(
    *,
    time_s: list[Any],
    distance_m: list[Any],
    heartrate: list[Any],
    velocity: list[Any],
    watts: list[Any],
    sport: str,
) -> list[dict[str, Any]]:
    """Build 1 km splits with pace/power, avg HR, and stop pollution flag."""
    n = min(len(time_s), len(distance_m))
    if n < 2:
        return []

    pause_thr = _pause_gap_threshold(time_s)
    splits: list[dict[str, Any]] = []
    next_km = 1
    start_idx = 0

    def _slice_stats(i0: int, i1: int, km_label: int) -> dict[str, Any]:
        t0 = float(time_s[i0] or 0)
        t1 = float(time_s[i1] or 0)
        d0 = float(distance_m[i0] or 0)
        d1 = float(distance_m[i1] or 0)
        elapsed_dt = max(0.0, t1 - t0)
        # Moving time excludes auto-pause gaps
        moving_dt = 0.0
        for j in range(i0, i1):
            try:
                step = float(time_s[j + 1] or 0) - float(time_s[j] or 0)
            except (TypeError, ValueError):
                continue
            if 0 < step <= pause_thr:
                moving_dt += step
        dt = moving_dt if moving_dt > 0 else elapsed_dt
        dd = max(0.0, d1 - d0)
        pace_s_per_km = (dt / dd * 1000.0) if dd > 1 else None

        hr_vals = _finite(heartrate[i0 : i1 + 1]) if heartrate else []
        watt_vals = _finite(watts[i0 : i1 + 1]) if watts else []
        # Ignore zero watts for avg when device reports zeros while stopped
        watt_moving = [w for w in watt_vals if w > 0]

        # Polluted if long pauses: auto-pause gaps or crawl speed for >60s total
        stop_s = 0.0
        polluted = False
        end = min(i1, max(len(time_s) - 1, i0))
        for j in range(i0, end):
            try:
                t_a = float(time_s[j] or 0)
                t_b = float(time_s[j + 1] or 0)
            except (TypeError, ValueError):
                continue
            sample_dt = max(0.0, t_b - t_a)
            speed = 0.0
            if velocity and j < len(velocity) and velocity[j] is not None:
                try:
                    speed = float(velocity[j])
                except (TypeError, ValueError):
                    speed = 0.0
            if sample_dt > pause_thr:
                stop_s += sample_dt
            elif speed < 0.3 and sample_dt > 0:
                stop_s += sample_dt
        polluted = stop_s > 60.0

        split: dict[str, Any] = {
            "km": km_label,
            "distance_m": round(dd, 1),
            "time_s": round(dt, 1),
            "pace_s_per_km": round(pace_s_per_km, 1) if pace_s_per_km else None,
            "pace": _fmt_pace(pace_s_per_km),
            "avg_hr": round(_mean(hr_vals), 1) if hr_vals else None,
            "avg_watts": round(_mean(watt_moving), 1) if watt_moving else None,
            "stop_time_s": round(stop_s, 1),
            "polluted_by_stops": polluted,
        }
        if _is_swim(sport):
            # Swim: still report pace as /km; optional /100m
            if pace_s_per_km:
                split["pace_per_100m"] = _fmt_pace(pace_s_per_km / 10.0)
                if split["pace_per_100m"]:
                    split["pace_per_100m"] = split["pace_per_100m"].replace("/km", "/100m")
        return split

    for i in range(n):
        dist = distance_m[i]
        if dist is None:
            continue
        try:
            d = float(dist)
        except (TypeError, ValueError):
            continue
        while d >= next_km * 1000.0 and start_idx < i:
            splits.append(_slice_stats(start_idx, i, next_km))
            start_idx = i
            next_km += 1

    # Partial final km if meaningful (>100m)
    if start_idx < n - 1:
        d0 = float(distance_m[start_idx] or 0)
        d1 = float(distance_m[n - 1] or 0)
        if d1 - d0 >= 100:
            splits.append(_slice_stats(start_idx, n - 1, next_km))

    return splits


def _hr_drift(
    *,
    time_s: list[Any],
    heartrate: list[Any],
    distance_m: list[Any],
    velocity: list[Any],
    watts: list[Any],
) -> dict[str, Any] | None:
    """First-half vs second-half avg HR (by elapsed time midpoint)."""
    n = min(len(time_s), len(heartrate))
    if n < 10:
        return None

    t_vals = []
    for i in range(n):
        try:
            t_vals.append(float(time_s[i]))
        except (TypeError, ValueError):
            t_vals.append(float(i))
    t0, t1 = t_vals[0], t_vals[-1]
    if t1 <= t0:
        mid_t = (n - 1) / 2.0
        mid_idx = n // 2
        use_time = False
    else:
        mid_t = (t0 + t1) / 2.0
        mid_idx = next((i for i, t in enumerate(t_vals) if t >= mid_t), n // 2)
        use_time = True

    pause_thr = _pause_gap_threshold(time_s)

    def half_means(i0: int, i1: int) -> dict[str, float | None]:
        # Prefer moving samples: exclude points after large recording gaps
        hr_vals: list[float] = []
        vel_vals: list[float] = []
        watt_vals: list[float] = []
        moving_time = 0.0
        for j in range(i0, min(i1, n)):
            gap = 0.0
            if j > i0:
                gap = t_vals[j] - t_vals[j - 1]
            if gap > pause_thr:
                continue  # skip first sample after auto-pause gap
            hv = heartrate[j] if j < len(heartrate) else None
            if hv is not None:
                try:
                    hr_vals.append(float(hv))
                except (TypeError, ValueError):
                    pass
            if velocity and j < len(velocity) and velocity[j] is not None:
                try:
                    vel_vals.append(float(velocity[j]))
                except (TypeError, ValueError):
                    pass
            if watts and j < len(watts) and watts[j] is not None:
                try:
                    wv = float(watts[j])
                    if wv > 0:
                        watt_vals.append(wv)
                except (TypeError, ValueError):
                    pass
            if j + 1 < min(i1, n):
                step = t_vals[j + 1] - t_vals[j]
                if 0 < step <= pause_thr:
                    moving_time += step

        dist = distance_m[i0:i1] if distance_m else []
        pace = None
        if len(dist) >= 2:
            try:
                dd = float(dist[-1] or 0) - float(dist[0] or 0)
                # Use moving time (exclude pause gaps) for pace comparison
                dt = moving_time if moving_time > 0 else (
                    t_vals[min(i1 - 1, n - 1)] - t_vals[i0]
                )
                if dd > 1 and dt > 0:
                    pace = dt / dd * 1000.0
            except (TypeError, ValueError):
                pace = None
        return {
            "avg_hr": _mean(hr_vals),
            "avg_speed_mps": _mean(vel_vals) if vel_vals else None,
            "avg_watts": _mean(watt_vals) if watt_vals else None,
            "pace_s_per_km": pace,
        }

    first = half_means(0, mid_idx)
    second = half_means(mid_idx, n)
    hr1, hr2 = first["avg_hr"], second["avg_hr"]
    if not hr1 or not hr2 or hr1 <= 0:
        return None
    drift_pct = (hr2 - hr1) / hr1 * 100.0

    notes: list[str] = []
    # Pace/power change notes
    p1, p2 = first["pace_s_per_km"], second["pace_s_per_km"]
    if p1 and p2 and p1 > 0:
        pace_change_pct = (p2 - p1) / p1 * 100.0
        if abs(pace_change_pct) >= 3:
            direction = "slower" if pace_change_pct > 0 else "faster"
            notes.append(f"pace {abs(pace_change_pct):.0f}% {direction} in 2nd half")
    w1, w2 = first["avg_watts"], second["avg_watts"]
    if w1 and w2 and w1 > 0:
        power_change_pct = (w2 - w1) / w1 * 100.0
        if abs(power_change_pct) >= 5:
            direction = "higher" if power_change_pct > 0 else "lower"
            notes.append(f"power {abs(power_change_pct):.0f}% {direction} in 2nd half")
    s1, s2 = first["avg_speed_mps"], second["avg_speed_mps"]
    if s1 and s2 and s1 > 0 and not (p1 and p2):
        speed_change_pct = (s2 - s1) / s1 * 100.0
        if abs(speed_change_pct) >= 3:
            direction = "faster" if speed_change_pct > 0 else "slower"
            notes.append(f"speed {abs(speed_change_pct):.0f}% {direction} in 2nd half")

    return {
        "hr_drift_pct": round(drift_pct, 1),
        "first_half_avg_hr": round(hr1, 1),
        "second_half_avg_hr": round(hr2, 1),
        "first_half_pace_s_per_km": round(p1, 1) if p1 else None,
        "second_half_pace_s_per_km": round(p2, 1) if p2 else None,
        "first_half_avg_watts": round(w1, 1) if w1 else None,
        "second_half_avg_watts": round(w2, 1) if w2 else None,
        "notes": notes,
    }


def _power_spikes(
    watts: list[Any],
    time_s: list[Any],
    *,
    np_watts: float | None,
    avg_watts: float | None,
) -> dict[str, Any] | None:
    w_all = []
    for i, v in enumerate(watts):
        if v is None:
            continue
        try:
            w_all.append((i, float(v)))
        except (TypeError, ValueError):
            continue
    if not w_all:
        return None

    values = [w for _, w in w_all]
    max_w = max(values)
    threshold = 300.0
    if np_watts and np_watts > 0:
        threshold = max(threshold, 1.2 * np_watts)

    # Count brief spike events: contiguous runs above threshold lasting < 15s
    spike_events = 0
    spike_samples = 0
    i = 0
    idx_map = {idx: w for idx, w in w_all}
    n = len(watts)
    while i < n:
        w = idx_map.get(i)
        if w is None or w < threshold:
            i += 1
            continue
        j = i
        while j < n:
            wj = idx_map.get(j)
            if wj is None or wj < threshold:
                break
            j += 1
        # duration via time stream if available
        if time_s and i < len(time_s) and j - 1 < len(time_s):
            try:
                dur = float(time_s[j - 1] or 0) - float(time_s[i] or 0)
            except (TypeError, ValueError):
                dur = float(j - i)
        else:
            dur = float(j - i)
        sample_count = j - i
        spike_samples += sample_count
        # "brief" spikes: under 15s (or single-sample bursts)
        if dur <= 15.0 or sample_count <= 15:
            spike_events += 1
        i = max(j, i + 1)

    vi = None
    if np_watts and avg_watts and avg_watts > 0:
        vi = round(np_watts / avg_watts, 3)

    return {
        "threshold_w": round(threshold, 1),
        "spike_events": spike_events,
        "spike_samples": spike_samples,
        "max_watts": round(max_w, 1),
        "np_watts": round(np_watts, 1) if np_watts else None,
        "avg_watts": round(avg_watts, 1) if avg_watts else None,
        "variability_index": vi,
    }


def _overall_from_summary_and_streams(
    summary: dict[str, Any],
    streams: dict[str, list[Any]],
    sport: str,
) -> dict[str, Any]:
    moving = summary.get("moving_time")
    elapsed = summary.get("elapsed_time")
    distance_m = summary.get("distance") or summary.get("icu_distance")
    if distance_m is None:
        dist_s = _finite(_safe_get_list(streams, "distance"))
        distance_m = dist_s[-1] if dist_s else None

    hr_stream = _finite(_safe_get_list(streams, "heartrate"))
    avg_hr = summary.get("average_heartrate")
    if avg_hr is None and hr_stream:
        avg_hr = _mean(hr_stream)
    max_hr = summary.get("max_heartrate")
    if max_hr is None and hr_stream:
        max_hr = max(hr_stream)

    elev = summary.get("total_elevation_gain")
    if elev is None:
        alt = _finite(_safe_get_list(streams, "altitude"))
        if len(alt) >= 2:
            gain = 0.0
            for a, b in zip(alt, alt[1:]):
                if b > a:
                    gain += b - a
            elev = gain

    tss = summary.get("icu_training_load") or summary.get("tss")
    intensity = summary.get("icu_intensity")  # typically percent e.g. 65.7
    intensity_factor = None
    if intensity is not None:
        try:
            intensity_factor = float(intensity) / 100.0 if float(intensity) > 2 else float(intensity)
        except (TypeError, ValueError):
            intensity_factor = None

    np_watts = (
        summary.get("icu_weighted_avg_watts")
        or summary.get("normalized_power")
        or summary.get("weighted_average_watts")
    )
    avg_watts = summary.get("average_watts") or summary.get("icu_average_watts")
    watt_stream = [w for w in _finite(_safe_get_list(streams, "watts")) if w > 0]
    if avg_watts is None and watt_stream:
        avg_watts = _mean(watt_stream)

    distance_km = round(float(distance_m) / 1000.0, 3) if distance_m else None

    overall: dict[str, Any] = {
        "moving_time_s": moving,
        "elapsed_time_s": elapsed,
        "distance_km": distance_km,
        "avg_hr": round(float(avg_hr), 1) if avg_hr is not None else None,
        "max_hr": round(float(max_hr), 1) if max_hr is not None else None,
        "elevation_gain_m": round(float(elev), 1) if elev is not None else None,
        "tss": tss,
        "intensity_factor": round(intensity_factor, 3) if intensity_factor is not None else None,
        "avg_watts": round(float(avg_watts), 1) if avg_watts is not None else None,
        "np_watts": round(float(np_watts), 1) if np_watts is not None else None,
        "moving_pace_s_per_km": None,
        "moving_pace": None,
    }

    if distance_m and moving and float(distance_m) > 0 and float(moving) > 0:
        pace = float(moving) / (float(distance_m) / 1000.0)
        overall["moving_pace_s_per_km"] = round(pace, 1)
        overall["moving_pace"] = _fmt_pace(pace)

    if _is_swim(sport) and overall["moving_pace_s_per_km"]:
        p100 = overall["moving_pace_s_per_km"] / 10.0
        overall["moving_pace_per_100m"] = (_fmt_pace(p100) or "").replace("/km", "/100m") or None

    return overall


def analyse_activity_from_streams(
    activity_summary: dict[str, Any],
    streams: dict[str, list[Any]],
) -> dict[str, Any]:
    """Build a structured session report from summary + streams."""
    sport = _activity_type(activity_summary)
    aligned = _aligned_series(
        streams, ["time", "distance", "heartrate", "velocity_smooth", "watts", "altitude"]
    )
    time_s = aligned["time"]
    distance_m = aligned["distance"]
    heartrate = aligned["heartrate"]
    velocity = aligned["velocity_smooth"]
    watts = aligned["watts"]

    overall = _overall_from_summary_and_streams(activity_summary, streams, sport)

    elapsed = overall.get("elapsed_time_s")
    moving = overall.get("moving_time_s")
    stop_time_s = None
    if elapsed is not None and moving is not None:
        try:
            stop_time_s = max(0.0, float(elapsed) - float(moving))
        except (TypeError, ValueError):
            stop_time_s = None

    splits = _km_splits(
        time_s=time_s,
        distance_m=distance_m,
        heartrate=heartrate,
        velocity=velocity,
        watts=watts,
        sport=sport,
    )

    drift = _hr_drift(
        time_s=time_s,
        heartrate=heartrate,
        distance_m=distance_m,
        velocity=velocity,
        watts=watts,
    )

    power = None
    # Power spikes for rides (and any session that actually has watts stream)
    if _is_ride(sport) and watts:
        power = _power_spikes(
            watts,
            time_s,
            np_watts=overall.get("np_watts"),
            avg_watts=overall.get("avg_watts"),
        )
    elif watts and _is_ride(sport) is False and overall.get("avg_watts"):
        # Still compute for runs with power meter if useful, but only when watts present
        # Spec: "power_spikes (rides with watts)" — keep rides-only
        pass

    report: dict[str, Any] = {
        "activity_id": activity_summary.get("id"),
        "name": activity_summary.get("name"),
        "type": sport,
        "start_date_local": activity_summary.get("start_date_local"),
        "overall": overall,
        "stop_time_s": round(stop_time_s, 1) if stop_time_s is not None else None,
        "splits_by_km": splits,
        "hr_drift": drift,
        "hr_drift_pct": drift.get("hr_drift_pct") if drift else None,
        "power_spikes": power,
    }
    return report


def format_report_text(report: dict[str, Any]) -> str:
    """Short coach-readable paragraph + optional split lines."""
    name = report.get("name") or "Activity"
    sport = report.get("type") or ""
    overall = report.get("overall") or {}
    lines: list[str] = []

    bits: list[str] = [f"{name} ({sport})"]
    if overall.get("distance_km") is not None:
        bits.append(f"{overall['distance_km']:.2f} km")
    if overall.get("moving_time_s") is not None:
        bits.append(f"moving {_fmt_duration(overall['moving_time_s'])}")
    if report.get("stop_time_s"):
        bits.append(f"stops {_fmt_duration(report['stop_time_s'])}")
    if overall.get("moving_pace"):
        bits.append(f"pace {overall['moving_pace']}")
    elif overall.get("moving_pace_per_100m"):
        bits.append(f"pace {overall['moving_pace_per_100m']}")
    # Watts/NP primarily for rides; still show if present on rides
    if overall.get("avg_watts") is not None and _is_ride(str(sport)):
        w = f"avg {overall['avg_watts']:.0f}W"
        if overall.get("np_watts") is not None:
            w += f", NP {overall['np_watts']:.0f}W"
        bits.append(w)
    if overall.get("avg_hr") is not None:
        hr = f"HR {overall['avg_hr']:.0f}"
        if overall.get("max_hr") is not None:
            hr += f"/{overall['max_hr']:.0f}"
        bits.append(hr)
    if overall.get("elevation_gain_m") is not None:
        bits.append(f"elev +{overall['elevation_gain_m']:.0f}m")
    if overall.get("tss") is not None:
        tss_bit = f"TSS {overall['tss']}"
        if overall.get("intensity_factor") is not None:
            tss_bit += f" IF {overall['intensity_factor']:.2f}"
        bits.append(tss_bit)

    headline = " · ".join(bits)
    lines.append(headline)

    drift = report.get("hr_drift")
    if drift and drift.get("hr_drift_pct") is not None:
        drift_line = (
            f"HR drift {drift['hr_drift_pct']:+.1f}% "
            f"({drift.get('first_half_avg_hr')} → {drift.get('second_half_avg_hr')} bpm)"
        )
        notes = drift.get("notes") or []
        if notes:
            drift_line += " — " + "; ".join(notes)
        lines.append(drift_line)

    power = report.get("power_spikes")
    if power:
        pbits = [f"max {power.get('max_watts')}W"]
        if power.get("spike_events") is not None:
            pbits.append(
                f"{power['spike_events']} brief spikes above {power.get('threshold_w')}W"
            )
        if power.get("variability_index") is not None:
            pbits.append(f"VI {power['variability_index']}")
        lines.append("Power: " + ", ".join(str(x) for x in pbits))

    splits = report.get("splits_by_km") or []
    if splits:
        lines.append("Splits:")
        for sp in splits:
            km = sp.get("km")
            pace = sp.get("pace") or "—"
            hr = sp.get("avg_hr")
            flag = " [STOPS]" if sp.get("polluted_by_stops") else ""
            extra = ""
            if sp.get("avg_watts") is not None and _is_ride(str(sport)):
                extra = f", {sp['avg_watts']:.0f}W"
            hr_s = f", HR {hr:.0f}" if hr is not None else ""
            dist_note = ""
            if sp.get("distance_m") is not None and sp["distance_m"] < 950:
                dist_note = f" ({sp['distance_m']:.0f}m)"
            lines.append(f"  km {km}{dist_note}: {pace}{hr_s}{extra}{flag}")

    return "\n".join(lines)
