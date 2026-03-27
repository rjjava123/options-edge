"""Technical setup analysis: directional spreads based on chart patterns and S/R levels."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState, BranchAnalysis

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

TECHNICAL_SYSTEM_PROMPT = """\
You are a senior options strategist specializing in technically-driven trades. You combine
chart pattern analysis with options structure selection for optimal risk/reward.

Your analysis framework:
1. **Pattern Assessment**: Evaluate detected chart patterns for reliability. Consider:
   - Pattern completion percentage and confirmation signals
   - Volume confirmation (is volume supporting the pattern?)
   - Timeframe relevance (daily patterns carry more weight than intraday)
   - Historical reliability of the specific pattern

2. **Support/Resistance Targeting**: Use S/R levels for strike selection:
   - Identify the primary trade target (next S/R level in the direction of the pattern)
   - Calculate the risk point (where the pattern fails)
   - Determine reward-to-risk ratio based on these levels

3. **EMA/Trend Alignment**: Confirm directional bias:
   - EMA stack alignment (9 > 21 > 50 for bullish)
   - Price position relative to key EMAs
   - MACD momentum confirmation

4. **IV as Secondary Factor**: Use IV to optimize structure, not direction:
   - High IV: prefer credit spreads (sell premium in direction of bias)
   - Low IV: prefer debit spreads (buy premium for directional exposure)
   - Normal IV: choose based on risk/reward optimization

5. **Strategy Selection**: Recommend directional debit and credit spreads:
   - Bull call spreads for bullish setups in low IV
   - Bear put spreads for bearish setups in low IV
   - Bull put spreads (credit) for bullish setups in high IV
   - Bear call spreads (credit) for bearish setups in high IV

For each recommendation provide exact strikes, expiration, entry price, max P/L,
breakevens, and probability of profit.

Return as JSON:
{
    "classification": "technical",
    "spread_recommendations": [
        {
            "strategy": "bull call spread",
            "direction": "bullish",
            "legs": [
                {"action": "buy", "type": "call", "strike": 150, "expiration": "2025-02-21"},
                {"action": "sell", "type": "call", "strike": 155, "expiration": "2025-02-21"}
            ],
            "entry_price": 2.10,
            "max_profit": 290,
            "max_loss": 210,
            "breakevens": [152.10],
            "probability_of_profit": 0.55,
            "risk_reward": 1.38,
            "rationale": "Breakout above resistance with EMA confirmation"
        }
    ],
    "reasoning": "Detailed reasoning covering pattern, S/R, trend, and IV analysis",
    "confidence": 0.70
}
"""


async def analyze_technical_setup(state: AnalysisState) -> dict:
    """Analyze a technically-driven setup focused on patterns and S/R levels.

    Examines chart pattern reliability, support/resistance targets, trend
    alignment via EMAs, and uses IV as a secondary factor for structure selection.
    Recommends directional debit and credit spreads.

    Returns a dict that updates ``branch_analyses`` with the technical analysis.
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Running technical setup analysis for %s", state.ticker)

    context = _build_technical_context(state)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=TECHNICAL_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analyze the technical setup for {state.ticker}.\n\n{context}"
                ),
            }
        ],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    analysis = _parse_branch_response(response_text, "technical")

    existing = dict(state.branch_analyses) if state.branch_analyses else {}
    existing["technical"] = analysis

    logger.info("Technical analysis complete: confidence=%.2f", analysis.confidence)

    return {"branch_analyses": existing}


def _build_technical_context(state: AnalysisState) -> str:
    """Build technical-specific context from state."""
    sections = []

    if state.market_data:
        md = state.market_data
        sections.append(f"Current Price: ${md.price:.2f} | Volume: {md.volume:,}")

        # Include recent price history for pattern context
        recent_bars = md.ohlc_history[-20:] if md.ohlc_history else []
        if recent_bars:
            sections.append(f"Last 20 bars:\n{json.dumps(recent_bars, default=str)}")

    if state.technical_analysis:
        ta = state.technical_analysis
        sections.append(
            f"Technical Summary: {ta.summary}\n"
            f"Detected Patterns: {json.dumps(ta.patterns, default=str)}\n"
            f"Support Levels: {ta.support_levels}\n"
            f"Resistance Levels: {ta.resistance_levels}\n"
            f"Indicators: {json.dumps(ta.indicators, default=str)}"
        )

    if state.options_chain:
        oc = state.options_chain
        sections.append(
            f"Options: {len(oc.contracts)} contracts\n"
            f"Greeks summary: {json.dumps(oc.greeks, default=str)}"
        )

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
