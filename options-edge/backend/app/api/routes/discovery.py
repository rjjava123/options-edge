"""Discovery routes: trigger screener + analysis pipeline and view results."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.graph.builder import analysis_graph
from app.models.screener import ScreenerCandidate, ScreenerFilters
from app.models.state import AnalysisState
from app.models.thesis import Thesis
from app.screener.runner import run_screener

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/discovery", tags=["discovery"])

# Module-level state for tracking the last scan
_last_scan_timestamp: datetime | None = None
_scan_running: bool = False


class DiscoveryRequest(BaseModel):
    """Request body for triggering a discovery run."""
    filters: ScreenerFilters = ScreenerFilters()
    max_concurrent: int = 5


class DiscoveryStatusResponse(BaseModel):
    last_scan: datetime | None = None
    is_running: bool = False


# ------------------------------------------------------------------
# Background task
# ------------------------------------------------------------------

async def _run_analysis_for_candidate(candidate: ScreenerCandidate) -> dict | None:
    """Run the full analysis graph for a single screener candidate."""
    try:
        initial_state = AnalysisState(
            ticker=candidate.ticker,
            flow_type="screener",
        )
        result = await analysis_graph.ainvoke(initial_state.model_dump())
        return result
    except Exception:
        logger.exception("Analysis failed for %s", candidate.ticker)
        return None


async def _run_discovery(filters: ScreenerFilters, max_concurrent: int) -> None:
    """Full discovery pipeline: screener -> concurrent analysis for each candidate."""
    global _last_scan_timestamp, _scan_running
    _scan_running = True

    try:
        # Step 1: Run screener
        logger.info("Starting discovery screener run")
        screener_result = await run_screener(filters)
        logger.info("Screener returned %d candidates", len(screener_result.candidates))

        # Step 2: Run analysis graph for each candidate with concurrency limit
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _limited_analysis(candidate: ScreenerCandidate):
            async with semaphore:
                return await _run_analysis_for_candidate(candidate)

        tasks = [_limited_analysis(c) for c in screener_result.candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        logger.info(
            "Discovery complete: %d/%d candidates analysed successfully",
            successful,
            len(screener_result.candidates),
        )

        _last_scan_timestamp = datetime.now(timezone.utc)

    except Exception:
        logger.exception("Discovery run failed")
    finally:
        _scan_running = False


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.post("/run")
async def trigger_discovery(
    request: DiscoveryRequest,
    background_tasks: BackgroundTasks,
):
    """Trigger a discovery run in the background.

    Runs the screener pipeline and then analyses each candidate through the
    full LangGraph analysis graph concurrently.
    """
    global _scan_running
    if _scan_running:
        raise HTTPException(status_code=409, detail="A discovery scan is already running")

    background_tasks.add_task(_run_discovery, request.filters, request.max_concurrent)
    return {"message": "Discovery run started", "status": "running"}


@router.get("/results")
async def get_results(db: AsyncSession = Depends(get_db)):
    """Return theses generated today (latest discovery results)."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    stmt = (
        select(Thesis)
        .where(Thesis.created_at >= today_start)
        .order_by(Thesis.created_at.desc())
    )
    result = await db.execute(stmt)
    theses = result.scalars().all()

    return {
        "count": len(theses),
        "theses": [
            {
                "id": str(t.id),
                "ticker": t.ticker,
                "direction": t.direction,
                "spread_type": t.spread_type,
                "short_strike": t.short_strike,
                "long_strike": t.long_strike,
                "expiration_date": t.expiration_date.isoformat(),
                "entry_price": t.entry_price,
                "confidence": t.confidence,
                "reasoning": t.reasoning,
                "created_at": t.created_at.isoformat(),
            }
            for t in theses
        ],
    }


@router.get("/status")
async def get_status():
    """Return the current discovery scan status and last scan timestamp."""
    return DiscoveryStatusResponse(
        last_scan=_last_scan_timestamp,
        is_running=_scan_running,
    )
