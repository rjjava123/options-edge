"""Async client for the Benzinga News API."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.benzinga.com/api/v2"


class BenzingaClient:
    """Thin async wrapper around the Benzinga content API.

    The free tier provides news headlines and teasers.  Full article bodies
    require a paid subscription.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or get_settings().BENZINGA_API_KEY
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            timeout=20.0,
            headers={
                "Accept": "application/json",
            },
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "BenzingaClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # News
    # ------------------------------------------------------------------

    async def get_news(
        self,
        ticker: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch recent news headlines and teasers for *ticker*.

        Returns a list of dicts with at least the keys:
        ``id``, ``title``, ``teaser``, ``published``, ``url``, ``source``.
        """
        params: dict[str, Any] = {
            "token": self._api_key,
            "tickers": ticker.upper(),
            "pageSize": str(limit),
            "displayOutput": "headline",
        }
        resp = await self._client.get("/news", params=params)
        resp.raise_for_status()
        raw: list[dict[str, Any]] = resp.json()

        # Normalise to a consistent shape
        articles: list[dict[str, Any]] = []
        for item in raw:
            articles.append(
                {
                    "id": item.get("id"),
                    "title": item.get("title", ""),
                    "teaser": item.get("teaser", ""),
                    "published": item.get("created", item.get("updated", "")),
                    "url": item.get("url", ""),
                    "source": item.get("author", ""),
                    "tickers": [
                        s.get("name", "") for s in item.get("stocks", [])
                    ],
                }
            )
        return articles
