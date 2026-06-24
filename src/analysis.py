"""Deterministic feature engine.

Crunches the full daily history (180+ days) into a compact, per-metric statistical
summary grouped by domain. This is what lets the brief actually *use* all the history:
the math (means, trends, percentiles, significance) happens here in code — reliable and
hallucination-proof — so the LLM only ever sees a small, already-interpreted report.
"""

from __future__ import annotations

import statistics
from typing import Any

from src import config
from src.features import _display_value, _resolve_reference_day, _time_context
from datetime import date

# Metrics measured overnight → anchor to last night's (reference_day) value.
OVERNIGHT = {
    "sleep_seconds", "sleep_score", "deep_sleep_seconds", "rem_sleep_seconds",
    "light_sleep_seconds", "awake_count", "avg_sleep_stress", "respiration_avg",
    "hrv_avg", "hrv_status", "resting_hr", "body_battery_high", "body_battery_low",
    "spo2_avg", "training_readiness",
}

# Display order / grouping for the report the LLM reads.
DOMAINS: dict[str, list[str]] = {
    "recovery": [
        "hrv_avg", "hrv_status", "body_battery_high", "body_battery_low",
        "resting_hr", "training_readiness",
    ],
    "sleep": [
        "sleep_seconds", "sleep_score", "deep_sleep_seconds", "rem_sleep_seconds",
        "light_sleep_seconds", "awake_count", "avg_sleep_stress", "respiration_avg",
    ],
    "stress": ["stress_avg", "stress_max"],
    "activity": ["steps", "intensity_minutes", "floors_climbed", "active_kcal"],
    "fitness": ["vo2_max", "fitness_age"],
    "body": ["weight_grams", "body_fat_percent", "spo2_avg"],
}

_Z_THRESHOLD = 0.8


def _num(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _rnd(x: Any) -> Any:
    return round(x, 1) if isinstance(x, float) else x


def _series(rows: list[dict[str, Any]], key: str) -> list[tuple[str, Any]]:
    """Chronological (date, display_value) pairs where value is present."""
    out: list[tuple[str, Any]] = []
    for r in rows:
        v = r.get(key)
        if v is None:
            continue
        out.append((r["day"], _display_value(key, v)))
    return out


def _signal(good: str, z: float | None, in_band: bool | None, status_ok: bool | None) -> str:
    if good == "status":
        return "good" if status_ok else "watch"
    if good == "target":
        if in_band is None:
            return "neutral"
        return "good" if in_band else "watch"
    if z is None:
        return "neutral"
    if good == "up":
        if z >= _Z_THRESHOLD:
            return "good"
        if z <= -_Z_THRESHOLD:
            return "watch"
    if good == "down":
        if z <= -_Z_THRESHOLD:
            return "good"
        if z >= _Z_THRESHOLD:
            return "watch"
    return "neutral"


def _metric_summary(
    key: str, rows: list[dict[str, Any]], reference_day: str, today: str,
    sleep_band: tuple[float, float],
) -> dict[str, Any] | None:
    meta = config.FIELD_META[key]
    good, unit, label = meta["good"], meta["unit"], meta["label"]
    series = _series(rows, key)
    if not series:
        return None

    by_day = dict(series)
    is_overnight = key in OVERNIGHT

    # anchor = the value we report on now
    if is_overnight:
        anchor_day = reference_day if reference_day in by_day else series[-1][0]
    else:
        completed = [(d, v) for d, v in series if d < today]
        anchor_day = completed[-1][0] if completed else series[-1][0]
    anchor = by_day.get(anchor_day)

    out: dict[str, Any] = {
        "value": _rnd(anchor),
        "unit": unit,
        "good_direction": good,
        "on": anchor_day,
    }
    if not is_overnight and reference_day == today and today in by_day:
        out["today_partial"] = _rnd(by_day[today])

    # status (text) metric, e.g. HRV status
    if good == "status":
        out["signal"] = _signal(good, None, None, str(anchor).upper() == "BALANCED")
        return out

    if not _num(anchor):
        out["signal"] = "neutral"
        return out

    # baseline = prior values, excluding the anchor day itself and any partial today
    base = [v for d, v in series if _num(v) and d != anchor_day and d <= today]
    base = [v for v in base if v is not None]
    z = None
    if len(base) >= 1:
        recent = base[-30:]
        mean30 = statistics.fmean(recent)
        out["avg_30d"] = round(mean30, 1)
        if mean30:
            out["pct_vs_30d"] = round((anchor - mean30) / mean30 * 100)
        if len(recent) >= 3:
            sd = statistics.pstdev(recent)
            if sd > 0:
                z = round((anchor - mean30) / sd, 2)
                out["z"] = z
        pr = sum(1 for v in base if v <= anchor) / len(base)
        out["percentile"] = round(pr * 100)
        if anchor >= max(base):
            out["extreme"] = "highest in history"
        elif anchor <= min(base):
            out["extreme"] = "lowest in history"

    in_band = None
    if key == "sleep_seconds":
        in_band = sleep_band[0] <= anchor <= sleep_band[1]
        out["goal_band_h"] = list(sleep_band)
    out["signal"] = _signal(good, z, in_band, None)
    return out


def build_feature_report(
    rows: list[dict[str, Any]], profile: dict[str, Any] | None = None
) -> dict[str, Any]:
    today = date.today().isoformat()
    base: dict[str, Any] = {
        "today": today,
        **_time_context(),
        "profile": profile or {},
        "goals": {
            "steps": config.STEP_GOAL,
            "sleep_hours": list(config.SLEEP_TARGET_HOURS),
        },
    }
    if not rows:
        base.update({"reference_day": today, "reference_day_is_today": True,
                     "note": "no_data", "domains": {}, "no_data_metrics": []})
        return base

    # analyze only the most recent window (older days stay stored, just not scored)
    if config.HISTORY_DAYS > 0:
        rows = rows[-config.HISTORY_DAYS:]

    ref = _resolve_reference_day(rows)
    base["reference_day"] = ref
    base["reference_day_is_today"] = ref == today
    base["history_span"] = {"from": rows[0]["day"], "to": rows[-1]["day"]}

    domains: dict[str, Any] = {}
    no_data: list[str] = []
    for domain, keys in DOMAINS.items():
        block: dict[str, Any] = {}
        for key in keys:
            s = _metric_summary(key, rows, ref, today, config.SLEEP_TARGET_HOURS)
            if s is None:
                no_data.append(config.FIELD_META[key]["label"])
            else:
                block[config.FIELD_META[key]["label"]] = s
        if block:
            domains[domain] = block
    base["domains"] = domains
    base["no_data_metrics"] = no_data
    return base
