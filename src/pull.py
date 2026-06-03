"""Incremental daily upsert for recent days."""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

from src import config
from src import db
from src import garmin_client

logger = logging.getLogger(__name__)


def run() -> int:
    api = garmin_client.login()
    today = date.today()
    errors = 0
    for i in range(config.DAYS_BACK + 1):
        d = today - timedelta(days=i)
        iso = d.isoformat()
        try:
            row = garmin_client.fetch_day(api, iso)
            db.upsert_day(row)
            logger.info("Upserted %s", iso)
        except Exception as err:
            errors += 1
            logger.error("Failed %s: %s", iso, err)
        if i < config.DAYS_BACK:
            time.sleep(1)
    return errors


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(0 if run() <= 1 else 1)
