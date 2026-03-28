"""Trap detection: compare current thesis to historical poorly-scoring patterns."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic
from sqlalchemy import select

from app.config import get_settings
from app.db.database import async_session_factory
from app.models.state import AnalysisState, TrapWarning
from app.models.thesis import SystemScore, Thesis

logger = logging.getLogger(__name__)

MODEL = "claude-opus-4-6"

TRAP_DETECTION_SYSTEM_PROMPT = """\
You are a risk analyst specializing in pattern recognition for options trades. Your job is to
identify potential "traps" -- situations where a current trade thesis resembles historically
unprofitable patterns.

You will receive:
1. The current analysis state (ticker, classifications, branch analyses, technical data)
2. A set of historical theses with similar characteristics and their outcomes

Your task:
- Compare the current setup to each historical thesis
- Identify structural similarities (same patterns, same flow type, similar IV environment)
- Flag any historical thesis that had a poor outcome (negative final P&L, missed target)
- Assess whether the current setup is likely to fall into the same trap

For each potential trap, explain:
- What specific similarity exists
- What went wrong in the historical case
- Whether the current setup has mitigating factors

Return as JSON:
{
    "trap_warnings": [
        {
            "similar_thesis_id": "uuid-string",
            "similarity_score": 0.78,
            "outcome": "loss",
            "warning": "Description of the trap pattern and why current setup may repeat it"
        }
    ],
    "overall_risk_assessment": "low/medium/high",
    "mitigation_notes": "What makes this setup different from historical failures, if anything"
}

If no historical data is available or no similarities found, return empty trap_warnings
with overall_risk_assessment of "unknown".
"""


async def check_trap_detection(state: AnalysisState) -> dict:
    """Check current thesis against historical patterns for trap detection."""
    settings = get_settings()
    logger.info("Running trap detection for %s", state.ticker)

    # -- Query historical theses -------------------------------------------
    historical = await _fetch_similar_historical_theses(state)

    if not historical:
        logger.info("No historical theses found for comparison")
        return {"trap_warnings": []}

    # -- Claude evaluation -------------------------------------------------
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    context = _build_trap_context(state, historical)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=TRAP_DETECTION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Evaluate trap risk for the current {state.ticker} thesis.\n\n{context}"
                ),
            }
        ],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    trap_warnings = _parse_trap_response(response_text)

    logger.info("Trap detection complete: %d warnings generated", len(trap_warnings))

    return {"trap_warnings": trap_warnings}


async def _fetch_similar_historical_theses(
    state: AnalysisState,
) -> list[dict]:
    """Query DB for historical theses with similar characteristics."""
    try:
        async with async_session_factory() as session:
            stmt = (
                select(Thesis, SystemScore)
                .outerjoin(SystemScore, SystemScore.thesis_id == Thesis.id)
                .where(
                    Thesis.is_active.is_(False),
                    (Thesis.ticker == state.ticker.upper())
                    | (Thesis.flow_type == state.flow_type),
                )
                .order_by(Thesis.created_at.desc())
                .limit(20)
            )

            result = await session.execute(stmt)
            rows = result.all()

            historical = []
            for thesis_row, score_row in rows:
                entry = {
                    "id": str(thesis_row.id),
                    "ticker": thesis_row.ticker,
                    "flow_type": thesis_row.flow_type,
                    "direction": thesis_row.direction,
                    "spread_type": thesis_row.spread_type,
                    "setup_classifications": thesis_row.setup_classifications,
                    "confidence": thesis_row.confidence,
                    "reasoning": thesis_row.reasoning[:500],
                    "created_at": thesis_row.created_at.isoformat(),
                }
                if score_row:
                    entry["outcome"] = {
                        "final_pnl": score_row.final_pnl,
                        "hit_profit_target": score_row.hit_profit_target,
                        "max_adverse_excursion": score_row.max_adverse_excursion,
                        "max_favorable_excursion": score_row.max_favorable_excursion,
                    }
                historical.append(entry)

            return historical

    except Exception:
        logger.exception("Failed to query historical theses for trap detection")
        return []


def _build_trap_context(state: AnalysisState, historical: list[dict]) -> str:
    """Build context for the trap detection prompt."""
    sections = []

    # Current state summary
    current: dict = {
        "ticker": state.ticker,
        "flow_type": state.flow_type,
        "setup_classifications": state.setup_classifications or [],
    }

    if state.branch_analyses:
        current["branch_summaries"] = []
        for ba in state.branch_analyses.values():
            current["branch_summaries"].append({
                "classification": ba.classification,
                "confidence": ba.confidence,
                "reasoning": ba.reasoning[:300],
                "num_recommendations": len(ba.spread_recommendations),
            })

    if state.technical_analysis:
        current["technical_summary"] = state.technical_analysis.summary

    if state.unusual_activity:
        current["put_call_ratio"] = state.unusual_activity.put_call_ratio
        current["num_flow_anomalies"] = len(state.unusual_activity.flow_anomalies)
        current["num_block_trades"] = len(state.unusual_activity.block_trades)

    if state.news_context:
        current["news_sentiment"] = state.news_context.sentiment

    if state.market_data:
        current["current_price"] = state.market_data.current_price
        current["today_change_pct"] = state.market_data.today_change_pct

    if state.options_chain and state.options_chain.summary:
        s = state.options_chain.summary
        current["iv_rank"] = s.iv_rank
        current["avg_iv"] = (s.avg_call_iv + s.avg_put_iv) / 2 if (s.avg_call_iv + s.avg_put_iv) > 0 else 0

    sections.append(
        f"## Current Setup\n{json.dumps(current, indent=2, default=str)}"
    )

    sections.append(
        f"## Historical Theses ({len(historical)} records)\n"
        f"{json.dumps(historical, indent=2, default=str)}"
    )

    return "\n\n".join(sections)


def _parse_trap_response(response_text: str) -> list[TrapWarning]:
    """Parse Claude's response into a list of TrapWarning objects."""
    try:
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        result = json.loads(json_str.strip())
        warnings_data = result.get("trap_warnings", [])

        return [
            TrapWarning(
                similar_thesis_id=w.get("similar_thesis_id", ""),
                similarity_score=w.get("similarity_score", 0.0),
                outcome=w.get("outcome", "unknown"),
                warning=w.get("warning", ""),
            )
            for w in warnings_data
            if w.get("warning")
        ]
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse trap detection response as JSON")
        return []
