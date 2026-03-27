"""Run technical analysis on price history to detect patterns and key levels."""

from __future__ import annotations

import logging

from app.models.state import AnalysisState, TechnicalAnalysis
from app.technicals import (
    compute_ema,
    compute_macd,
    compute_rsi,
    compute_vwap,
    detect_chart_patterns,
    find_support_resistance,
)

logger = logging.getLogger(__name__)


async def detect_technical_patterns(state: AnalysisState) -> dict:
    """Compute technical indicators and detect chart patterns.

    Runs the following analyses on OHLC history from ``state.market_data``:
    - RSI (14-period)
    - EMAs (9, 21, 50-period)
    - MACD (12, 26, 9)
    - VWAP
    - Support / resistance levels
    - Chart pattern detection (double top/bottom, head & shoulders, flags, etc.)

    Returns a dict keyed by ``technical_analysis`` for state merging.
    """
    if state.market_data is None or not state.market_data.ohlc_history:
        logger.warning("No market data available for technical analysis")
        return {"technical_analysis": TechnicalAnalysis()}

    bars = state.market_data.ohlc_history
    closes = [bar["close"] for bar in bars if bar.get("close") is not None]
    highs = [bar["high"] for bar in bars if bar.get("high") is not None]
    lows = [bar["low"] for bar in bars if bar.get("low") is not None]
    volumes = [bar["volume"] for bar in bars if bar.get("volume") is not None]

    if len(closes) < 26:
        logger.warning("Insufficient bars (%d) for full technical analysis", len(closes))
        return {"technical_analysis": TechnicalAnalysis()}

    logger.info("Running technical analysis on %d bars for %s", len(closes), state.ticker)

    # -- Indicators --------------------------------------------------------
    rsi_14 = compute_rsi(closes, period=14)
    ema_9 = compute_ema(closes, period=9)
    ema_21 = compute_ema(closes, period=21)
    ema_50 = compute_ema(closes, period=50)
    macd_line, signal_line, histogram = compute_macd(
        closes, fast=12, slow=26, signal=9
    )
    vwap = compute_vwap(highs, lows, closes, volumes)

    indicators = {
        "rsi_14": rsi_14,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "ema_50": ema_50,
        "macd": {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": histogram,
        },
        "vwap": vwap,
        "current_price": closes[-1] if closes else 0.0,
    }

    # -- Support / resistance ----------------------------------------------
    support_levels = find_support_resistance(lows, mode="support")
    resistance_levels = find_support_resistance(highs, mode="resistance")

    # -- Chart patterns ----------------------------------------------------
    detected_patterns = detect_chart_patterns(bars)

    # -- Build summary -----------------------------------------------------
    current_rsi = rsi_14[-1] if rsi_14 else 0.0
    trend = "neutral"
    if ema_9 and ema_21:
        if ema_9[-1] > ema_21[-1]:
            trend = "bullish"
        elif ema_9[-1] < ema_21[-1]:
            trend = "bearish"

    macd_signal = "neutral"
    if histogram:
        if histogram[-1] > 0:
            macd_signal = "bullish"
        elif histogram[-1] < 0:
            macd_signal = "bearish"

    summary_parts = [
        f"Trend: {trend} (EMA 9/21 crossover)",
        f"RSI(14): {current_rsi:.1f}",
        f"MACD: {macd_signal}",
    ]
    if detected_patterns:
        summary_parts.append(f"Patterns: {', '.join(detected_patterns)}")
    if support_levels:
        summary_parts.append(f"Support: {', '.join(f'${s:.2f}' for s in support_levels[:3])}")
    if resistance_levels:
        summary_parts.append(
            f"Resistance: {', '.join(f'${r:.2f}' for r in resistance_levels[:3])}"
        )

    technical_analysis = TechnicalAnalysis(
        patterns=detected_patterns,
        indicators=indicators,
        support_levels=support_levels,
        resistance_levels=resistance_levels,
        summary=" | ".join(summary_parts),
    )

    logger.info("Technical analysis complete: %s", technical_analysis.summary)

    return {"technical_analysis": technical_analysis}
