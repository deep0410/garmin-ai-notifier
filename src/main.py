"""Daily orchestration: pull → digest → brief → notify."""

from __future__ import annotations

import logging
import sys

from src import analysis
from src import db
from src import garmin_client
from src import insight
from src import notify
from src import pull

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> int:
    api = garmin_client.login()

    errors = pull.run(api)
    if errors > 1:
        logger.warning("Pull had %d day failures (continuing)", errors)

    profile = None
    try:
        profile = garmin_client.fetch_profile(api)
    except Exception as err:  # noqa: BLE001 - profile is optional context
        logger.warning("Profile fetch failed (continuing without it): %s", err)

    rows = db.load_all_days()
    if not rows:
        logger.error("No data in garmin.db — run backfill first")
        return 1

    report = analysis.build_feature_report(rows, profile=profile)
    logger.info(
        "Feature report reference_day=%s window=%s domains=%d",
        report.get("reference_day"),
        report.get("history_span"),
        len(report.get("domains", {})),
    )

    brief = insight.generate(report)
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
