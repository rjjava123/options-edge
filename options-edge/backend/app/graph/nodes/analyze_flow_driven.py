"""Flow-driven setup analysis: following institutional positioning and order flow."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState, BranchAnalysis

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

FLOW_DRIVEN_SYSTEM_PROMPT = """\
You are a senior options strategist specializing in order-flow analysis. Your expertise is in
reading institutional positioning through options activity and structuring trades that follow
smart money flow.

Your analysis framework:
1. **Opening vs Closing Analysis**: Determine if activity is new positioning or closing:
   - Volume significantly exceeding open interest = likely new opening positions
   - Volume with decreasing OI the next day = likely closing
   - Multi-day OI buildup at a strike = accumulation pattern
   - Consider the delta of the options being traded (OTM vs ITM)

2. **Hedge vs Directional**: Classify the likely intent:
   - Large put buying with existing long stock positions = hedging (not bearish)
   - Call buying with no visible stock position = directional bullish bet
   - Spread activity (buying one strike, selling another) = defined-risk directional
   - Collar activity = protective, may signal concern
   - Ratio spreads = complex positioning, often institutional

3. **Institutional Patterns**: Identify smart money signatures:
   - Block trades (100+ contracts in single print) = institutional
   - Sweep orders (hitting multiple exchanges rapidly) = urgency
   - Dark pool correlation (unusual volume without price movement)
   - Consistent accumulation at specific strikes over multiple days
   - Roll patterns (closing one month, opening the next)

4. **Flow Direction**: Determine net directional bias:
   - Net call delta vs net put delta
   - Premium direction (is more premium being bought or sold?)
   - Skew of activity (are trades concentrated on one side?)

5. **Trade Structure**: Follow the flow with appropriate spreads:
   - Mirror institutional strikes when possible
   - Use defined-risk structures (spreads) to follow undefined-risk flow
   - Match expiration to the observed flow timeframe
   - Consider the Greeks of the flow contracts for cloning

Return as JSON:
{
    "classification": "flow_driven",
    "spread_recommendations": [
        {
            "strategy": "bull call spread",
            "direction": "bullish",
            "legs": [
                {"action": "buy", "type": "call", "strike": 155, "expiration": "2025-03-21"},
                {"action": "sell", "type": "call", "strike": 160, "expiration": "2025-03-21"}
            ],
            "entry_price": 2.30,
            "max_profit": 270,
            "max_loss": 230,
            "breakevens": [157.30],
            "probability_of_profit": 0.48,
            "risk_reward": 1.17,
            "flow_alignment": "Mirroring 2,500-lot call buying at 155 strike",
            "rationale": "Institutional block buying at March 155 calls with 3x OI volume"
        }
    ],
    "reasoning": "Detailed reasoning covering flow classification, institutional patterns, and trade alignment",
    "confidence": 0.60
}
"""


async def analyze_flow_driven_setup(state: AnalysisState) -> dict:
    """Analyze a flow-driven setup by interpreting unusual options activity.

    Examines opening vs closing flow, hedge vs directional intent, institutional
    patterns, and net flow direction to recommend trades aligned with smart money.

    Returns a dict that updates ``branch_analyses`` with the flow-driven analysis.
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Running flow-driven analysis for %s", state.ticker)

    context = _build_flow_context(state)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=FLOW_DRIVEN_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analyze the order flow setup for {state.ticker}.\n\n{context}"
                ),
            }
        ],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    analysis = _parse_branch_response(response_text, "flow_driven")

    existing = dict(state.branch_analyses) if state.branch_analyses else {}
    existing["flow_driven"] = analysis

    logger.info("Flow-driven analysis complete: confidence=%.2f", analysis.confidence)

    return {"branch_analyses": existing}


def _build_flow_context(state: AnalysisState) -> str:
    """Build flow-specific context from state."""
    sections = []

    if state.market_data:
        md = state.market_data
        sections.append(f"Current Price: ${md.price:.2f} | Volume: {md.volume:,}")

    if state.unusual_activity:
        ua = state.unusual_activity
        sections.append(
            f"## Unusual Activity (Primary Data)\n"
            f"Put/Call Ratio: {ua.put_call_ratio:.3f}\n"
            f"Flow Anomalies ({len(ua.flow_anomalies)}):\n"
            f"{json.dumps(ua.flow_anomalies, indent=2, default=str)}\n\n"
            f"Block Trades ({len(ua.block_trades)}):\n"
            f"{json.dumps(ua.block_trades, indent=2, default=str)}\n\n"
            f"OI Outliers ({len(ua.oi_changes)}):\n"
            f"{json.dumps(ua.oi_changes, indent=2, default=str)}"
        )

    if state.options_chain:
        oc = state.options_chain
        # Provide high-volume contracts for flow analysis
        high_vol = sorted(
            oc.contracts,
            key=lambda c: c.get("volume", 0),
            reverse=True,
        )[:20]
        sections.append(
            f"## Top 20 Contracts by Volume\n"
            f"{json.dumps(high_vol, indent=2, default=str)}\n"
            f"Greeks: {json.dumps(oc.greeks, default=str)}"
        )

    if state.technical_analysis:
        sections.append(f"Technical Summary: {state.technical_analysis.summary}")

    return "\n\n".join(sections)


def _parse_branch_response(response_text: str, classification: str) -> BranchAnalysis:
    """Parse Claude's JSON response into a BranchAnalysis object."""
    try:
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        result = json.loads(json_str.strip())
        return BranchAnalysis(
            classification=classification,
            spread_recommendations=result.get("spread_recommendations", []),
            reasoning=result.get("reasoning", ""),
            confidence=result.get("confidence", 0.0),
        )
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse %s analysis response as JSON", classification)
        return BranchAnalysis(
            classification=classification,
            reasoning=response_text[:1000],
            confidence=0.0,
        )
