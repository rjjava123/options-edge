"""Async client for the Polygon.io REST API (stocks + options)."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.polygon.io"


class PolygonClient:
    """Thin async wrapper around Polygon.io endpoints used by Options Edge.

    All methods return parsed JSON dicts/lists.  Callers are responsible for
    mapping the raw payloads into domain models.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or get_settings().POLYGON_API_KEY
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "PolygonClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _auth_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"apiKey": self._api_key}
        if extra:
            params.update(extra)
        return params

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Issue a GET request and return the JSON body.

        Raises ``httpx.HTTPStatusError`` for 4xx/5xx responses.
        """
        resp = await self._client.get(path, params=self._auth_params(params))
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Stock endpoints
    # ------------------------------------------------------------------

    async def get_stock_quote(self, ticker: str) -> dict[str, Any]:
        """Return the latest NBBO quote for *ticker*.

        Uses ``/v2/last/nbbo/{ticker}``.
        """
        data = await self._get(f"/v2/last/nbbo/{ticker.upper()}")
        return data.get("results", data)

    async def get_snapshot(self, ticker: str) -> dict[str, Any]:
        """Return a full ticker snapshot including price, volume, and change.

        Uses ``/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}``.

        Returns a dict with keys such as:
        - ``lastTrade`` (price, size)
        - ``lastQuote`` (bid, ask, bidSize, askSize)
        - ``todaysChange``, ``todaysChangePerc``
        - ``day`` (o, h, l, c, v, vw)
        - ``prevDay`` (o, h, l, c, v, vw)
        - ``min`` (intra-day aggregate)
        """
        logger.debug("Fetching snapshot for %s", ticker)
        try:
            data = await self._get(
                f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}"
            )
            return data.get("ticker", data)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Snapshot request failed for %s: %s %s",
                ticker,
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise

    async def get_daily_bars(
        self,
        ticker: str,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Return daily OHLCV bars for the last *days* calendar days.

        Uses ``/v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}``.

        Each result dict uses Polygon's native field names:
        - ``v``  : volume
        - ``vw`` : volume-weighted average price
        - ``o``  : open
        - ``c``  : close
        - ``h``  : high
        - ``l``  : low
        - ``t``  : Unix timestamp (ms)
        - ``n``  : number of transactions
        """
        end = date.today()
        start = end - timedelta(days=days)
        logger.debug("Fetching daily bars for %s from %s to %s", ticker, start, end)
        try:
            data = await self._get(
                f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/"
                f"{start.isoformat()}/{end.isoformat()}",
                params={
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": str(days + 30),
                },
            )
            return data.get("results", [])
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Daily bars request failed for %s: %s %s",
                ticker,
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise

    async def get_ohlc_history(
        self,
        ticker: str,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Alias for :meth:`get_daily_bars` (kept for backward compatibility)."""
        return await self.get_daily_bars(ticker, days=days)

    async def get_grouped_daily(
        self, date_str: str | None = None
    ) -> list[dict[str, Any]]:
        """Return aggregates for ALL US stocks for a single trading day.

        Uses ``/v2/aggs/grouped/locale/us/market/stocks/{date}``.

        This is a single API call that returns one bar per ticker for the
        entire market.  Useful as a first-pass screener filter (e.g. volume,
        price range) to avoid making per-ticker snapshot calls.

        If *date_str* is ``None``, defaults to the most recent completed
        trading day (yesterday, or Friday if today is Saturday/Sunday).

        Each result dict uses Polygon's native field names:
        - ``T``  : ticker symbol
        - ``v``  : volume
        - ``vw`` : volume-weighted average price
        - ``o``  : open
        - ``c``  : close
        - ``h``  : high
        - ``l``  : low
        - ``t``  : Unix timestamp (ms)
        - ``n``  : number of transactions
        """
        if date_str is None:
            d = date.today()
            # Walk back to the most recent weekday (rough proxy for trading day)
            while d.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
                d -= timedelta(days=1)
            # Use the prior trading day to ensure the market has closed
            if d == date.today():
                d -= timedelta(days=1)
                while d.weekday() >= 5:
                    d -= timedelta(days=1)
            date_str = d.isoformat()

        logger.debug("Fetching grouped daily aggregates for %s", date_str)
        try:
            data = await self._get(
                f"/v2/aggs/grouped/locale/us/market/stocks/{date_str}",
                params={"adjusted": "true"},
            )
            return data.get("results", [])
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Grouped daily request failed for %s: %s %s",
                date_str,
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise

    # ------------------------------------------------------------------
    # Options endpoints
    # ------------------------------------------------------------------

    async def get_options_chain(
        self,
        ticker: str,
        *,
        min_dte: int = 1,
        max_dte: int = 14,
    ) -> list[dict[str, Any]]:
        """Return options contracts for *ticker* within the DTE window.

        Uses ``/v3/snapshot/options/{underlyingAsset}`` with expiration filters.

        Defaults to 1-14 DTE for short-dated spread trading strategies.
        """
        exp_gte = (date.today() + timedelta(days=min_dte)).isoformat()
        exp_lte = (date.today() + timedelta(days=max_dte)).isoformat()

        logger.debug(
            "Fetching options chain for %s (DTE %d-%d, exp %s to %s)",
            ticker,
            min_dte,
            max_dte,
            exp_gte,
            exp_lte,
        )

        all_results: list[dict[str, Any]] = []
        next_url: str | None = None
        path = f"/v3/snapshot/options/{ticker.upper()}"
        params: dict[str, Any] = {
            "expiration_date.gte": exp_gte,
            "expiration_date.lte": exp_lte,
            "limit": "250",
        }

        try:
            while True:
                if next_url:
                    # Polygon pagination returns a full URL; extract path + query
                    resp = await self._client.get(
                        next_url, params={"apiKey": self._api_key}
                    )
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    data = await self._get(path, params=params)

                all_results.extend(data.get("results", []))
                next_url = data.get("next_url")
                if not next_url:
                    break
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Options chain request failed for %s: %s %s",
                ticker,
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise

        logger.debug("Fetched %d option contracts for %s", len(all_results), ticker)
        return all_results

    async def get_option_contract_snapshot(
        self, contract_ticker: str
    ) -> dict[str, Any]:
        """Return a snapshot for a single option contract.

        Uses ``/v3/snapshot/options/{underlyingAsset}/{optionContract}``.
        The *contract_ticker* should be the full OCC-style ticker, e.g.
        ``O:AAPL250418C00170000``.
        """
        # Extract underlying from the contract ticker
        parts = contract_ticker.replace("O:", "")
        underlying = ""
        for ch in parts:
            if ch.isalpha():
                underlying += ch
            else:
                break

        logger.debug(
            "Fetching option contract snapshot for %s (underlying=%s)",
            contract_ticker,
            underlying,
        )
        try:
            data = await self._get(
                f"/v3/snapshot/options/{underlying}/{contract_ticker}"
            )
            return data.get("results", data)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Option contract snapshot failed for %s: %s %s",
                contract_ticker,
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise

    async def get_option_contract_daily_bars(
        self,
        contract_ticker: str,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """Return daily OHLCV bars for a specific option contract.

        Uses ``/v2/aggs/ticker/{contract_ticker}/range/1/day/{from}/{to}``.

        Used for P&L tracking of option positions.  The *contract_ticker*
        should be the full OCC-style ticker, e.g. ``O:AAPL250418C00170000``.

        Each result dict uses Polygon's native field names:
        - ``v``  : volume
        - ``vw`` : volume-weighted average price
        - ``o``  : open
        - ``c``  : close
        - ``h``  : high
        - ``l``  : low
        - ``t``  : Unix timestamp (ms)
        - ``n``  : number of transactions
        """
        end = date.today()
        start = end - timedelta(days=days)
        logger.debug(
            "Fetching option contract daily bars for %s from %s to %s",
            contract_ticker,
            start,
            end,
        )
        try:
            data = await self._get(
                f"/v2/aggs/ticker/{contract_ticker}/range/1/day/"
                f"{start.isoformat()}/{end.isoformat()}",
                params={
                    "adjusted": "true",
                    "sort": "asc",
                    "limit": str(days + 30),
                },
            )
            return data.get("results", [])
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Option contract daily bars failed for %s: %s %s",
                contract_ticker,
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    async def get_ticker_news(
        self,
        ticker: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent news articles for *ticker*.

        Uses ``/v2/reference/news``.
        """
        logger.debug("Fetching news for %s (limit=%d)", ticker, limit)
        try:
            data = await self._get(
                "/v2/reference/news",
                params={
                    "ticker": ticker.upper(),
                    "limit": str(limit),
                    "order": "desc",
                },
            )
            return data.get("results", [])
        except httpx.HTTPStatusError as exc:
            logger.error(
                "News request failed for %s: %s %s",
                ticker,
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise

    # ------------------------------------------------------------------
    # Reference
    # ------------------------------------------------------------------

    async def get_optionable_tickers(
        self, *, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Return US-listed tickers that have listed options.

        Uses ``/v3/reference/tickers`` with ``type=CS`` and ``market=stocks``.
        Paginates through all results.
        """
        all_tickers: list[dict[str, Any]] = []
        next_url: str | None = None
        path = "/v3/reference/tickers"
        params: dict[str, Any] = {
            "type": "CS",
            "market": "stocks",
            "active": "true",
            "limit": str(limit),
            "order": "asc",
            "sort": "ticker",
        }

        logger.debug("Fetching optionable tickers (limit=%d per page)", limit)
        try:
            while True:
                if next_url:
                    resp = await self._client.get(
                        next_url, params={"apiKey": self._api_key}
                    )
                    resp.raise_for_status()
                    data = resp.json()
                else:
                    data = await self._get(path, params=params)

                all_tickers.extend(data.get("results", []))
                next_url = data.get("next_url")
                if not next_url:
                    break
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Optionable tickers request failed: %s %s",
                exc.response.status_code,
                exc.response.text[:200],
            )
            raise

        logger.debug("Fetched %d optionable tickers", len(all_tickers))
        return all_tickers


# ------------------------------------------------------------------
# Module-level factory
# ------------------------------------------------------------------


def get_polygon_client(api_key: str | None = None) -> PolygonClient:
    """Create and return a new :class:`PolygonClient` instance.

    If *api_key* is not provided, the key is read from application settings.
    """
    return PolygonClient(api_key=api_key)
