"""One-time historical backfill into garmin.db."""

from __future__ import annotations

import logging
import random
import time
from datetime import date, timedelta

from src import config
from src import db
from src import garmin_client

logger = logging.getLogger(__name__)


def run() -> None:
    db.init_db()
    api = garmin_client.login()
    today = date.today()
    total = config.BACKFILL_DAYS
    ok = 0
    for i in range(total):
        d = today - timedelta(days=i)
        iso = d.isoformat()
        try:
            row = garmin_client.fetch_day(api, iso)
            db.upsert_day(row)
            ok += 1
            if (i + 1) % 10 == 0 or i == 0:
                logger.info("Backfill %d/%d — %s ok", i + 1, total, iso)
        except Exception as err:
            logger.warning("Skip %s: %s", iso, err)
        time.sleep(1.0 + random.random() * 0.5)
    logger.info("Backfill done: %d/%d days written", ok, total)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
