"""Automated system scoring for closed or expired theses."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import thesis_repo

logger = logging.getLogger(__name__)


async def calculate_system_score(
    thesis_id,
    db_session: AsyncSession,
) -> dict:
    """Compute automated performance metrics for a thesis and persist the score.

    Queries all daily snapshots for the thesis and derives:

    - ``profitable_at_close_date`` -- first date the thesis was profitable
    - ``hit_profit_target`` -- whether the profit target was ever reached
    - ``days_to_profit_target`` -- trading days from entry to profit target hit
    - ``max_favorable_excursion`` -- peak P&L in dollars during the life of the trade
    - ``max_adverse_excursion`` -- worst P&L in dollars during the life of the trade
    - ``final_pnl`` -- the P&L on the last snapshot (close / expiry day)

    Returns the score dict and saves it via ``thesis_repo.create_system_score``.
    """
    thesis = await thesis_repo.get_thesis(db_session, thesis_id)
    if thesis is None:
        raise ValueError(f"Thesis {thesis_id} not found")

    snapshots = await thesis_repo.get_snapshots_for_thesis(db_session, thesis_id)
    if not snapshots:
        logger.warning("No snapshots found for thesis %s -- cannot score", thesis_id)
        return {}

    # Compute metrics
    profitable_at_close_date: Optional[date] = None
    hit_profit_target: bool = False
    days_to_profit_target: Optional[int] = None
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0

    entry_date = thesis.created_at.date()

    for i, snap in enumerate(snapshots):
        pnl = snap.pnl_dollars

        # Track MFE / MAE
        if pnl > max_favorable_excursion:
            max_favorable_excursion = pnl
        if pnl < max_adverse_excursion:
            max_adverse_excursion = pnl

        # First profitable date
        if pnl > 0 and profitable_at_close_date is None:
            profitable_at_close_date = snap.snapshot_date

        # Profit target
        if not hit_profit_target and pnl >= thesis.profit_target:
            hit_profit_target = True
            days_to_profit_target = (snap.snapshot_date - entry_date).days

    # Final P&L is the last snapshot
    final_pnl = snapshots[-1].pnl_dollars

    score_data = {
        "thesis_id": thesis_id,
        "profitable_at_close_date": profitable_at_close_date,
        "hit_profit_target": hit_profit_target,
        "days_to_profit_target": days_to_profit_target,
        "max_favorable_excursion": round(max_favorable_excursion, 2),
        "max_adverse_excursion": round(max_adverse_excursion, 2),
        "final_pnl": round(final_pnl, 2),
    }

    # Check if a system score already exists; if so, skip creation
    existing = await thesis_repo.get_system_score(db_session, thesis_id)
    if existing is None:
        await thesis_repo.create_system_score(db_session, **score_data)
        logger.info("System score saved for thesis %s: final_pnl=%.2f", thesis_id, final_pnl)
    else:
        logger.info("System score already exists for thesis %s -- skipping", thesis_id)

    return score_data
