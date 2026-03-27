"""Fetch current and historical market data for the underlying ticker."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.config import get_settings
from app.data.polygon_client import get_polygon_client
from app.models.state import AnalysisState, MarketData

logger = logging.getLogger(__name__)


async def fetch_market_data(state: AnalysisState) -> dict:
    """Retrieve price action, volume, OHLC history, and basic quote data.

    Uses the Polygon REST API to pull:
    - Previous-day and current quote snapshot
    - 90 calendar days of daily OHLC bars for trend analysis
    - Current volume and last trade price

    Returns a dict keyed by ``market_data`` so LangGraph merges the result
    into ``AnalysisState.market_data``.
    """
    settings = get_settings()
    client = get_polygon_client(settings.POLYGON_API_KEY)
    ticker = state.ticker.upper()

    logger.info("Fetching market data for %s", ticker)

    # -- Snapshot / quote --------------------------------------------------
    snapshot = await client.get_snapshot(ticker)
    quote = {
        "bid": snapshot.get("ticker", {}).get("lastQuote", {}).get("p", 0.0),
        "ask": snapshot.get("ticker", {}).get("lastQuote", {}).get("P", 0.0),
        "last_trade_price": snapshot.get("ticker", {}).get("lastTrade", {}).get("p", 0.0),
        "last_trade_size": snapshot.get("ticker", {}).get("lastTrade", {}).get("s", 0),
        "prev_close": snapshot.get("ticker", {}).get("prevDay", {}).get("c", 0.0),
        "today_change_pct": snapshot.get("ticker", {}).get("todaysChangePerc", 0.0),
    }

    price = quote["last_trade_price"] or quote["prev_close"]
    volume = snapshot.get("ticker", {}).get("day", {}).get("v", 0)

    # -- OHLC history (90 calendar days) -----------------------------------
    end_date = date.today()
    start_date = end_date - timedelta(days=90)

    aggregates = await client.get_aggregates(
        ticker=ticker,
        multiplier=1,
        timespan="day",
        from_date=start_date.isoformat(),
        to_date=end_date.isoformat(),
    )

    ohlc_history = [
        {
            "date": bar.get("t"),
            "open": bar.get("o"),
            "high": bar.get("h"),
            "low": bar.get("l"),
            "close": bar.get("c"),
            "volume": bar.get("v"),
            "vwap": bar.get("vw"),
            "transactions": bar.get("n"),
        }
        for bar in aggregates.get("results", [])
    ]

    market_data = MarketData(
        price=price,
        volume=int(volume),
        ohlc_history=ohlc_history,
        quote=quote,
    )

    logger.info(
        "Market data fetched: %s @ $%.2f, vol=%d, %d bars",
        ticker,
        price,
        volume,
        len(ohlc_history),
    )

    return {"market_data": market_data}
