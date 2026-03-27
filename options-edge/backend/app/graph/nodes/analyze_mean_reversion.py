"""Mean reversion setup analysis: credit spreads, IV rank, theta decay."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState, BranchAnalysis

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

MEAN_REVERSION_SYSTEM_PROMPT = """\
You are a senior options strategist specializing in mean reversion trades. Your expertise is in
identifying overextended moves and structuring credit spreads to profit from reversion.

Your analysis framework:
1. **Extension Assessment**: Quantify how overextended the move is:
   - RSI extremes (above 75 or below 25 are significant; above 80/below 20 are extreme)
   - Standard deviation from moving averages (2+ sigma is notable)
   - Percentage move from recent mean (20-day or 50-day MA)
   - Rate of change (how quickly did the extension happen?)

2. **IV Rank & Percentile**: Critical for credit spread viability:
   - Current IV rank relative to 52-week range
   - IV percentile (what % of time IV has been lower)
   - Is IV elevated due to the extension, or from external catalysts?
   - IV term structure: is near-term IV elevated vs. deferred?

3. **Skew Analysis**: Put/call skew informs strike selection:
   - After a selloff: puts may be bid up (good for selling put spreads)
   - After a rally: calls may be cheap (better to sell call spreads)
   - Skew steepness tells you where the market sees risk

4. **Theta Decay Profile**: Optimize time decay:
   - Select expirations where theta decay is most favorable (30-45 DTE sweet spot)
   - Calculate daily theta capture relative to max loss
   - Consider gamma risk as expiration approaches

5. **Credit Maximization**: Structure for best premium collection:
   - Strike width vs credit received ratio
   - Delta of short strike (target 0.20-0.30 for good premium with margin of safety)
   - Breakeven distance as % of underlying price

Recommend credit spreads (bull put spreads for oversold, bear call spreads for overbought).

Return as JSON:
{
    "classification": "mean_reversion",
    "spread_recommendations": [
        {
            "strategy": "bull put spread",
            "direction": "bullish (mean reversion)",
            "legs": [
                {"action": "sell", "type": "put", "strike": 145, "expiration": "2025-02-21"},
                {"action": "buy", "type": "put", "strike": 140, "expiration": "2025-02-21"}
            ],
            "entry_price": 1.80,
            "max_profit": 180,
            "max_loss": 320,
            "breakevens": [143.20],
            "probability_of_profit": 0.68,
            "risk_reward": 0.56,
            "theta_per_day": 4.50,
            "iv_rank_at_entry": 72,
            "rationale": "RSI at 22 with 3-sigma selloff; selling elevated put premium"
        }
    ],
    "reasoning": "Detailed reasoning covering extension analysis, IV, skew, theta, and credit optimization",
    "confidence": 0.65
}
"""


async def analyze_mean_reversion_setup(state: AnalysisState) -> dict:
    """Analyze a mean reversion setup with focus on credit spreads and IV.

    Examines RSI extremes, IV rank vs history, skew dynamics, theta decay
    optimization, and credit maximization for spread construction.

    Returns a dict that updates ``branch_analyses`` with the mean reversion analysis.
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Running mean reversion analysis for %s", state.ticker)

    context = _build_mean_reversion_context(state)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=MEAN_REVERSION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analyze the mean reversion setup for {state.ticker}.\n\n{context}"
                ),
            }
        ],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    analysis = _parse_branch_response(response_text, "mean_reversion")

    existing = dict(state.branch_analyses) if state.branch_analyses else {}
    existing["mean_reversion"] = analysis

    logger.info("Mean reversion analysis complete: confidence=%.2f", analysis.confidence)

    return {"branch_analyses": existing}


def _build_mean_reversion_context(state: AnalysisState) -> str:
    """Build mean-reversion-specific context from state."""
    sections = []

    if state.market_data:
        md = state.market_data
        sections.append(f"Current Price: ${md.price:.2f} | Volume: {md.volume:,}")

        # Calculate extension metrics from history
        if md.ohlc_history:
            closes = [b["close"] for b in md.ohlc_history if b.get("close")]
            if len(closes) >= 20:
                mean_20 = sum(closes[-20:]) / 20
                pct_from_mean = ((md.price - mean_20) / mean_20) * 100
                sections.append(
                    f"20-day mean: ${mean_20:.2f} | "
                    f"Extension from mean: {pct_from_mean:+.2f}%"
                )

    if state.technical_analysis:
        ta = state.technical_analysis
        sections.append(
            f"Technical Summary: {ta.summary}\n"
            f"Indicators: {json.dumps(ta.indicators, default=str)}\n"
            f"Support: {ta.support_levels}\n"
            f"Resistance: {ta.resistance_levels}"
        )

    if state.options_chain:
        oc = state.options_chain
        sections.append(
            f"Options: {len(oc.contracts)} contracts\n"
            f"Greeks summary: {json.dumps(oc.greeks, default=str)}\n"
            f"Expirations: {', '.join(oc.expirations)}"
        )

    if state.unusual_activity:
        ua = state.unusual_activity
        sections.append(f"Put/Call ratio: {ua.put_call_ratio:.3f}")

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
