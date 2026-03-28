"""Range-bound setup analysis: iron condors, premium selling, and volatility arbitrage."""

from __future__ import annotations

import json
import logging
import math

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

RANGE_BOUND_SYSTEM_PROMPT = """\
You are a senior options strategist specializing in range-bound / neutral strategies.
Your expertise is in iron condors, iron butterflies, and premium selling when the underlying
is consolidating.

Your analysis framework:
1. **Range Identification**: Define the trading range:
   - Upper boundary from resistance levels and recent highs
   - Lower boundary from support levels and recent lows
   - Range duration (longer consolidation = higher confidence in range)
   - Volume behavior within range (declining volume supports range continuation)

2. **Realized vs Implied Volatility**: The core edge for premium selling:
   - Calculate recent realized volatility (20-day HV)
   - Compare to current implied volatility
   - If IV > RV: premium is rich, favorable for selling
   - IV/RV ratio > 1.2 is ideal for iron condors
   - Consider IV rank and percentile for historical context

3. **Expected Move Calculation**: Size the wings appropriately:
   - Calculate the implied expected move from ATM straddle pricing
   - Compare to the actual defined range
   - Wings should be placed outside the expected move AND the range
   - Consider 1-sigma and 2-sigma moves for different confidence levels

4. **Wing Placement**: Optimize the condor structure:
   - Short strikes at or beyond the range boundaries
   - Delta of short strikes (target 0.15-0.25 for probability of profit)
   - Wing width determines max loss and margin requirements
   - Consider asymmetric condors if range is skewed

5. **Theta and Risk Management**:
   - Target 30-45 DTE for optimal theta decay curve
   - Calculate daily theta capture as % of max loss
   - Plan adjustment triggers (when to roll, close, or widen)
   - Consider expected gamma exposure as price approaches short strikes

Return as JSON:
{
    "classification": "range_bound",
    "spread_recommendations": [
        {
            "spread_type": "iron condor",
            "direction": "neutral",
            "legs": [
                {"action": "buy", "contract_type": "put", "strike": 140, "expiration": "2025-02-21"},
                {"action": "sell", "contract_type": "put", "strike": 145, "expiration": "2025-02-21"},
                {"action": "sell", "contract_type": "call", "strike": 160, "expiration": "2025-02-21"},
                {"action": "buy", "contract_type": "call", "strike": 165, "expiration": "2025-02-21"}
            ],
            "entry_price": 2.00,
            "max_profit": 200,
            "max_loss": 300,
            "breakevens": [143.00, 162.00],
            "probability_of_profit": 0.65,
            "confidence": 0.70,
            "rationale": "IV 35% overpricing realized vol; range holding for 3 weeks"
        }
    ],
    "reasoning": "Detailed reasoning covering range, vol analysis, wing placement, and risk",
    "confidence": 0.70
}
"""


async def analyze_range_bound_setup(state: AnalysisState) -> dict:
    """Analyze a range-bound setup with focus on iron condors and premium selling."""
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Running range-bound analysis for %s", state.ticker)

    context = _build_range_context(state)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=3000,
        system=RANGE_BOUND_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analyze the range-bound setup for {state.ticker}.\n\n{context}"
                ),
            }
        ],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    analysis = _parse_branch_response(response_text, "range_bound")

    existing = dict(state.branch_analyses) if state.branch_analyses else {}
    existing["range_bound"] = analysis

    logger.info("Range-bound analysis complete: confidence=%.2f", analysis.confidence)

    return {"branch_analyses": existing}


def _build_range_context(state: AnalysisState) -> str:
    """Build range-bound-specific context from state."""
    sections = []

    if state.market_data:
        md = state.market_data
        sections.append(
            f"Current Price: ${md.current_price:.2f} | Volume: {md.volume:,}\n"
            f"Change: {md.today_change_pct:+.2f}%"
        )

        # Calculate realized volatility from history
        if md.ohlc_history and len(md.ohlc_history) >= 20:
            closes = [b.close for b in md.ohlc_history if b.close > 0]
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

            # Range over last 20 bars
            recent_bars = md.ohlc_history[-20:]
            recent_highs = [b.high for b in recent_bars if b.high > 0]
            recent_lows = [b.low for b in recent_bars if b.low > 0]
            if recent_highs and recent_lows:
                sections.append(
                    f"20-day Range: ${min(recent_lows):.2f} - ${max(recent_highs):.2f}"
                )

    if state.technical_analysis:
        ta = state.technical_analysis
        sections.append(f"Technical Summary: {ta.summary}")

        if ta.support_levels:
            sections.append(
                f"Support: {', '.join(f'${s:.2f}' for s in ta.support_levels)}"
            )
        if ta.resistance_levels:
            sections.append(
                f"Resistance: {', '.join(f'${r:.2f}' for r in ta.resistance_levels)}"
            )

        if ta.patterns:
            pattern_data = [
                {"name": p.name, "type": p.type, "confidence": p.confidence}
                for p in ta.patterns
            ]
            sections.append(f"Patterns: {json.dumps(pattern_data)}")

    if state.options_chain:
        oc = state.options_chain
        sections.append(
            f"Options: {len(oc.contracts)} contracts\n"
            f"Expirations: {', '.join(oc.expirations)}"
        )
        if oc.summary:
            s = oc.summary
            sections.append(
                f"Avg Call IV: {s.avg_call_iv:.4f} | Avg Put IV: {s.avg_put_iv:.4f}\n"
                f"Total OI: {s.total_oi:,}"
            )
            if s.iv_rank is not None:
                sections.append(f"IV Rank: {s.iv_rank:.1f}")

        # Calculate expected move from ATM straddle
        if state.market_data and state.market_data.current_price > 0:
            price = state.market_data.current_price
            atm_calls = [
                c for c in oc.contracts
                if c.contract_type == "call"
                and abs(c.strike_price - price) < price * 0.02
            ]
            atm_puts = [
                c for c in oc.contracts
                if c.contract_type == "put"
                and abs(c.strike_price - price) < price * 0.02
            ]
            if atm_calls and atm_puts:
                straddle_price = atm_calls[0].last_price + atm_puts[0].last_price
                if straddle_price > 0:
                    expected_move_pct = (straddle_price / price) * 100
                    sections.append(
                        f"ATM Straddle: ${straddle_price:.2f} "
                        f"(Expected Move: {expected_move_pct:.1f}%)"
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
