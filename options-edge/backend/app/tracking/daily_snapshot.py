"""Nightly job logic: pull actual option contract prices and record P&L snapshots."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.polygon_client import PolygonClient
from app.db.repositories import thesis_repo
from app.tracking.exit_conditions import check_exit_conditions

logger = logging.getLogger(__name__)


async def take_daily_snapshots(db_session: AsyncSession) -> int:
    """Pull actual contract prices and record a P&L snapshot for every active thesis.

    For each thesis with ``status == 'active'``:
      1. Fetch the latest daily close from Polygon for the underlying ticker.
      2. Fetch actual option contract daily bars for both spread legs using
         ``get_option_contract_daily_bars()`` to get real closing prices.
      3. Mark-to-market the spread from actual contract prices (falling back
         to a simplified model if contract bars are unavailable).
      4. Compute dollar and percent P&L relative to entry.
      5. Check exit conditions (profit target, stop loss, expiration).
      6. Persist the snapshot via ``thesis_repo.create_snapshot``.

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
                # -- Underlying close -----------------------------------------
                bars = await polygon.get_daily_bars(thesis.ticker, days=5)
                if not bars:
                    logger.warning("No OHLC data for %s -- skipping", thesis.ticker)
                    continue

                underlying_close = bars[-1].get("c", 0.0)

                # -- Actual option contract prices ----------------------------
                spread_mark = await _mark_spread_from_contracts(
                    polygon, thesis, underlying_close
                )

                # P&L = difference between current mark and entry credit/debit
                pnl_dollars = thesis.entry_price - spread_mark
                pnl_percent = (
                    (pnl_dollars / abs(thesis.max_loss)) * 100
                    if thesis.max_loss
                    else 0.0
                )

                # Build snapshot record
                snapshot_data = {
                    "thesis_id": thesis.id,
                    "snapshot_date": today,
                    "underlying_close": underlying_close,
                    "spread_mark": round(spread_mark, 4),
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
                        thesis.id,
                        thesis.ticker,
                        exit_condition,
                    )

            except Exception:
                logger.exception(
                    "Failed to snapshot thesis %s (%s)",
                    thesis.id,
                    thesis.ticker,
                )
                continue

    await db_session.commit()
    logger.info("Daily snapshots complete: %d snapshots recorded", count)
    return count


# ------------------------------------------------------------------
# Contract-level mark-to-market
# ------------------------------------------------------------------


async def _mark_spread_from_contracts(
    polygon: PolygonClient,
    thesis,
    underlying_close: float,
) -> float:
    """Mark-to-market using actual option contract closing prices.

    Attempts to pull daily bars for each leg's OCC-style contract ticker
    using ``get_option_contract_daily_bars()``.  If both legs have data, the
    spread mark is the net of the two closing prices.  If contract data is
    unavailable (expired, illiquid, etc.), falls back to a simplified
    directional model.
    """
    state_snapshot: dict = getattr(thesis, "state_snapshot", None) or {}

    # Try to reconstruct contract tickers from thesis data
    short_contract = _build_contract_ticker(
        thesis.ticker,
        thesis.expiration_date,
        thesis.short_strike,
        thesis.direction,
        is_short=True,
    )
    long_contract = _build_contract_ticker(
        thesis.ticker,
        thesis.expiration_date,
        thesis.long_strike,
        thesis.direction,
        is_short=False,
    )

    short_close: float | None = None
    long_close: float | None = None

    # Fetch actual contract bars
    if short_contract:
        try:
            short_bars = await polygon.get_option_contract_daily_bars(
                short_contract, days=5
            )
            if short_bars:
                short_close = short_bars[-1].get("c", None)
        except Exception:
            logger.debug(
                "Could not fetch bars for short leg %s", short_contract
            )

    if long_contract:
        try:
            long_bars = await polygon.get_option_contract_daily_bars(
                long_contract, days=5
            )
            if long_bars:
                long_close = long_bars[-1].get("c", None)
        except Exception:
            logger.debug(
                "Could not fetch bars for long leg %s", long_contract
            )

    # If we have both leg prices, compute actual spread mark
    if short_close is not None and long_close is not None:
        # For credit spreads: mark = short_close - long_close
        # For debit spreads: mark = long_close - short_close
        if thesis.spread_type in (
            "bull put spread",
            "bear call spread",
            "iron condor",
        ):
            # Credit spread: we sold the short, bought the long
            spread_mark = short_close - long_close
        else:
            # Debit spread: we bought the long, sold the short
            spread_mark = long_close - short_close

        logger.debug(
            "Contract-level mark for %s: short=%.4f, long=%.4f, spread=%.4f",
            thesis.ticker,
            short_close,
            long_close,
            spread_mark,
        )
        return max(spread_mark, 0.0)

    # Fallback: simplified directional model
    logger.debug(
        "Falling back to directional model for %s (contract data unavailable)",
        thesis.ticker,
    )
    return _estimate_spread_mark_fallback(thesis, underlying_close)


def _build_contract_ticker(
    underlying: str,
    expiration_date: str,
    strike: float,
    direction: str,
    *,
    is_short: bool,
) -> str | None:
    """Build an OCC-style option contract ticker.

    Format: ``O:{UNDERLYING}{YYMMDD}{C|P}{STRIKE*1000:08d}``

    For a bull put spread (bullish credit spread):
      - Short leg = put at higher strike
      - Long leg = put at lower strike

    For a bear call spread (bearish credit spread):
      - Short leg = call at lower strike
      - Long leg = call at higher strike
    """
    if not expiration_date or strike <= 0:
        return None

    try:
        # Parse expiration: expected YYYY-MM-DD
        parts = expiration_date.split("-")
        yy = parts[0][2:]  # last 2 digits of year
        mm = parts[1]
        dd = parts[2]
        date_part = f"{yy}{mm}{dd}"
    except (IndexError, ValueError):
        return None

    # Determine option type from spread direction
    if direction == "bullish":
        option_type = "P"  # bull put spread
    elif direction == "bearish":
        option_type = "C"  # bear call spread
    else:
        # For neutral strategies like iron condors, determine from position
        option_type = "P" if is_short else "C"

    strike_int = int(strike * 1000)

    return f"O:{underlying.upper()}{date_part}{option_type}{strike_int:08d}"


def _estimate_spread_mark_fallback(thesis, underlying_close: float) -> float:
    """Fallback: estimate spread mark from underlying price movement.

    Uses a simplified directional model when actual contract bars are
    unavailable.  This is less accurate than actual contract prices but
    provides a reasonable approximation for P&L tracking.
    """
    width = abs(thesis.long_strike - thesis.short_strike)
    if width == 0:
        return thesis.entry_price

    if thesis.direction == "bullish":
        # Bull put spread: profitable when underlying stays above short strike
        if underlying_close >= thesis.short_strike:
            return 0.0
        elif underlying_close <= thesis.long_strike:
            return width
        else:
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
