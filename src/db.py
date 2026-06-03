"""SQLite storage for daily Garmin rows (scalar health metrics only, no raw JSON)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daily (
    day                 TEXT PRIMARY KEY,
    steps               INTEGER,
    resting_hr          INTEGER,
    sleep_seconds       INTEGER,
    sleep_score         INTEGER,
    deep_sleep_seconds  INTEGER,
    rem_sleep_seconds   INTEGER,
    stress_avg          INTEGER,
    body_battery_high   INTEGER,
    body_battery_low    INTEGER,
    hrv_avg             INTEGER,
    training_readiness  INTEGER,
    intensity_minutes   INTEGER,
    active_kcal         INTEGER,
    spo2_avg            INTEGER,
    weight_grams        INTEGER,
    body_fat_percent    INTEGER,
    vo2_max             INTEGER,
    fitness_age         INTEGER
);
"""

_MIGRATIONS: list[tuple[str, str]] = [
    ("body_fat_percent", "INTEGER"),
    ("vo2_max", "INTEGER"),
    ("fitness_age", "INTEGER"),
]


def _connect(path: Path | None = None) -> sqlite3.Connection:
    p = path or config.db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    existing = {row[1] for row in conn.execute("PRAGMA table_info(daily)")}
    if not existing:
        return
    for col, typ in _MIGRATIONS:
        if col not in existing:
            conn.execute(f"ALTER TABLE daily ADD COLUMN {col} {typ}")
    if "raw" in existing:
        try:
            conn.execute("ALTER TABLE daily DROP COLUMN raw")
        except sqlite3.OperationalError:
            conn.execute("UPDATE daily SET raw = NULL")


def init_db(path: Path | None = None) -> None:
    with _connect(path) as conn:
        conn.execute(_SCHEMA)
        _migrate(conn)
        conn.commit()


def upsert_day(row: dict[str, Any], path: Path | None = None) -> None:
    init_db(path)
    values = [row.get(c) for c in config.DAILY_COLUMNS]
    placeholders = ", ".join("?" * len(config.DAILY_COLUMNS))
    col_names = ", ".join(config.DAILY_COLUMNS)
    updates = ", ".join(
        f"{c}=excluded.{c}" for c in config.DAILY_COLUMNS if c != "day"
    )
    sql = f"""
        INSERT INTO daily ({col_names}) VALUES ({placeholders})
        ON CONFLICT(day) DO UPDATE SET {updates}
    """
    with _connect(path) as conn:
        conn.execute(sql, values)
        conn.commit()


def load_all_days(path: Path | None = None) -> list[dict[str, Any]]:
    init_db(path)
    cols = ", ".join(config.DAILY_COLUMNS)
    with _connect(path) as conn:
        rows = conn.execute(
            f"SELECT {cols} FROM daily ORDER BY day ASC"
        ).fetchall()
    return [dict(row) for row in rows]
