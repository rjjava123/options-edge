"""Classify the trading setup into analysis categories using Claude."""

from __future__ import annotations

import json
import logging

from anthropic import AsyncAnthropic

from app.config import get_settings
from app.models.state import AnalysisState

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-20250514"

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
            f"Price: ${md.price:.2f}\n"
            f"Volume: {md.volume:,}\n"
            f"Quote: {json.dumps(md.quote, default=str)}\n"
            f"History bars: {len(md.ohlc_history)}"
        )

    # Technical analysis
    if state.technical_analysis:
        ta = state.technical_analysis
        sections.append(
            f"## Technical Analysis\n"
            f"Summary: {ta.summary}\n"
            f"Patterns: {', '.join(ta.patterns) if ta.patterns else 'None'}\n"
            f"Support: {ta.support_levels}\n"
            f"Resistance: {ta.resistance_levels}\n"
            f"Indicators: {json.dumps(ta.indicators, default=str)}"
        )

    # Options chain summary
    if state.options_chain:
        oc = state.options_chain
        sections.append(
            f"## Options Chain\n"
            f"Contracts: {len(oc.contracts)}\n"
            f"Expirations: {', '.join(oc.expirations)}\n"
            f"Greeks summary: {json.dumps(oc.greeks, default=str)}"
        )

    # Unusual activity
    if state.unusual_activity:
        ua = state.unusual_activity
        sections.append(
            f"## Unusual Activity\n"
            f"Put/Call ratio: {ua.put_call_ratio:.3f}\n"
            f"Flow anomalies: {len(ua.flow_anomalies)}\n"
            f"Block trades: {len(ua.block_trades)}\n"
            f"OI outliers: {len(ua.oi_changes)}\n"
            f"Top anomalies: {json.dumps(ua.flow_anomalies[:5], default=str)}\n"
            f"Top blocks: {json.dumps(ua.block_trades[:5], default=str)}"
        )

    # News context
    if state.news_context:
        nc = state.news_context
        sections.append(
            f"## News Context\n"
            f"Sentiment: {nc.sentiment}\n"
            f"Headlines: {json.dumps(nc.headlines[:10], default=str)}\n"
            f"Analyst actions: {json.dumps(nc.analyst_actions, default=str)}"
        )

    return "\n\n".join(sections) if sections else "No data gathered yet."
