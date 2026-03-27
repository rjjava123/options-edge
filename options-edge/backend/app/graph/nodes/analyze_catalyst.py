"""Catalyst-driven setup analysis: earnings, events, IV crush, and event spreads."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState, BranchAnalysis

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

CATALYST_SYSTEM_PROMPT = """\
You are a senior options strategist specializing in catalyst-driven trades. Your expertise is in
pricing binary events, earnings moves, and IV crush dynamics.

Your analysis framework:
1. **Event Identification**: What is the catalyst? When does it occur? Is it priced in?
2. **Implied vs Historical Move**: Compare the current implied move (from ATM straddle pricing)
   to historical earnings/event moves. Is IV overstating or understating the expected move?
3. **IV Crush Analysis**: Calculate expected IV crush post-event. What is the theta decay
   profile? How much premium is at risk from IV contraction alone?
4. **Skew Analysis**: Is the put/call skew telling a story? Is downside protection bid up
   more than usual? Are OTM calls showing unusual demand?
5. **Strategy Selection**: Based on the above, recommend specific spreads:
   - If IV overstated: iron condors, short straddles/strangles, credit spreads
   - If IV understated: debit spreads, long straddles, calendar spreads
   - Mixed: bull/bear spreads with defined risk

For each recommended spread, provide:
- Exact strikes and expiration
- Entry price estimate, max profit, max loss
- Breakeven points
- Probability of profit estimate
- Risk/reward ratio
- Confidence level (0.0 - 1.0)

Return your analysis as JSON:
{
    "classification": "catalyst",
    "spread_recommendations": [
        {
            "strategy": "iron condor / bull call spread / etc.",
            "direction": "bullish / bearish / neutral",
            "legs": [
                {"action": "sell/buy", "type": "call/put", "strike": 150, "expiration": "2025-02-21"}
            ],
            "entry_price": 1.50,
            "max_profit": 150,
            "max_loss": 350,
            "breakevens": [148.5, 156.5],
            "probability_of_profit": 0.62,
            "risk_reward": 0.43,
            "rationale": "why this specific structure"
        }
    ],
    "reasoning": "Detailed reasoning covering event analysis, IV, skew, and timing",
    "confidence": 0.75
}
"""


async def analyze_catalyst_setup(state: AnalysisState) -> dict:
    """Analyze a catalyst-driven setup with focus on event pricing and IV dynamics.

    Examines earnings moves vs implied, IV crush expectations, skew analysis,
    and timing. Considers bull/bear spreads, iron condors, and event-driven
    structures.

    Returns a dict that updates ``branch_analyses`` with the catalyst analysis.
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Running catalyst analysis for %s", state.ticker)

    context = _build_catalyst_context(state)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=CATALYST_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analyze the catalyst-driven setup for {state.ticker}.\n\n{context}"
                ),
            }
        ],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    analysis = _parse_branch_response(response_text, "catalyst")

    existing = dict(state.branch_analyses) if state.branch_analyses else {}
    existing["catalyst"] = analysis

    logger.info("Catalyst analysis complete: confidence=%.2f", analysis.confidence)

    return {"branch_analyses": existing}


def _build_catalyst_context(state: AnalysisState) -> str:
    """Build catalyst-specific context from state."""
    sections = []

    if state.market_data:
        md = state.market_data
        sections.append(
            f"Current Price: ${md.price:.2f} | Volume: {md.volume:,}\n"
            f"Quote: {json.dumps(md.quote, default=str)}"
        )

    if state.options_chain:
        oc = state.options_chain
        # Find ATM straddle for implied move calculation
        atm_contracts = _find_atm_contracts(oc.contracts, state.market_data.price if state.market_data else 0)
        sections.append(
            f"Options Chain: {len(oc.contracts)} contracts, "
            f"Expirations: {', '.join(oc.expirations)}\n"
            f"Greeks: {json.dumps(oc.greeks, default=str)}\n"
            f"ATM contracts: {json.dumps(atm_contracts, default=str)}"
        )

    if state.news_context:
        nc = state.news_context
        sections.append(
            f"News Sentiment: {nc.sentiment}\n"
            f"Headlines: {json.dumps(nc.headlines[:10], default=str)}\n"
            f"Analyst Actions: {json.dumps(nc.analyst_actions, default=str)}"
        )

    if state.technical_analysis:
        sections.append(f"Technical Summary: {state.technical_analysis.summary}")

    if state.unusual_activity:
        ua = state.unusual_activity
        sections.append(
            f"Unusual Activity: P/C ratio={ua.put_call_ratio:.3f}, "
            f"{len(ua.block_trades)} block trades, "
            f"{len(ua.flow_anomalies)} flow anomalies"
        )

    return "\n\n".join(sections)


def _find_atm_contracts(contracts: list[dict], current_price: float) -> list[dict]:
    """Find the nearest ATM call and put contracts."""
    if not contracts or current_price <= 0:
        return []

    atm: list[dict] = []
    for ct in ("call", "put"):
        type_contracts = [c for c in contracts if c.get("contract_type") == ct]
        if type_contracts:
            nearest = min(
                type_contracts,
                key=lambda c: abs(c.get("strike_price", 0) - current_price),
            )
            atm.append(nearest)
    return atm


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
