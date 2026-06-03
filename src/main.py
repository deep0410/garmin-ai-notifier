"""Daily orchestration: pull → digest → brief → notify."""

from __future__ import annotations

import logging
import sys

from src import db
from src import features
from src import insight
from src import notify
from src import pull

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    errors = pull.run()
    if errors > 1:
        logger.warning("Pull had %d day failures (continuing)", errors)

    rows = db.load_all_days()
    if not rows:
        logger.error("No data in garmin.db — run backfill first")
        return 1

    digest = features.build_digest(rows)
    logger.info(
        "Digest reference_day=%s days=%d",
        digest["reference_day"],
        digest["day_count"],
    )

    brief = insight.generate(digest)
    print(brief)
    notify.send("Daily Garmin Brief", brief)
    logger.info("Notification sent via ntfy")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as err:
        logger.error("Fatal: %s", err)
        raise SystemExit(1) from err
