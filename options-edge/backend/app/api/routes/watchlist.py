"""Watchlist routes: manage tickers the user wants to monitor."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.repositories import watchlist_repo
from app.graph.builder import analysis_graph
from app.models.state import AnalysisState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddTickerRequest(BaseModel):
    ticker: str
    notes: Optional[str] = None


class WatchlistItem(BaseModel):
    ticker: str
    added_at: str
    notes: Optional[str] = None


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/")
async def list_watchlist(db: AsyncSession = Depends(get_db)):
    """Return all tickers on the watchlist, ordered by most recently added."""
    items = await watchlist_repo.list_watchlist(db)
    return {
        "count": len(items),
        "items": [
            {
                "ticker": w.ticker,
                "added_at": w.added_at.isoformat(),
                "notes": w.notes,
            }
            for w in items
        ],
    }


@router.post("/", status_code=201)
async def add_ticker(request: AddTickerRequest, db: AsyncSession = Depends(get_db)):
    """Add a ticker to the watchlist."""
    existing = await watchlist_repo.get_ticker(db, request.ticker)
    if existing:
        raise HTTPException(status_code=409, detail=f"{request.ticker.upper()} is already on the watchlist")

    entry = await watchlist_repo.add_ticker(db, request.ticker, request.notes)
    return {
        "ticker": entry.ticker,
        "added_at": entry.added_at.isoformat(),
        "notes": entry.notes,
    }


@router.delete("/{ticker}", status_code=204)
async def remove_ticker(ticker: str, db: AsyncSession = Depends(get_db)):
    """Remove a ticker from the watchlist."""
    existing = await watchlist_repo.get_ticker(db, ticker)
    if not existing:
        raise HTTPException(status_code=404, detail=f"{ticker.upper()} is not on the watchlist")

    await watchlist_repo.remove_ticker(db, ticker)


@router.post("/{ticker}/refresh")
async def refresh_ticker(ticker: str, db: AsyncSession = Depends(get_db)):
    """Refresh news context for a watchlist ticker.

    Runs only the ``fetch_news_context`` node from the analysis graph
    to pull fresh news and sentiment data.
    """
    existing = await watchlist_repo.get_ticker(db, ticker)
    if not existing:
        raise HTTPException(status_code=404, detail=f"{ticker.upper()} is not on the watchlist")

    try:
        # Import the node directly to run it in isolation
        from app.graph.nodes.fetch_news_context import fetch_news_context

        state = AnalysisState(ticker=ticker.upper(), flow_type="watchlist_refresh")
        result = await fetch_news_context(state)
        news_context = result.get("news_context")

        return {
            "ticker": ticker.upper(),
            "news_context": news_context.model_dump() if news_context else None,
        }

    except Exception as exc:
        logger.exception("Failed to refresh news for %s", ticker)
        raise HTTPException(status_code=500, detail=str(exc))
