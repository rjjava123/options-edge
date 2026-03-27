"""Synthesize all branch analyses and trap warnings into a final trade thesis."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState
from app.models.state import Thesis as ThesisState

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

SYNTHESIS_SYSTEM_PROMPT = """\
You are a senior portfolio manager making the final trade decision. You have received
analyses from multiple specialist branches and trap detection warnings. Your job is to
synthesize everything into a single, actionable trade thesis.

Decision framework:
1. **Consensus Check**: Do the branch analyses agree on direction? Conflicting signals
   should lower confidence. Unanimous direction should increase it.

2. **Best Structure Selection**: From all recommended spreads across branches, select
   the single best trade structure considering:
   - Risk/reward ratio
   - Probability of profit
   - Alignment with the strongest branch analysis
   - Simplicity (prefer simpler structures when edge is similar)

3. **Trap Warning Integration**: If trap warnings exist:
   - Reduce confidence proportionally to similarity scores
   - Consider if the current setup has mitigating factors
   - If trap warnings are severe (similarity > 0.8), consider passing on the trade

4. **Position Sizing Guidance**: Based on confidence level:
   - High confidence (>0.75): full position
   - Medium confidence (0.50-0.75): half position
   - Low confidence (<0.50): quarter position or pass

5. **Exit Strategy**: Define clear exit rules:
   - Profit target: where to take gains
   - Stop loss: where to cut losses
   - Time stop: close by what DTE to avoid gamma risk

You MUST return a complete thesis as JSON with this exact structure:
{
    "ticker": "AAPL",
    "direction": "bullish" | "bearish" | "neutral",
    "spread_type": "bull call spread" | "bear put spread" | "iron condor" | etc.,
    "short_strike": 155.0,
    "long_strike": 150.0,
    "expiration_date": "2025-02-21",
    "entry_price": 2.30,
    "max_profit": 270.0,
    "max_loss": 230.0,
    "profit_target": 200.0,
    "stop_loss": 150.0,
    "confidence": 0.72,
    "reasoning": "Comprehensive reasoning synthesizing all branches, including why this structure was chosen over alternatives and how trap warnings were incorporated",
    "setup_classifications": ["technical", "flow_driven"]
}

If the overall analysis does not support a trade (too many conflicting signals, severe trap
warnings, insufficient edge), set confidence below 0.3 and explain in reasoning why the
setup should be avoided.
"""


async def synthesize_thesis(state: AnalysisState) -> dict:
    """Synthesize all analysis branches and trap warnings into a final thesis.

    Makes a final Claude call that considers all branch outputs, trap detection
    results, and overall market context to produce a single actionable thesis
    with specific strikes, expiration, entry/exit targets, and confidence.

    Returns a dict keyed by ``thesis`` for state merging.
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Synthesizing final thesis for %s", state.ticker)

    context = _build_synthesis_context(state)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=SYNTHESIS_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Synthesize the final trade thesis for {state.ticker}.\n\n{context}"
                ),
            }
        ],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    thesis = _parse_thesis_response(response_text, state)

    logger.info(
        "Thesis synthesized: %s %s %s @ $%.2f, confidence=%.2f",
        thesis.direction,
        thesis.spread_type,
        thesis.ticker,
        thesis.entry_price,
        thesis.confidence,
    )

    return {"thesis": thesis}


def _build_synthesis_context(state: AnalysisState) -> str:
    """Build the full context for thesis synthesis."""
    sections = []

    # Market overview
    if state.market_data:
        md = state.market_data
        sections.append(
            f"## Market Data\n"
            f"Price: ${md.current_price:.2f} | Volume: {md.volume:,}\n"
            f"Change: {md.today_change_pct:+.2f}% | Bid: ${md.bid:.2f} | Ask: ${md.ask:.2f}\n"
            f"VWAP: ${md.vwap:.2f} | Prev Close: ${md.prev_close:.2f}"
        )

    # Technical summary
    if state.technical_analysis:
        sections.append(f"## Technical Analysis\n{state.technical_analysis.summary}")

    # News context
    if state.news_context:
        nc = state.news_context
        sections.append(
            f"## News Context\n"
            f"Sentiment: {nc.sentiment}\n"
            f"Key headlines: {json.dumps(nc.headlines[:5], default=str)}"
        )

    # Setup classifications
    if state.setup_classifications:
        sections.append(
            f"## Setup Classifications\n{', '.join(state.setup_classifications)}"
        )

    # Branch analyses (the core input)
    if state.branch_analyses:
        for ba in state.branch_analyses.values():
            sections.append(
                f"## Branch: {ba.classification} (confidence: {ba.confidence:.2f})\n"
                f"Reasoning: {ba.reasoning}\n"
                f"Spread Recommendations:\n"
                f"{json.dumps(ba.spread_recommendations, indent=2, default=str)}"
            )

    # Trap warnings
    if state.trap_warnings:
        warnings = [
            {
                "similar_thesis_id": tw.similar_thesis_id,
                "similarity_score": tw.similarity_score,
                "outcome": tw.outcome,
                "warning": tw.warning,
            }
            for tw in state.trap_warnings
        ]
        sections.append(
            f"## Trap Warnings ({len(warnings)})\n"
            f"{json.dumps(warnings, indent=2, default=str)}"
        )
    else:
        sections.append("## Trap Warnings\nNone detected.")

    return "\n\n".join(sections)


def _parse_thesis_response(response_text: str, state: AnalysisState) -> ThesisState:
    """Parse Claude's JSON response into a Thesis state object."""
    try:
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        result = json.loads(json_str.strip())

        return ThesisState(
            ticker=result.get("ticker", state.ticker),
            direction=result.get("direction", "neutral"),
            spread_type=result.get("spread_type", "unknown"),
            short_strike=float(result.get("short_strike", 0)),
            long_strike=float(result.get("long_strike", 0)),
            expiration_date=result.get("expiration_date", ""),
            entry_price=float(result.get("entry_price", 0)),
            max_profit=float(result.get("max_profit", 0)),
            max_loss=float(result.get("max_loss", 0)),
            profit_target=float(result.get("profit_target", 0)),
            stop_loss=float(result.get("stop_loss", 0)),
            confidence=float(result.get("confidence", 0)),
            reasoning=result.get("reasoning", ""),
            setup_classifications=result.get(
                "setup_classifications",
                state.setup_classifications or [],
            ),
        )
    except (json.JSONDecodeError, IndexError, ValueError):
        logger.exception("Failed to parse thesis synthesis response")
        return ThesisState(
            ticker=state.ticker,
            direction="neutral",
            spread_type="unknown",
            short_strike=0,
            long_strike=0,
            expiration_date="",
            entry_price=0,
            max_profit=0,
            max_loss=0,
            profit_target=0,
            stop_loss=0,
            confidence=0,
            reasoning=f"Failed to parse synthesis. Raw: {response_text[:500]}",
            setup_classifications=state.setup_classifications or [],
        )
