"""Mean reversion setup analysis: credit spreads, IV rank, theta decay."""

from __future__ import annotations

import json
import logging
import math

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState, BranchAnalysis, SpreadCandidate, SpreadLeg

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

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
            "spread_type": "bull put spread",
            "direction": "bullish (mean reversion)",
            "legs": [
                {"action": "sell", "contract_type": "put", "strike": 145, "expiration": "2025-02-21"},
                {"action": "buy", "contract_type": "put", "strike": 140, "expiration": "2025-02-21"}
            ],
            "entry_price": 1.80,
            "max_profit": 180,
            "max_loss": 320,
            "breakevens": [143.20],
            "probability_of_profit": 0.68,
            "confidence": 0.65,
            "rationale": "RSI at 22 with 3-sigma selloff; selling elevated put premium"
        }
    ],
    "reasoning": "Detailed reasoning covering extension analysis, IV, skew, theta, and credit optimization",
    "confidence": 0.65
}
"""


async def analyze_mean_reversion_setup(state: AnalysisState) -> dict:
    """Analyze a mean reversion setup with focus on credit spreads and IV."""
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
        sections.append(
            f"Current Price: ${md.current_price:.2f} | Prev Close: ${md.prev_close:.2f}\n"
            f"Change: {md.today_change_pct:+.2f}% | Volume: {md.volume:,}"
        )

        # Calculate extension metrics from history
        if md.ohlc_history and len(md.ohlc_history) >= 20:
            closes = [b.close for b in md.ohlc_history if b.close > 0]
            if len(closes) >= 20:
                mean_20 = sum(closes[-20:]) / 20
                pct_from_mean = ((md.current_price - mean_20) / mean_20) * 100
                sections.append(
                    f"20-day mean: ${mean_20:.2f} | "
                    f"Extension from mean: {pct_from_mean:+.2f}%"
                )

                # Calculate realized volatility
                if len(closes) >= 21:
                    log_returns = [
                        math.log(closes[i] / closes[i - 1])
                        for i in range(1, len(closes))
                        if closes[i - 1] > 0
                    ]
                    recent_returns = log_returns[-20:]
                    if recent_returns:
                        mean_ret = sum(recent_returns) / len(recent_returns)
                        variance = sum(
                            (r - mean_ret) ** 2 for r in recent_returns
                        ) / len(recent_returns)
                        rv_20 = math.sqrt(variance * 252) * 100
                        sections.append(f"Realized Volatility (20d): {rv_20:.1f}%")

    if state.technical_analysis:
        ta = state.technical_analysis
        sections.append(f"Technical Summary: {ta.summary}")

        if ta.indicators:
            ind = ta.indicators
            sections.append(
                f"RSI(14): {ind.rsi_14:.1f} | Trend: {ind.trend}\n"
                f"EMA 9: ${ind.ema_9:.2f} | EMA 21: ${ind.ema_21:.2f} | "
                f"EMA 50: ${ind.ema_50:.2f}"
            )

        if ta.support_levels:
            sections.append(
                f"Support: {', '.join(f'${s:.2f}' for s in ta.support_levels)}"
            )
        if ta.resistance_levels:
            sections.append(
                f"Resistance: {', '.join(f'${r:.2f}' for r in ta.resistance_levels)}"
            )

    if state.options_chain:
        oc = state.options_chain
        sections.append(f"Options: {len(oc.contracts)} contracts")
        sections.append(f"Expirations: {', '.join(oc.expirations)}")
        if oc.summary:
            s = oc.summary
            sections.append(
                f"Avg Call IV: {s.avg_call_iv:.4f} | Avg Put IV: {s.avg_put_iv:.4f}\n"
                f"Total OI: {s.total_oi:,} | P/C OI Ratio: {s.put_call_oi_ratio:.3f}"
            )
            if s.iv_rank is not None:
                sections.append(f"IV Rank: {s.iv_rank:.1f}")

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
