"""Fetch the universe of optionable US equities from Polygon."""

from __future__ import annotations

import logging

from app.data.polygon_client import PolygonClient

logger = logging.getLogger(__name__)


async def fetch_optionable_universe(
    client: PolygonClient | None = None,
) -> list[str]:
    """Return a list of ticker symbols for US equities with listed options.

    Queries Polygon's reference tickers endpoint and paginates through all
    active common-stock tickers.  The Polygon API does not have a dedicated
    "has options" flag, so we pull all active CS tickers (~3,000-4,000) as a
    proxy.  Downstream screener filters will eliminate illiquid names.

    Parameters
    ----------
    client
        An existing :class:`PolygonClient` instance.  If ``None`` a temporary
        client is created and closed automatically.

    Returns
    -------
    list[str]
        Sorted list of uppercase ticker symbols.
    """
    own_client = client is None
    if own_client:
        client = PolygonClient()

    try:
        raw = await client.get_optionable_tickers(limit=1000)
        tickers = sorted(
            {
                t["ticker"]
                for t in raw
                if t.get("ticker")
                and not any(ch in t["ticker"] for ch in (".", "-", "/"))
            }
        )
        logger.info("Fetched %d optionable tickers from Polygon", len(tickers))
        return tickers
    finally:
        if own_client:
            await client.close()
