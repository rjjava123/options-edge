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

    async def get_ohlc_history(
        self,
        ticker: str,
        days: int = 90,
    ) -> list[dict[str, Any]]:
        """Return daily OHLCV bars for the last *days* trading days.

        Uses ``/v2/aggs/ticker/{ticker}/range/1/day/{from}/{to}``.
        """
        end = date.today()
        start = end - timedelta(days=days)
        data = await self._get(
            f"/v2/aggs/ticker/{ticker.upper()}/range/1/day/{start.isoformat()}/{end.isoformat()}",
            params={"adjusted": "true", "sort": "asc", "limit": str(days + 30)},
        )
        return data.get("results", [])

    # ------------------------------------------------------------------
    # Options endpoints
    # ------------------------------------------------------------------

    async def get_options_chain(
        self,
        ticker: str,
        *,
        min_dte: int = 14,
        max_dte: int = 60,
    ) -> list[dict[str, Any]]:
        """Return options contracts for *ticker* within the DTE window.

        Uses ``/v3/snapshot/options/{underlyingAsset}`` with expiration filters.
        """
        exp_gte = (date.today() + timedelta(days=min_dte)).isoformat()
        exp_lte = (date.today() + timedelta(days=max_dte)).isoformat()

        all_results: list[dict[str, Any]] = []
        next_url: str | None = None
        path = f"/v3/snapshot/options/{ticker.upper()}"
        params: dict[str, Any] = {
            "expiration_date.gte": exp_gte,
            "expiration_date.lte": exp_lte,
            "limit": "250",
        }

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

        data = await self._get(
            f"/v3/snapshot/options/{underlying}/{contract_ticker}"
        )
        return data.get("results", data)

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
        data = await self._get(
            "/v2/reference/news",
            params={"ticker": ticker.upper(), "limit": str(limit), "order": "desc"},
        )
        return data.get("results", [])

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

        return all_tickers
