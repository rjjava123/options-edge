"""Screener orchestration: batch universe filter -> apply filter funnel -> return candidates."""

from __future__ import annotations

import logging
from datetime import datetime

from app.data.polygon_client import PolygonClient
from app.models.screener import ScreenerFilters, ScreenerResult
from app.screener.filters import (
    iv_rank_filter,
    liquidity_filter,
    technical_momentum_filter,
    universe_filter,
    unusual_activity_filter,
)

logger = logging.getLogger(__name__)


async def run_screener(config: ScreenerFilters) -> ScreenerResult:
    """Execute the full screener pipeline and return qualifying candidates.

    Steps
    -----
    1. **Universe filter** — single ``get_grouped_daily()`` API call returns
       one bar per ticker for the entire US market.  Applies price and stock
       volume gates in-memory to reduce ~10 000 tickers down to ~1 000-2 000.
    2. **Liquidity filter** — options volume + bid-ask spread (batched).
    3. **IV rank filter** — 30-80 rank sweet spot by default.
    4. **Unusual activity filter** — volume/OI ratio.
    5. **Technical momentum filter** — RSI + EMA alignment.

    Each filter narrows the funnel.  The final candidates are returned in a
    :class:`ScreenerResult`.
    """
    async with PolygonClient() as client:
        # Step 1 -- Universe (single API call for all tickers)
        logger.info("Running universe filter (grouped daily)...")
        candidates = await universe_filter(config, client=client)
        total_screened = len(candidates)
        logger.info("Universe filter: %d candidates", total_screened)

        # Step 2 -- Liquidity
        logger.info("Running liquidity filter...")
        candidates = await liquidity_filter(candidates, config, client)

        # Step 3 -- IV rank
        logger.info("Running IV rank filter...")
        candidates = await iv_rank_filter(candidates, config, client)

        # Step 4 -- Unusual activity
        logger.info("Running unusual activity filter...")
        candidates = await unusual_activity_filter(candidates, config, client)

        # Step 5 -- Technical momentum
        logger.info("Running technical momentum filter...")
        candidates = await technical_momentum_filter(candidates, config, client)

        logger.info(
            "Screener complete: %d candidates from %d screened",
            len(candidates),
            total_screened,
        )

    return ScreenerResult(
        candidates=candidates,
        total_screened=total_screened,
        timestamp=datetime.utcnow(),
    )
