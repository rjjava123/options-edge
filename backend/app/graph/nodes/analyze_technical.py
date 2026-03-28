"""Technical setup analysis: directional spreads based on chart patterns and S/R levels."""

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
            "spread_type": "bull call spread",
            "direction": "bullish",
            "legs": [
                {"action": "buy", "contract_type": "call", "strike": 150, "expiration": "2025-02-21"},
                {"action": "sell", "contract_type": "call", "strike": 155, "expiration": "2025-02-21"}
            ],
            "entry_price": 2.10,
            "max_profit": 290,
            "max_loss": 210,
            "breakevens": [152.10],
            "probability_of_profit": 0.55,
            "confidence": 0.70,
            "rationale": "Breakout above resistance with EMA confirmation"
        }
    ],
    "reasoning": "Detailed reasoning covering pattern, S/R, trend, and IV analysis",
    "confidence": 0.70
}
"""


async def analyze_technical_setup(state: AnalysisState) -> dict:
    """Analyze a technically-driven setup focused on patterns and S/R levels."""
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
        sections.append(
            f"Current Price: ${md.current_price:.2f} | Prev Close: ${md.prev_close:.2f}\n"
            f"Change: {md.today_change_pct:+.2f}% | Volume: {md.volume:,}\n"
            f"VWAP: ${md.vwap:.2f}"
        )

        # Include recent price history for pattern context
        if md.ohlc_history:
            recent_bars = md.ohlc_history[-20:]
            bar_data = [
                {
                    "date": b.timestamp,
                    "O": b.open,
                    "H": b.high,
                    "L": b.low,
                    "C": b.close,
                    "V": b.volume,
                }
                for b in recent_bars
            ]
            sections.append(f"Last {len(recent_bars)} bars:\n{json.dumps(bar_data, default=str)}")

    if state.technical_analysis:
        ta = state.technical_analysis
        sections.append(f"Technical Summary: {ta.summary}")

        if ta.patterns:
            pattern_data = [
                {
                    "name": p.name,
                    "type": p.type,
                    "confidence": p.confidence,
                    "price_level": p.price_level,
                }
                for p in ta.patterns
            ]
            sections.append(f"Detected Patterns:\n{json.dumps(pattern_data, indent=2)}")

        if ta.support_levels:
            sections.append(
                f"Support Levels: {', '.join(f'${s:.2f}' for s in ta.support_levels)}"
            )
        if ta.resistance_levels:
            sections.append(
                f"Resistance Levels: {', '.join(f'${r:.2f}' for r in ta.resistance_levels)}"
            )

        if ta.indicators:
            ind = ta.indicators
            sections.append(
                f"Indicators: RSI={ind.rsi_14:.1f} EMA9=${ind.ema_9:.2f} "
                f"EMA21=${ind.ema_21:.2f} EMA50=${ind.ema_50:.2f} "
                f"MACD={ind.macd_line:.4f} Signal={ind.signal_line:.4f} "
                f"Hist={ind.macd_histogram:.4f} Trend={ind.trend} MACD_Signal={ind.macd_signal}"
            )

    if state.options_chain:
        oc = state.options_chain
        sections.append(f"Options: {len(oc.contracts)} contracts")
        if oc.summary:
            s = oc.summary
            sections.append(
                f"Avg Call IV: {s.avg_call_iv:.4f} | Avg Put IV: {s.avg_put_iv:.4f}\n"
                f"Total OI: {s.total_oi:,}"
            )
            if s.iv_rank is not None:
                sections.append(f"IV Rank: {s.iv_rank:.1f}")

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
