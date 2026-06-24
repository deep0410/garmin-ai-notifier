"""Format Garmin history for Gemini (no precomputed stats)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from src import config


def _time_context() -> dict[str, Any]:
    """Local clock context so the brief knows it's morning and today is still unfolding."""
    now = datetime.now()
    hour = now.hour
    if hour < 5:
        tod = "overnight"
    elif hour < 11:
        tod = "morning"
    elif hour < 17:
        tod = "afternoon"
    else:
        tod = "evening"
    return {
        "now_local": now.isoformat(timespec="minutes"),
        "hour_local": hour,
        "time_of_day": tod,
    }


def _display_value(key: str, val: Any) -> Any:
    if val is None:
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return val
    if key == "sleep_seconds":
        return round(n / 3600, 2)
    if key in ("deep_sleep_seconds", "rem_sleep_seconds", "light_sleep_seconds"):
        return round(n / 60, 1)
    if key == "weight_grams":
        return round(n / 1000, 2)
    if key.endswith("_seconds"):
        return int(n)
    return int(n) if n == int(n) else round(n, 2)


def _format_day(row: dict[str, Any]) -> dict[str, Any]:
    """Every DB column for this day — null stays null so nothing is hidden."""
    out: dict[str, Any] = {"date": row.get("day")}
    for key in config.DAILY_COLUMNS:
        if key == "day":
            continue
        meta = config.FIELD_META[key]
        unit = meta.get("unit", "")
        label = meta["label"]
        key_label = f"{label} ({unit})" if unit else label
        raw = row.get(key)
        out[key_label] = _display_value(key, raw) if raw is not None else None
    return out


def _has_overnight_sleep(row: dict[str, Any]) -> bool:
    return row.get("sleep_seconds") is not None


def _resolve_reference_day(rows: list[dict[str, Any]]) -> str:
    """Wake-up day for last night — Garmin stores that sleep on calendar today."""
    today = date.today().isoformat()
    by_day = {r["day"]: r for r in rows}

    if today in by_day and _has_overnight_sleep(by_day[today]):
        return today

    for r in reversed(rows):
        if _has_overnight_sleep(r):
            return r["day"]

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if yesterday in by_day:
        return yesterday
    for r in reversed(rows):
        if any(r.get(k) is not None for k in config.FIELD_META):
            return r["day"]
    return rows[-1]["day"] if rows else yesterday


def _metrics_guide() -> dict[str, Any]:
    guide: dict[str, Any] = {}
    for key, meta in config.FIELD_META.items():
        guide[key] = {
            "label": meta["label"],
            "unit": meta["unit"],
            "good_direction": meta["good"],
            "hint": meta["hint"],
        }
    return guide


def build_digest(
    rows: list[dict[str, Any]], profile: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Pass full daily history + field guide; Gemini does all interpretation."""
    today = date.today().isoformat()
    if not rows:
        ref = (date.today() - timedelta(days=1)).isoformat()
        return {
            "today": today,
            **_time_context(),
            "profile": profile or {},
            "reference_day": ref,
            "reference_day_is_today": ref == today,
            "note": "no_data",
            "goals": {
                "steps": config.STEP_GOAL,
                "sleep_hours": list(config.SLEEP_TARGET_HOURS),
            },
            "metrics_guide": _metrics_guide(),
            "daily_history": [],
            "day_count": 0,
        }

    today = date.today().isoformat()
    ref = _resolve_reference_day(rows)
    ref_is_today = ref == today
    return {
        "today": today,
        **_time_context(),
        "profile": profile or {},
        "reference_day": ref,
        "reference_day_is_today": ref_is_today,
        "note": (
            "Calendar today is `today`. `reference_day` is the Garmin wake-up date for last night "
            "(usually equals today once sleep is synced). "
            "Overnight metrics on reference_day: sleep, HRV, stress, REM, deep sleep, resting HR, "
            "body battery, training readiness, SpO2 — compare these across daily_history. "
            "Activity metrics (steps, intensity minutes, active calories) on a row where date equals "
            "today are PARTIAL (day still in progress). Never call them 'yesterday' or rank them "
            "against full prior days. For steps/WATCH, use only completed days (date < today) or "
            "say 'so far today' with no 'lowest/highest in history' unless day_count is large. "
            "With day_count under 14, say 'best in your N stored days' never 'personal best' or "
            "'on record'. null = no value that day."
        ),
        "goals": {
            "steps": config.STEP_GOAL,
            "sleep_hours": list(config.SLEEP_TARGET_HOURS),
        },
        "metrics_guide": _metrics_guide(),
        "day_count": len(rows),
        "daily_history": [_format_day(r) for r in rows],
    }
