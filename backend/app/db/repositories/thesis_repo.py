"""CRUD operations for thesis-related tables."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.thesis import (
    SystemScore,
    Thesis,
    ThesisDailySnapshot,
    UserScore,
)


# ---------------------------------------------------------------------------
# Thesis
# ---------------------------------------------------------------------------

async def create_thesis(session: AsyncSession, **kwargs) -> Thesis:
    """Insert a new thesis row and return it."""
    thesis = Thesis(**kwargs)
    session.add(thesis)
    await session.flush()
    return thesis


async def get_thesis(session: AsyncSession, thesis_id: uuid.UUID) -> Optional[Thesis]:
    """Fetch a single thesis by primary key."""
    return await session.get(Thesis, thesis_id)


async def list_theses(
    session: AsyncSession,
    *,
    ticker: Optional[str] = None,
    status: Optional[str] = None,
    is_active: Optional[bool] = None,
    direction: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Sequence[Thesis]:
    """Return theses with optional filters, ordered by creation date descending."""
    stmt = select(Thesis).order_by(Thesis.created_at.desc())

    if ticker is not None:
        stmt = stmt.where(Thesis.ticker == ticker.upper())
    if status is not None:
        stmt = stmt.where(Thesis.status == status)
    if is_active is not None:
        stmt = stmt.where(Thesis.is_active == is_active)
    if direction is not None:
        stmt = stmt.where(Thesis.direction == direction)

    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return result.scalars().all()


async def update_thesis_status(
    session: AsyncSession,
    thesis_id: uuid.UUID,
    status: str,
    *,
    is_active: Optional[bool] = None,
    closed_at: Optional[datetime] = None,
) -> None:
    """Update the status (and optionally is_active / closed_at) of a thesis."""
    values: dict = {"status": status}
    if is_active is not None:
        values["is_active"] = is_active
    if closed_at is not None:
        values["closed_at"] = closed_at

    stmt = update(Thesis).where(Thesis.id == thesis_id).values(**values)
    await session.execute(stmt)
    await session.flush()


# ---------------------------------------------------------------------------
# Daily Snapshots
# ---------------------------------------------------------------------------

async def create_snapshot(session: AsyncSession, **kwargs) -> ThesisDailySnapshot:
    """Insert a daily P&L snapshot."""
    snapshot = ThesisDailySnapshot(**kwargs)
    session.add(snapshot)
    await session.flush()
    return snapshot


async def get_snapshots_for_thesis(
    session: AsyncSession,
    thesis_id: uuid.UUID,
    *,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> Sequence[ThesisDailySnapshot]:
    """Return all daily snapshots for a thesis, optionally filtered by date range."""
    stmt = (
        select(ThesisDailySnapshot)
        .where(ThesisDailySnapshot.thesis_id == thesis_id)
        .order_by(ThesisDailySnapshot.snapshot_date.asc())
    )
    if start_date is not None:
        stmt = stmt.where(ThesisDailySnapshot.snapshot_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(ThesisDailySnapshot.snapshot_date <= end_date)

    result = await session.execute(stmt)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# System Score
# ---------------------------------------------------------------------------

async def create_system_score(session: AsyncSession, **kwargs) -> SystemScore:
    """Insert an automated system score for a thesis."""
    score = SystemScore(**kwargs)
    session.add(score)
    await session.flush()
    return score


async def get_system_score(
    session: AsyncSession, thesis_id: uuid.UUID
) -> Optional[SystemScore]:
    """Fetch the system score for a given thesis."""
    stmt = select(SystemScore).where(SystemScore.thesis_id == thesis_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# User Score
# ---------------------------------------------------------------------------

async def create_user_score(session: AsyncSession, **kwargs) -> UserScore:
    """Insert a user-provided score for a thesis."""
    score = UserScore(**kwargs)
    session.add(score)
    await session.flush()
    return score


async def get_user_score(
    session: AsyncSession, thesis_id: uuid.UUID
) -> Optional[UserScore]:
    """Fetch the user score for a given thesis."""
    stmt = select(UserScore).where(UserScore.thesis_id == thesis_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
