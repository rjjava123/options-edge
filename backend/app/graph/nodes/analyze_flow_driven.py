"""Flow-driven setup analysis: following institutional positioning and order flow."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState, BranchAnalysis, SpreadCandidate, SpreadLeg

logger = logging.getLogger(__name__)

def _safe_float(value, default: float = 0.0) -> float:
    """Extract a numeric value from potentially messy LLM output."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Try to extract the first number from the string
        import re
        match = re.search(r'-?[\d,]+\.?\d*', value.replace(',', ''))
        if match:
            return float(match.group())
    return default

MODEL = "claude-sonnet-4-6"

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
            "spread_type": "bull call spread",
            "direction": "bullish",
            "legs": [
                {"action": "buy", "contract_type": "call", "strike": 155, "expiration": "2025-03-21"},
                {"action": "sell", "contract_type": "call", "strike": 160, "expiration": "2025-03-21"}
            ],
            "entry_price": 2.30,
            "max_profit": 270,
            "max_loss": 230,
            "breakevens": [157.30],
            "probability_of_profit": 0.48,
            "confidence": 0.60,
            "rationale": "Institutional block buying at March 155 calls with 3x OI volume"
        }
    ],
    "reasoning": "Detailed reasoning covering flow classification, institutional patterns, and trade alignment",
    "confidence": 0.60
}
"""


async def analyze_flow_driven_setup(state: AnalysisState) -> dict:
    """Analyze a flow-driven setup by interpreting unusual options activity."""
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
        sections.append(
            f"Current Price: ${md.current_price:.2f} | Volume: {md.volume:,}\n"
            f"Change: {md.today_change_pct:+.2f}%"
        )

    if state.unusual_activity:
        ua = state.unusual_activity
        sections.append(
            f"## Unusual Activity (Primary Data)\n"
            f"Put/Call Ratio: {ua.put_call_ratio:.3f}"
        )

        if ua.flow_anomalies:
            anomaly_data = [
                {
                    "contract_type": a.contract_type,
                    "strike": a.strike,
                    "expiration": a.expiration,
                    "volume": a.volume,
                    "oi": a.oi,
                    "volume_oi_ratio": a.volume_oi_ratio,
                    "is_opening": a.is_opening,
                }
                for a in ua.flow_anomalies
            ]
            sections.append(
                f"Flow Anomalies ({len(ua.flow_anomalies)}):\n"
                f"{json.dumps(anomaly_data, indent=2)}"
            )

        if ua.block_trades:
            block_data = [
                {
                    "contract_type": b.contract_type,
                    "strike": b.strike,
                    "expiration": b.expiration,
                    "size": b.size,
                    "premium": b.premium,
                    "direction": b.direction,
                }
                for b in ua.block_trades
            ]
            sections.append(
                f"Block Trades ({len(ua.block_trades)}):\n"
                f"{json.dumps(block_data, indent=2)}"
            )

        if ua.oi_changes:
            oi_data = [
                {
                    "contract_type": o.contract_type,
                    "strike": o.strike,
                    "expiration": o.expiration,
                    "prev_oi": o.prev_oi,
                    "current_oi": o.current_oi,
                    "change_pct": o.change_pct,
                }
                for o in ua.oi_changes
            ]
            sections.append(
                f"OI Outliers ({len(ua.oi_changes)}):\n"
                f"{json.dumps(oi_data, indent=2)}"
            )

    if state.options_chain:
        oc = state.options_chain
        # Provide high-volume contracts for flow analysis
        sorted_contracts = sorted(
            oc.contracts,
            key=lambda c: c.volume,
            reverse=True,
        )[:20]
        high_vol_data = [
            {
                "contract_type": c.contract_type,
                "strike": c.strike_price,
                "expiration": c.expiration_date,
                "volume": c.volume,
                "oi": c.open_interest,
                "last_price": c.last_price,
                "iv": c.implied_volatility,
                "delta": c.delta,
            }
            for c in sorted_contracts
        ]
        sections.append(
            f"## Top 20 Contracts by Volume\n"
            f"{json.dumps(high_vol_data, indent=2)}"
        )
        if oc.summary:
            s = oc.summary
            sections.append(
                f"Total Call Vol: {s.total_call_volume:,} | Total Put Vol: {s.total_put_volume:,}\n"
                f"Total Call OI: {s.total_call_oi:,} | Total Put OI: {s.total_put_oi:,}"
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

        spread_recs = []
        for rec in result.get("spread_recommendations", []):
            legs = [
                SpreadLeg(
                    contract_type=leg.get("contract_type", leg.get("type", "")),
                    strike=leg.get("strike", 0),
                    expiration=leg.get("expiration", ""),
                    action=leg.get("action", "buy"),
                )
                for leg in rec.get("legs", [])
            ]
            spread_recs.append(SpreadCandidate(
                spread_type=rec.get("spread_type", rec.get("strategy", "")),
                direction=rec.get("direction", ""),
                legs=legs,
                entry_price=_safe_float(rec.get("entry_price", 0)),
                max_profit=_safe_float(rec.get("max_profit", 0)),
                max_loss=_safe_float(rec.get("max_loss", 0)),
                breakevens=[_safe_float(b) for b in rec.get("breakevens", []) if _safe_float(b) > 0],
                probability_of_profit=_safe_float(rec.get("probability_of_profit", 0)),
                confidence=_safe_float(rec.get("confidence", result.get("confidence", 0))),
                rationale=str(rec.get("rationale", "")),
            ))

        reasoning_raw = result.get("reasoning", "")
        reasoning = json.dumps(reasoning_raw, indent=2) if isinstance(reasoning_raw, dict) else str(reasoning_raw)

        return BranchAnalysis(
            classification=classification,
            spread_recommendations=spread_recs,
            reasoning=reasoning,
            confidence=result.get("confidence", 0.0),
        )
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse %s analysis response as JSON", classification)
        return BranchAnalysis(
            classification=classification,
            reasoning=response_text[:1000],
            confidence=0.0,
        )
