"""Nightly job logic: pull closing prices and record P&L snapshots for open theses."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.polygon_client import PolygonClient
from app.db.repositories import thesis_repo
from app.tracking.exit_conditions import check_exit_conditions

logger = logging.getLogger(__name__)


async def take_daily_snapshots(db_session: AsyncSession) -> int:
    """Pull closing prices and record a P&L snapshot for every active thesis.

    For each thesis with ``status == 'active'``:
      1. Fetch the latest daily close from Polygon for the underlying ticker.
      2. Estimate the current spread mark-to-market from entry price and
         underlying movement (a simplified model -- full options re-pricing
         would require live greeks).
      3. Compute dollar and percent P&L relative to entry.
      4. Check exit conditions (profit target, stop loss, expiration).
      5. Persist the snapshot via ``thesis_repo.create_snapshot``.

    Returns the number of snapshots created.
    """
    active_theses = await thesis_repo.list_theses(
        db_session, status="active", is_active=True, limit=500,
    )

    if not active_theses:
        logger.info("No active theses to snapshot")
        return 0

    today = date.today()
    count = 0

    async with PolygonClient() as polygon:
        for thesis in active_theses:
            try:
                bars = await polygon.get_ohlc_history(thesis.ticker, days=5)
                if not bars:
                    logger.warning("No OHLC data for %s -- skipping", thesis.ticker)
                    continue

                underlying_close = bars[-1].get("c", 0.0)

                # Simplified mark-to-market: estimate spread value from
                # directional movement of the underlying relative to strikes.
                spread_mark = _estimate_spread_mark(thesis, underlying_close)

                # P&L = difference between current mark and entry credit/debit
                pnl_dollars = thesis.entry_price - spread_mark
                pnl_percent = (pnl_dollars / abs(thesis.max_loss)) * 100 if thesis.max_loss else 0.0

                # Check exit conditions
                snapshot_data = {
                    "thesis_id": thesis.id,
                    "snapshot_date": today,
                    "underlying_close": underlying_close,
                    "spread_mark": spread_mark,
                    "pnl_dollars": round(pnl_dollars, 2),
                    "pnl_percent": round(pnl_percent, 2),
                }

                exit_condition = check_exit_conditions(thesis, snapshot_data)
                if exit_condition:
                    snapshot_data["exit_condition_met"] = exit_condition

                await thesis_repo.create_snapshot(db_session, **snapshot_data)
                count += 1

                # If an exit condition was met, update thesis status
                if exit_condition:
                    from datetime import datetime, timezone

                    await thesis_repo.update_thesis_status(
                        db_session,
                        thesis.id,
                        status=exit_condition,
                        is_active=False,
                        closed_at=datetime.now(timezone.utc),
                    )
                    logger.info(
                        "Thesis %s for %s closed: %s",
                        thesis.id, thesis.ticker, exit_condition,
                    )

            except Exception:
                logger.exception("Failed to snapshot thesis %s (%s)", thesis.id, thesis.ticker)
                continue

    await db_session.commit()
    logger.info("Daily snapshots complete: %d snapshots recorded", count)
    return count


def _estimate_spread_mark(thesis, underlying_close: float) -> float:
    """Estimate the current spread mark-to-market.

    Uses a simple linear interpolation between max profit and max loss
    based on how far the underlying has moved relative to the spread strikes.
    This is a rough approximation; a production system would re-price
    using Black-Scholes or live option quotes.
    """
    width = abs(thesis.long_strike - thesis.short_strike)
    if width == 0:
        return thesis.entry_price

    if thesis.direction == "bullish":
        # Bull put spread: profitable when underlying stays above short strike
        if underlying_close >= thesis.short_strike:
            # Full profit zone
            return 0.0
        elif underlying_close <= thesis.long_strike:
            # Full loss zone
            return width
        else:
            # Linear interpolation
            ratio = (thesis.short_strike - underlying_close) / width
            return width * ratio
    else:
        # Bear call spread: profitable when underlying stays below short strike
        if underlying_close <= thesis.short_strike:
            return 0.0
        elif underlying_close >= thesis.long_strike:
            return width
        else:
            ratio = (underlying_close - thesis.short_strike) / width
            return width * ratio
