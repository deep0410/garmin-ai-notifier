"""Format Garmin history for Gemini (no precomputed stats)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from src import config


def _display_value(key: str, val: Any) -> Any:
    if val is None:
        return None
    try:
        n = float(val)
    except (TypeError, ValueError):
        return val
    if key == "sleep_seconds":
        return round(n / 3600, 2)
    if key in ("deep_sleep_seconds", "rem_sleep_seconds"):
        return round(n / 60, 1)
    if key == "weight_grams":
        return round(n / 1000, 2)
    if key.endswith("_seconds"):
        return int(n)
    return int(n) if n == int(n) else round(n, 2)


def _format_day(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"date": row.get("day")}
    for key in config.DAILY_COLUMNS:
        if key == "day" or row.get(key) is None:
            continue
        meta = config.FIELD_META[key]
        unit = meta.get("unit", "")
        label = meta["label"]
        key_label = f"{label} ({unit})" if unit else label
        out[key_label] = _display_value(key, row[key])
    return out


def _resolve_reference_day(rows: list[dict[str, Any]]) -> str:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    days = {r["day"] for r in rows}
    if yesterday in days:
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


def build_digest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pass full daily history + field guide; Gemini does all interpretation."""
    if not rows:
        ref = (date.today() - timedelta(days=1)).isoformat()
        return {
            "reference_day": ref,
            "note": "no_data",
            "goals": {
                "steps": config.STEP_GOAL,
                "sleep_hours": list(config.SLEEP_TARGET_HOURS),
            },
            "metrics_guide": _metrics_guide(),
            "daily_history": [],
            "day_count": 0,
        }

    ref = _resolve_reference_day(rows)
    return {
        "reference_day": ref,
        "note": "Write the brief for reference_day. Compare against full daily_history.",
        "goals": {
            "steps": config.STEP_GOAL,
            "sleep_hours": list(config.SLEEP_TARGET_HOURS),
        },
        "metrics_guide": _metrics_guide(),
        "day_count": len(rows),
        "daily_history": [_format_day(r) for r in rows],
    }
