"""Classify the trading setup into analysis categories using Claude."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

VALID_CLASSIFICATIONS = frozenset({
    "catalyst",
    "technical",
    "mean_reversion",
    "flow_driven",
    "range_bound",
})

CLASSIFICATION_SYSTEM_PROMPT = """\
You are a senior options strategist tasked with classifying a trading setup into one or more
analysis categories. Each category triggers a specialized analysis branch.

Categories:
- **catalyst**: A material event is imminent or recently occurred (earnings, FDA, M&A, guidance).
  Elevated IV and clear binary outcome expected. Triggers analysis of IV crush, event pricing,
  and straddle/strangle/spread strategies around the event.

- **technical**: A clear chart pattern or technical level is in play (breakout, breakdown, trend
  continuation, S/R test). Price action and pattern reliability are primary drivers.
  Triggers directional spread analysis.

- **mean_reversion**: Price has extended significantly from mean (RSI extreme, Bollinger Band
  breach, multi-sigma move). IV rank is elevated. Triggers credit spread and theta decay analysis
  focused on reversion to mean.

- **flow_driven**: Unusual options activity is the primary signal (block trades, sweep orders,
  extreme volume/OI ratios, significant new positioning). Triggers analysis that follows
  institutional flow direction.

- **range_bound**: Price is consolidating within a defined range with no clear directional bias.
  Realized vol is below implied vol. Triggers iron condor and premium selling analysis.

Rules:
- You MUST select at least ONE and at most THREE categories.
- Order categories by relevance (most relevant first).
- Consider all available data: market data, technicals, options chain, unusual activity, and news.
- If data is mixed or unclear, prefer fewer categories with higher conviction.

Return your response as JSON with this exact structure:
{
    "classifications": ["category1", "category2"],
    "reasoning": {
        "category1": "Brief explanation of why this category applies",
        "category2": "Brief explanation of why this category applies"
    }
}
"""


async def classify_context(state: AnalysisState) -> dict:
    """Classify the current setup into analysis branch categories.

    Makes an LLM call to Claude with all gathered data (market data, technicals,
    options chain, unusual activity, news) and determines which analysis
    branches to run.

    Returns a dict keyed by ``setup_classifications`` (list of category strings).
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    logger.info("Classifying setup context for %s", state.ticker)

    # Build context from all gathered state
    context = _build_context_summary(state)

    response = await client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=CLASSIFICATION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Classify the following trading setup for {state.ticker} "
                    f"(flow_type: {state.flow_type}):\n\n{context}"
                ),
            }
        ],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    # Parse classifications from JSON response
    try:
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        result = json.loads(json_str.strip())
        classifications = result.get("classifications", [])
    except (json.JSONDecodeError, IndexError):
        logger.warning("Failed to parse classification response, defaulting to technical")
        classifications = ["technical"]

    # Validate and filter classifications
    valid = [c for c in classifications if c in VALID_CLASSIFICATIONS]
    if not valid:
        valid = ["technical"]  # safe default
    valid = valid[:3]  # enforce max of 3

    logger.info("Setup classified as: %s", valid)

    return {"setup_classifications": valid}


def _build_context_summary(state: AnalysisState) -> str:
    """Build a text summary of all gathered state for the classification prompt."""
    sections: list[str] = []

    # Market data
    if state.market_data:
        md = state.market_data
        sections.append(
            f"## Market Data\n"
            f"Price: ${md.current_price:.2f}\n"
            f"Previous Close: ${md.prev_close:.2f}\n"
            f"Change: {md.today_change_pct:+.2f}%\n"
            f"Volume: {md.volume:,}\n"
            f"Bid: ${md.bid:.2f} | Ask: ${md.ask:.2f}\n"
            f"VWAP: ${md.vwap:.2f}\n"
            f"History bars: {len(md.ohlc_history)}"
        )

    # Technical analysis
    if state.technical_analysis:
        ta = state.technical_analysis
        sections.append(
            f"## Technical Analysis\n"
            f"Summary: {ta.summary}\n"
        )

        if ta.patterns:
            pattern_names = [p.name for p in ta.patterns]
            sections.append(f"Patterns: {', '.join(pattern_names)}")

        if ta.support_levels:
            sections.append(
                f"Support: {', '.join(f'${s:.2f}' for s in ta.support_levels)}"
            )
        if ta.resistance_levels:
            sections.append(
                f"Resistance: {', '.join(f'${r:.2f}' for r in ta.resistance_levels)}"
            )

        if ta.indicators:
            ind = ta.indicators
            sections.append(
                f"RSI(14): {ind.rsi_14:.1f} | Trend: {ind.trend} | "
                f"MACD: {ind.macd_signal}\n"
                f"EMA 9: ${ind.ema_9:.2f} | EMA 21: ${ind.ema_21:.2f} | "
                f"EMA 50: ${ind.ema_50:.2f}"
            )

    # Options chain summary
    if state.options_chain:
        oc = state.options_chain
        sections.append(
            f"## Options Chain\n"
            f"Contracts: {len(oc.contracts)}\n"
            f"Expirations: {', '.join(oc.expirations)}"
        )
        if oc.summary:
            s = oc.summary
            sections.append(
                f"Avg Call IV: {s.avg_call_iv:.4f} | Avg Put IV: {s.avg_put_iv:.4f}\n"
                f"Total Call OI: {s.total_call_oi:,} | Total Put OI: {s.total_put_oi:,}\n"
                f"Total Call Vol: {s.total_call_volume:,} | Total Put Vol: {s.total_put_volume:,}\n"
                f"P/C OI Ratio: {s.put_call_oi_ratio:.3f}\n"
                f"IV Rank: {s.iv_rank:.1f}" if s.iv_rank is not None else "IV Rank: N/A"
            )

    # Unusual activity
    if state.unusual_activity:
        ua = state.unusual_activity
        sections.append(
            f"## Unusual Activity\n"
            f"Put/Call ratio: {ua.put_call_ratio:.3f}\n"
            f"Flow anomalies: {len(ua.flow_anomalies)}\n"
            f"Block trades: {len(ua.block_trades)}\n"
            f"OI outliers: {len(ua.oi_changes)}"
        )

        if ua.flow_anomalies:
            top_anomalies = ua.flow_anomalies[:5]
            anomaly_strs = []
            for a in top_anomalies:
                anomaly_strs.append(
                    f"  {a.contract_type.upper()} ${a.strike:.2f} {a.expiration} "
                    f"Vol={a.volume:,} OI={a.oi:,} Ratio={a.volume_oi_ratio:.1f}x"
                )
            sections.append("Top anomalies:\n" + "\n".join(anomaly_strs))

        if ua.block_trades:
            top_blocks = ua.block_trades[:5]
            block_strs = []
            for b in top_blocks:
                block_strs.append(
                    f"  {b.contract_type.upper()} ${b.strike:.2f} {b.expiration} "
                    f"Size={b.size:,} Premium=${b.premium:,.0f} ({b.direction})"
                )
            sections.append("Top blocks:\n" + "\n".join(block_strs))

    # News context
    if state.news_context:
        nc = state.news_context
        sections.append(
            f"## News Context\n"
            f"Sentiment: {nc.sentiment}\n"
            f"Headlines ({len(nc.headlines)}): {json.dumps(nc.headlines[:10], default=str)}\n"
            f"Analyst actions: {json.dumps(nc.analyst_actions[:5], default=str)}"
        )

    return "\n\n".join(sections) if sections else "No data gathered yet."
