"""Active trades routes: view currently active theses with live P&L info."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.db.repositories import thesis_repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/active-trades", tags=["active-trades"])


@router.get("/")
async def list_active_trades(db: AsyncSession = Depends(get_db)):
    """List all active theses with their latest P&L snapshot data.

    Returns theses where ``is_active=True`` and ``status='active'``,
    enriched with the most recent daily snapshot for current P&L info.
    """
    theses = await thesis_repo.list_theses(
        db, status="active", is_active=True, limit=200,
    )

    trades = []
    for t in theses:
        snapshots = await thesis_repo.get_snapshots_for_thesis(db, t.id)
        latest = snapshots[-1] if snapshots else None

        trade_data = {
            "id": str(t.id),
            "ticker": t.ticker,
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
            "created_at": t.created_at.isoformat(),
            "current_pnl": None,
            "latest_snapshot": None,
        }

        if latest:
            trade_data["current_pnl"] = {
                "pnl_dollars": latest.pnl_dollars,
                "pnl_percent": latest.pnl_percent,
                "underlying_close": latest.underlying_close,
                "spread_mark": latest.spread_mark,
                "as_of": latest.snapshot_date.isoformat(),
            }
            trade_data["latest_snapshot"] = latest.snapshot_date.isoformat()

        trades.append(trade_data)

    return {"count": len(trades), "trades": trades}


@router.get("/{thesis_id}/alerts")
async def get_trade_alerts(thesis_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Return alert history for an active trade.

    Placeholder: returns snapshots where an exit condition was flagged.
    A full implementation would query a dedicated alerts table.
    """
    thesis = await thesis_repo.get_thesis(db, thesis_id)
    if not thesis:
        raise HTTPException(status_code=404, detail="Thesis not found")

    snapshots = await thesis_repo.get_snapshots_for_thesis(db, thesis_id)
    alerts = [
        {
            "date": s.snapshot_date.isoformat(),
            "condition": s.exit_condition_met,
            "pnl_dollars": s.pnl_dollars,
            "pnl_percent": s.pnl_percent,
            "underlying_close": s.underlying_close,
        }
        for s in snapshots
        if s.exit_condition_met is not None
    ]

    return {
        "thesis_id": str(thesis_id),
        "ticker": thesis.ticker,
        "alerts": alerts,
    }
