"""Central config: env vars, metric registry, goals."""

from __future__ import annotations

import os
from pathlib import Path

DB_PATH = os.getenv("DB_PATH", "garmin.db")
GARMIN_TOKENSTORE = os.path.expanduser(
    os.getenv("GARMINTOKENS", "~/.garminconnect")
)

DAYS_BACK = int(os.getenv("DAYS_BACK", "3"))
BACKFILL_DAYS = int(os.getenv("BACKFILL_DAYS", "400"))

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

NOTIFIER = os.getenv("NOTIFIER", "ntfy").lower()

MIN_HISTORY_DAYS = 14

METRICS: dict[str, dict[str, str]] = {
    "steps": {"label": "Steps", "unit": "", "good": "up"},
    "resting_hr": {"label": "Resting HR", "unit": "bpm", "good": "down"},
    "sleep_seconds": {"label": "Sleep", "unit": "h", "good": "target"},
    "sleep_score": {"label": "Sleep score", "unit": "", "good": "up"},
    "stress_avg": {"label": "Avg stress", "unit": "", "good": "down"},
    "body_battery_high": {"label": "Body Battery peak", "unit": "", "good": "up"},
    "hrv_avg": {"label": "HRV", "unit": "ms", "good": "up"},
    "training_readiness": {
        "label": "Training readiness",
        "unit": "",
        "good": "up",
    },
    "intensity_minutes": {"label": "Intensity minutes", "unit": "min", "good": "up"},
    "spo2_avg": {"label": "SpO2", "unit": "%", "good": "up"},
    "vo2_max": {"label": "VO2 max", "unit": "ml/kg/min", "good": "up"},
    "fitness_age": {"label": "Fitness age", "unit": "yr", "good": "down"},
    "body_fat_percent": {"label": "Body fat", "unit": "%", "good": "down"},
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
    return Path(__file__).resolve().parent.parent


def db_path() -> Path:
    p = Path(DB_PATH)
    if not p.is_absolute():
        p = project_root() / p
    return p
