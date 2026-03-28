"""Scheduled discovery job: run screener, batch analysis, email results.

Designed to be run as a standalone script via cron or a task scheduler::

    python -m jobs.discovery_job

"""

from __future__ import annotations

import asyncio
import logging
import sys

from app.alerts.email import GmailAlert
from app.config import get_settings
from app.db.database import async_session_factory
from app.db.repositories import thesis_repo
from app.graph.builder import analysis_graph
from app.models.screener import ScreenerFilters
from app.models.state import AnalysisState
from app.screener.runner import run_screener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("jobs.discovery")

MAX_CONCURRENT = 5


async def _analyse_candidate(ticker: str) -> dict | None:
    """Run the analysis graph for a single ticker."""
    try:
        state = AnalysisState(ticker=ticker, flow_type="scheduled_discovery")
        result = await analysis_graph.ainvoke(state.model_dump())
        return result
    except Exception:
        logger.exception("Analysis failed for %s", ticker)
        return None


async def main() -> None:
    """Entry point for the scheduled discovery job."""
    logger.info("=== Discovery job starting ===")

    # Step 1: Run screener with default filters
    filters = ScreenerFilters()
    screener_result = await run_screener(filters)
    candidates = screener_result.candidates
    logger.info("Screener returned %d candidates", len(candidates))

    if not candidates:
        logger.info("No candidates found -- exiting")
        return

    # Step 2: Run analysis graph for each candidate concurrently
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)

    async def _limited(ticker: str):
        async with semaphore:
            return await _analyse_candidate(ticker)

    tasks = [_limited(c.ticker) for c in candidates]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = [r for r in results if r is not None and not isinstance(r, Exception)]
    logger.info("Analysis complete: %d/%d successful", len(successful), len(candidates))

    # Step 3: Fetch today's generated theses for the email
    from datetime import datetime, timezone

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session_factory() as db:
        from sqlalchemy import select
        from app.models.thesis import Thesis

        stmt = (
            select(Thesis)
            .where(Thesis.created_at >= today_start)
            .order_by(Thesis.confidence.desc())
        )
        result = await db.execute(stmt)
        theses = result.scalars().all()

    logger.info("Found %d theses from today's run", len(theses))

    # Step 4: Email results
    if theses:
        try:
            alert = GmailAlert()
            alert.send_discovery_results(theses)
        except Exception:
            logger.exception("Failed to send discovery email")

    logger.info("=== Discovery job complete ===")


if __name__ == "__main__":
    asyncio.run(main())
