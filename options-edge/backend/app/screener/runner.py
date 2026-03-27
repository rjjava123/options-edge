"""Screener orchestration: fetch universe -> apply filter funnel -> return candidates."""

from __future__ import annotations

import logging
from datetime import datetime

from app.data.polygon_client import PolygonClient
from app.models.screener import ScreenerFilters, ScreenerResult
from app.screener.filters import (
    iv_rank_filter,
    liquidity_filter,
    technical_momentum_filter,
    unusual_activity_filter,
)
from app.screener.universe import fetch_optionable_universe

logger = logging.getLogger(__name__)


async def run_screener(config: ScreenerFilters) -> ScreenerResult:
    """Execute the full screener pipeline and return qualifying candidates.

    Steps
    -----
    1. Fetch the optionable universe from Polygon (~3,000-4,000 tickers).
    2. Apply liquidity filter (options volume + bid-ask spread).
    3. Apply IV rank filter (30-80 rank sweet spot by default).
    4. Apply unusual activity filter (volume/OI ratio).
    5. Apply technical momentum filter (RSI + EMA alignment).

    Each filter narrows the funnel.  The final candidates are returned in a
    :class:`ScreenerResult`.
    """
    async with PolygonClient() as client:
        # Step 1 -- Universe
        logger.info("Fetching optionable universe...")
        universe = await fetch_optionable_universe(client)
        total_screened = len(universe)
        logger.info("Universe size: %d tickers", total_screened)

        # Optional price / market-cap pre-filter from config
        if config.min_price is not None or config.max_price is not None:
            filtered: list[str] = []
            for ticker in universe:
                try:
                    bars = await client.get_ohlc_history(ticker, days=5)
                    if not bars:
                        continue
                    last_close = bars[-1].get("c", 0)
                    if config.min_price and last_close < config.min_price:
                        continue
                    if config.max_price and last_close > config.max_price:
                        continue
                    filtered.append(ticker)
                except Exception:
                    continue
            universe = filtered
            logger.info("After price filter: %d tickers", len(universe))

        # Step 2 -- Liquidity
        logger.info("Running liquidity filter...")
        candidates = await liquidity_filter(universe, config, client)

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
