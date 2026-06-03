"""Central config: env vars, metric registry, goals."""

from __future__ import annotations

import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT / ".env"


def _load_dotenv() -> None:
    if not _ENV_FILE.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_ENV_FILE)
    except ImportError:
        pass


_load_dotenv()

DB_PATH = os.getenv("DB_PATH", "garmin.db")
GARMIN_TOKENSTORE = os.path.expanduser(
    os.getenv("GARMINTOKENS", "~/.garminconnect")
)

DAYS_BACK = int(os.getenv("DAYS_BACK", "3"))
BACKFILL_DAYS = int(os.getenv("BACKFILL_DAYS", "180"))

STEP_GOAL = int(os.getenv("STEP_GOAL", "8000"))
SLEEP_TARGET_HOURS = (
    float(os.getenv("SLEEP_TARGET_HOURS_LOW", "7.0")),
    float(os.getenv("SLEEP_TARGET_HOURS_HIGH", "9.0")),
)
SLEEP_TARGET_SECONDS = (
    int(SLEEP_TARGET_HOURS[0] * 3600),
    int(SLEEP_TARGET_HOURS[1] * 3600),
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_FALLBACK = os.getenv("GEMINI_FALLBACK", "gemini-2.5-flash-lite")

NOTIFIER = (os.getenv("NOTIFIER") or "ntfy").strip().lower()

# All stored fields: label, unit, good direction, short hint for Gemini.
FIELD_META: dict[str, dict[str, str]] = {
    "steps": {
        "label": "Steps",
        "unit": "count",
        "good": "up",
        "hint": "Total steps for the day.",
    },
    "resting_hr": {
        "label": "Resting HR",
        "unit": "bpm",
        "good": "down",
        "hint": "Resting heart rate; lower often reflects better recovery.",
    },
    "sleep_seconds": {
        "label": "Sleep",
        "unit": "h",
        "good": "target",
        "hint": "Total sleep duration; target band from sleep_target_hours.",
    },
    "sleep_score": {
        "label": "Sleep score",
        "unit": "0-100",
        "good": "up",
        "hint": "Garmin sleep quality score.",
    },
    "deep_sleep_seconds": {
        "label": "Deep sleep",
        "unit": "min",
        "good": "up",
        "hint": "Time in deep sleep; supports physical recovery.",
    },
    "rem_sleep_seconds": {
        "label": "REM sleep",
        "unit": "min",
        "good": "up",
        "hint": "REM stage duration; linked to memory and cognitive recovery.",
    },
    "stress_avg": {
        "label": "Avg stress",
        "unit": "0-100",
        "good": "down",
        "hint": "Daily average stress level from Garmin.",
    },
    "body_battery_high": {
        "label": "Body Battery peak",
        "unit": "0-100",
        "good": "up",
        "hint": "Highest Body Battery that day.",
    },
    "body_battery_low": {
        "label": "Body Battery low",
        "unit": "0-100",
        "good": "up",
        "hint": "Lowest Body Battery; very low can mean incomplete recovery.",
    },
    "hrv_avg": {
        "label": "HRV",
        "unit": "ms",
        "good": "up",
        "hint": "Overnight heart rate variability average.",
    },
    "training_readiness": {
        "label": "Training readiness",
        "unit": "0-100",
        "good": "up",
        "hint": "Readiness to train; higher suggests capacity for hard sessions.",
    },
    "intensity_minutes": {
        "label": "Intensity minutes",
        "unit": "min",
        "good": "up",
        "hint": "Moderate minutes plus 2× vigorous minutes.",
    },
    "active_kcal": {
        "label": "Active calories",
        "unit": "kcal",
        "good": "up",
        "hint": "Calories burned from activity (not BMR).",
    },
    "spo2_avg": {
        "label": "SpO2",
        "unit": "%",
        "good": "up",
        "hint": "Average blood oxygen saturation.",
    },
    "weight_grams": {
        "label": "Weight",
        "unit": "kg",
        "good": "target",
        "hint": "Body weight if logged that day.",
    },
    "body_fat_percent": {
        "label": "Body fat",
        "unit": "%",
        "good": "down",
        "hint": "Body fat percentage if logged.",
    },
    "vo2_max": {
        "label": "VO2 max",
        "unit": "ml/kg/min",
        "good": "up",
        "hint": "Cardio fitness estimate from Garmin.",
    },
    "fitness_age": {
        "label": "Fitness age",
        "unit": "years",
        "good": "down",
        "hint": "Garmin fitness age estimate; lower vs chronological age is better.",
    },
}

DAILY_COLUMNS = [
    "day",
    "steps",
    "resting_hr",
    "sleep_seconds",
    "sleep_score",
    "deep_sleep_seconds",
    "rem_sleep_seconds",
    "stress_avg",
    "body_battery_high",
    "body_battery_low",
    "hrv_avg",
    "training_readiness",
    "intensity_minutes",
    "active_kcal",
    "spo2_avg",
    "weight_grams",
    "body_fat_percent",
    "vo2_max",
    "fitness_age",
]


def project_root() -> Path:
    return _ROOT


def db_path() -> Path:
    p = Path(DB_PATH)
    if not p.is_absolute():
        p = project_root() / p
    return p
