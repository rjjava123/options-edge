"""Fetch current and historical market data for the underlying ticker."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.data.polygon_client import get_polygon_client
from app.models.state import AnalysisState, MarketData, OHLCBar

logger = logging.getLogger(__name__)


async def fetch_market_data(state: AnalysisState) -> dict:
    """Retrieve price action, volume, OHLC history, and basic quote data.

    Uses the Polygon REST API to pull:
    - Snapshot for current price, bid/ask, volume, change %, vwap, prev close
    - 90 calendar days of daily OHLC bars for trend analysis

    Returns a dict keyed by ``market_data`` so LangGraph merges the result
    into ``AnalysisState.market_data``.
    """
    client = get_polygon_client()
    ticker = state.ticker.upper()

    logger.info("Fetching market data for %s", ticker)

    # -- Snapshot / quote --------------------------------------------------
    snapshot = await client.get_snapshot(ticker)

    current_price = snapshot.get("lastTrade", {}).get("p", 0.0)
    bid = snapshot.get("lastQuote", {}).get("P", 0.0)
    ask = snapshot.get("lastQuote", {}).get("p", 0.0)
    today_change_pct = snapshot.get("todaysChangePerc", 0.0)
    volume = int(snapshot.get("day", {}).get("v", 0))
    vwap = snapshot.get("day", {}).get("vw", 0.0)
    prev_close = snapshot.get("prevDay", {}).get("c", 0.0)

    # -- OHLC history (90 calendar days) -----------------------------------
    bars_raw = await client.get_daily_bars(ticker, days=90)

    ohlc_history = [
        OHLCBar(
            open=bar.get("o", 0.0),
            high=bar.get("h", 0.0),
            low=bar.get("l", 0.0),
            close=bar.get("c", 0.0),
            volume=int(bar.get("v", 0)),
            timestamp=datetime.fromtimestamp(
                bar.get("t", 0) / 1000, tz=timezone.utc
            ).isoformat(),
            vwap=bar.get("vw", 0.0),
        )
        for bar in bars_raw
    ]

    market_data = MarketData(
        current_price=current_price or prev_close,
        prev_close=prev_close,
        volume=volume,
        today_change_pct=today_change_pct,
        bid=bid,
        ask=ask,
        vwap=vwap,
        ohlc_history=ohlc_history,
    )

    logger.info(
        "Market data fetched: %s @ $%.2f, vol=%d, %d bars",
        ticker,
        market_data.current_price,
        volume,
        len(ohlc_history),
    )

    return {"market_data": market_data}
