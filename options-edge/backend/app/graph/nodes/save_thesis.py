"""Save the final thesis and state snapshot to Postgres."""

from __future__ import annotations

import logging

from app.db.database import async_session_factory
from app.db.repositories.thesis_repo import create_thesis
from app.models.state import AnalysisState

logger = logging.getLogger(__name__)


async def save_thesis(state: AnalysisState) -> dict:
    """Persist the generated thesis and a full state snapshot to the database.

    Saves the thesis record with all trade parameters, and stores the full
    ``AnalysisState`` as a JSONB snapshot for future analysis and trap detection.

    This is a terminal node -- returns an empty dict.
    """
    if state.thesis is None:
        logger.warning("No thesis to save for %s -- skipping persistence", state.ticker)
        return {}

    thesis = state.thesis
    logger.info(
        "Saving thesis for %s: %s %s, confidence=%.2f",
        thesis.ticker,
        thesis.direction,
        thesis.spread_type,
        thesis.confidence,
    )

    # Build the full state snapshot for historical analysis
    state_snapshot = _build_state_snapshot(state)

    try:
        async with async_session_factory() as session:
            await create_thesis(
                session,
                ticker=thesis.ticker.upper(),
                flow_type=state.flow_type,
                setup_classifications=thesis.setup_classifications,
                direction=thesis.direction,
                spread_type=thesis.spread_type,
                short_strike=thesis.short_strike,
                long_strike=thesis.long_strike,
                expiration_date=thesis.expiration_date,
                entry_price=thesis.entry_price,
                max_profit=thesis.max_profit,
                max_loss=thesis.max_loss,
                profit_target=thesis.profit_target,
                stop_loss=thesis.stop_loss,
                confidence=thesis.confidence,
                reasoning=thesis.reasoning,
                state_snapshot=state_snapshot,
            )
            await session.commit()

        logger.info("Thesis saved successfully for %s", thesis.ticker)

    except Exception:
        logger.exception("Failed to save thesis for %s", thesis.ticker)
        raise

    return {}


def _build_state_snapshot(state: AnalysisState) -> dict:
    """Serialize the full analysis state into a JSON-compatible dict."""
    snapshot: dict = {
        "ticker": state.ticker,
        "flow_type": state.flow_type,
    }

    if state.market_data:
        snapshot["market_data"] = state.market_data.model_dump()

    if state.options_chain:
        # Store summary rather than full chain to save space
        oc = state.options_chain
        snapshot["options_chain"] = {
            "num_contracts": len(oc.contracts),
            "expirations": oc.expirations,
            "summary": oc.summary.model_dump() if oc.summary else None,
        }

    if state.technical_analysis:
        snapshot["technical_analysis"] = state.technical_analysis.model_dump()

    if state.unusual_activity:
        snapshot["unusual_activity"] = state.unusual_activity.model_dump()

    if state.news_context:
        snapshot["news_context"] = state.news_context.model_dump()

    if state.setup_classifications:
        snapshot["setup_classifications"] = state.setup_classifications

    if state.branch_analyses:
        snapshot["branch_analyses"] = {
            key: ba.model_dump() for key, ba in state.branch_analyses.items()
        }

    if state.trap_warnings:
        snapshot["trap_warnings"] = [tw.model_dump() for tw in state.trap_warnings]

    return snapshot
