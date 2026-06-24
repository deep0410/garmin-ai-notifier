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
    "light_sleep_seconds": {
        "label": "Light sleep",
        "unit": "min",
        "good": "target",
        "hint": "Time in light sleep; the bulk of a normal night.",
    },
    "awake_count": {
        "label": "Awakenings",
        "unit": "count",
        "good": "down",
        "hint": "Number of times awake during the night; fewer is more consolidated sleep.",
    },
    "avg_sleep_stress": {
        "label": "Sleep stress",
        "unit": "0-100",
        "good": "down",
        "hint": "Average stress level during sleep; lower means a more restful night.",
    },
    "respiration_avg": {
        "label": "Respiration",
        "unit": "brpm",
        "good": "down",
        "hint": "Average overnight breaths per minute; a stable low rate often reflects recovery.",
    },
    "stress_avg": {
        "label": "Avg stress",
        "unit": "0-100",
        "good": "down",
        "hint": "Daily average stress level from Garmin.",
    },
    "stress_max": {
        "label": "Peak stress",
        "unit": "0-100",
        "good": "down",
        "hint": "Highest stress reading that day; a high peak can signal a hard moment.",
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
    "hrv_status": {
        "label": "HRV status",
        "unit": "",
        "good": "status",
        "hint": "HRV vs your personal baseline: BALANCED is good; LOW/UNBALANCED can mean stress, illness, or overtraining.",
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
    "floors_climbed": {
        "label": "Floors climbed",
        "unit": "count",
        "good": "up",
        "hint": "Floors ascended that day.",
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
    "light_sleep_seconds",
    "awake_count",
    "avg_sleep_stress",
    "respiration_avg",
    "stress_avg",
    "stress_max",
    "body_battery_high",
    "body_battery_low",
    "hrv_avg",
    "hrv_status",
    "training_readiness",
    "intensity_minutes",
    "floors_climbed",
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
