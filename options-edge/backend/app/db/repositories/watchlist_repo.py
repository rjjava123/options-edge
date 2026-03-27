"""CRUD operations for the watchlist table."""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thesis import Watchlist


async def add_ticker(
    session: AsyncSession,
    ticker: str,
    notes: Optional[str] = None,
) -> Watchlist:
    """Add a ticker to the watchlist. Returns the new row."""
    entry = Watchlist(ticker=ticker.upper(), notes=notes)
    session.add(entry)
    await session.flush()
    return entry


async def remove_ticker(session: AsyncSession, ticker: str) -> None:
    """Remove a ticker from the watchlist."""
    stmt = delete(Watchlist).where(Watchlist.ticker == ticker.upper())
    await session.execute(stmt)
    await session.flush()


async def get_ticker(session: AsyncSession, ticker: str) -> Optional[Watchlist]:
    """Return a single watchlist entry by ticker symbol."""
    stmt = select(Watchlist).where(Watchlist.ticker == ticker.upper())
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_watchlist(session: AsyncSession) -> Sequence[Watchlist]:
    """Return all watchlist entries ordered by most recently added."""
    stmt = select(Watchlist).order_by(Watchlist.added_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_notes(
    session: AsyncSession,
    ticker: str,
    notes: str,
) -> Optional[Watchlist]:
    """Update the notes for an existing watchlist entry."""
    entry = await get_ticker(session, ticker)
    if entry is None:
        return None
    entry.notes = notes
    await session.flush()
    return entry
