"""Scheduled tracking job: take daily P&L snapshots, check exits, send alerts.

Designed to be run as a standalone script after market close::

    python -m jobs.tracking_job

"""

from __future__ import annotations

import asyncio
import logging

from app.alerts.email import GmailAlert
from app.db.database import async_session_factory
from app.db.repositories import thesis_repo
from app.tracking.daily_snapshot import take_daily_snapshots
from app.tracking.scoring import calculate_system_score

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jobs.tracking")


async def main() -> None:
    """Entry point for the scheduled tracking job."""
    logger.info("=== Tracking job starting ===")

    async with async_session_factory() as db:
        # Step 1: Take daily snapshots for all active theses
        snapshot_count = await take_daily_snapshots(db)
        logger.info("Recorded %d daily snapshots", snapshot_count)

        # Step 2: Check for theses that just closed (exit condition met)
        # Re-query to find theses that were closed during snapshotting
        closed_theses = await thesis_repo.list_theses(db, is_active=False, limit=500)

        alert = GmailAlert()
        newly_closed = []

        for thesis in closed_theses:
            if thesis.status in ("closed_target", "closed_stop", "closed_expiry"):
                # Check if system score exists; if not, this was just closed
                existing_score = await thesis_repo.get_system_score(db, thesis.id)
                if existing_score is None:
                    newly_closed.append(thesis)

                    # Calculate system score
                    try:
                        await calculate_system_score(thesis.id, db)
                    except Exception:
                        logger.exception(
                            "Failed to score thesis %s (%s)", thesis.id, thesis.ticker
                        )

                    # Send exit alert
                    try:
                        alert.send_exit_alert(thesis, thesis.status)
                    except Exception:
                        logger.exception(
                            "Failed to send exit alert for %s", thesis.ticker
                        )

        await db.commit()

    logger.info(
        "Tracking job complete: %d snapshots, %d newly closed theses",
        snapshot_count,
        len(newly_closed),
    )
    logger.info("=== Tracking job complete ===")


if __name__ == "__main__":
    asyncio.run(main())
