"""Thesis routes: list, detail, score, activate, close, and trap-check."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.repositories import thesis_repo
from app.tracking.scoring import calculate_system_score

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/theses", tags=["theses"])


# ------------------------------------------------------------------
# Request / response schemas
# ------------------------------------------------------------------

class UserScoreRequest(BaseModel):
    score: int = Field(..., ge=1, le=10)
    direction_correct: Optional[bool] = None
    structure_appropriate: Optional[bool] = None
    timing_good: Optional[bool] = None
    notes: Optional[str] = None


class CloseRequest(BaseModel):
    reason: str = "manual_close"


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.get("/")
async def list_theses(
    ticker: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    spread_type: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List theses with optional query filters."""
    from sqlalchemy import select

    from app.models.thesis import Thesis

    stmt = select(Thesis).order_by(Thesis.created_at.desc())

    if ticker:
        stmt = stmt.where(Thesis.ticker == ticker.upper())
    if status:
        stmt = stmt.where(Thesis.status == status)
    if spread_type:
        stmt = stmt.where(Thesis.spread_type == spread_type)
    if date_from:
        stmt = stmt.where(Thesis.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        stmt = stmt.where(Thesis.created_at <= datetime.combine(date_to, datetime.max.time()))

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    theses = result.scalars().all()

    return {
        "count": len(theses),
        "limit": limit,
        "offset": offset,
        "theses": [_serialize_thesis(t) for t in theses],
    }


@router.get("/{thesis_id}")
async def get_thesis_detail(thesis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return a thesis with its daily snapshots and scores."""
    thesis = await thesis_repo.get_thesis(db, thesis_id)
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis not found")

    snapshots = await thesis_repo.get_snapshots_for_thesis(db, thesis_id)
    system_score = await thesis_repo.get_system_score(db, thesis_id)
    user_score = await thesis_repo.get_user_score(db, thesis_id)

    data = _serialize_thesis(thesis)
    data["daily_snapshots"] = [
        {
            "id": str(s.id),
            "snapshot_date": s.snapshot_date.isoformat(),
            "underlying_close": s.underlying_close,
            "spread_mark": s.spread_mark,
            "pnl_dollars": s.pnl_dollars,
            "pnl_percent": s.pnl_percent,
            "exit_condition_met": s.exit_condition_met,
        }
        for s in snapshots
    ]
    data["system_score"] = (
        {
            "profitable_at_close_date": (
                system_score.profitable_at_close_date.isoformat()
                if system_score.profitable_at_close_date
                else None
            ),
            "hit_profit_target": system_score.hit_profit_target,
            "days_to_profit_target": system_score.days_to_profit_target,
            "max_favorable_excursion": system_score.max_favorable_excursion,
            "max_adverse_excursion": system_score.max_adverse_excursion,
            "final_pnl": system_score.final_pnl,
        }
        if system_score
        else None
    )
    data["user_score"] = (
        {
            "score": user_score.score,
            "direction_correct": user_score.direction_correct,
            "structure_appropriate": user_score.structure_appropriate,
            "timing_good": user_score.timing_good,
            "notes": user_score.notes,
            "scored_at": user_score.scored_at.isoformat(),
        }
        if user_score
        else None
    )

    return data


@router.post("/{thesis_id}/score")
async def submit_user_score(
    thesis_id: uuid.UUID,
    request: UserScoreRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit a user score for a thesis."""
    thesis = await thesis_repo.get_thesis(db, thesis_id)
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis not found")

    existing = await thesis_repo.get_user_score(db, thesis_id)
    if existing:
        raise HTTPException(status_code=409, detail="User score already exists for this thesis")

    score = await thesis_repo.create_user_score(
        db,
        thesis_id=thesis_id,
        score=request.score,
        direction_correct=request.direction_correct,
        structure_appropriate=request.structure_appropriate,
        timing_good=request.timing_good,
        notes=request.notes,
    )

    return {
        "thesis_id": str(thesis_id),
        "score": score.score,
        "scored_at": score.scored_at.isoformat(),
    }


@router.post("/{thesis_id}/activate")
async def toggle_active(thesis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Toggle the ``is_active`` flag on a thesis."""
    thesis = await thesis_repo.get_thesis(db, thesis_id)
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis not found")

    new_active = not thesis.is_active
    await thesis_repo.update_thesis_status(
        db,
        thesis_id,
        status=thesis.status,
        is_active=new_active,
    )

    return {"thesis_id": str(thesis_id), "is_active": new_active}


@router.post("/{thesis_id}/close")
async def close_thesis(
    thesis_id: uuid.UUID,
    request: CloseRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually close a thesis."""
    thesis = await thesis_repo.get_thesis(db, thesis_id)
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis not found")

    if not thesis.is_active:
        raise HTTPException(status_code=400, detail="Thesis is already closed")

    await thesis_repo.update_thesis_status(
        db,
        thesis_id,
        status=request.reason,
        is_active=False,
        closed_at=datetime.now(timezone.utc),
    )

    # Calculate system score on close
    try:
        score_data = await calculate_system_score(thesis_id, db)
    except Exception:
        logger.exception("Failed to calculate system score for %s", thesis_id)
        score_data = {}

    return {
        "thesis_id": str(thesis_id),
        "status": request.reason,
        "system_score": score_data if score_data else None,
    }


@router.post("/{thesis_id}/trap-check")
async def run_trap_check(thesis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Run trap detection on an existing thesis.

    Reconstructs a partial analysis state from the stored snapshot and runs
    the ``check_trap_detection`` node to look for historical pattern matches.
    """
    thesis = await thesis_repo.get_thesis(db, thesis_id)
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis not found")

    from app.graph.nodes.check_trap_detection import check_trap_detection
    from app.models.state import AnalysisState, Thesis as ThesisState

    state = AnalysisState(
        ticker=thesis.ticker,
        flow_type=thesis.flow_type,
        setup_classifications=thesis.setup_classifications,
        thesis=ThesisState(
            ticker=thesis.ticker,
            direction=thesis.direction,
            spread_type=thesis.spread_type,
            short_strike=thesis.short_strike,
            long_strike=thesis.long_strike,
            expiration_date=thesis.expiration_date.isoformat(),
            entry_price=thesis.entry_price,
            max_profit=thesis.max_profit,
            max_loss=thesis.max_loss,
            profit_target=thesis.profit_target,
            stop_loss=thesis.stop_loss,
            confidence=thesis.confidence,
            reasoning=thesis.reasoning,
        ),
    )

    try:
        result = await check_trap_detection(state)
        warnings = result.get("trap_warnings", [])
        return {
            "thesis_id": str(thesis_id),
            "trap_warnings": [w.model_dump() if hasattr(w, "model_dump") else w for w in warnings],
        }
    except Exception as exc:
        logger.exception("Trap check failed for thesis %s", thesis_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _serialize_thesis(t) -> dict:
    """Convert a Thesis ORM instance to a JSON-serializable dict."""
    return {
        "id": str(t.id),
        "ticker": t.ticker,
        "created_at": t.created_at.isoformat(),
        "flow_type": t.flow_type,
        "setup_classifications": t.setup_classifications,
        "direction": t.direction,
        "spread_type": t.spread_type,
        "short_strike": t.short_strike,
        "long_strike": t.long_strike,
        "expiration_date": t.expiration_date.isoformat(),
        "entry_price": t.entry_price,
        "max_profit": t.max_profit,
        "max_loss": t.max_loss,
        "profit_target": t.profit_target,
        "stop_loss": t.stop_loss,
        "confidence": t.confidence,
        "reasoning": t.reasoning,
        "status": t.status,
        "is_active": t.is_active,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
    }
