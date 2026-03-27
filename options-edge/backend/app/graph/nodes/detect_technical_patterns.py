"""Run technical analysis on price history to detect patterns and key levels."""

from __future__ import annotations

import logging

import pandas as pd
import pandas_ta as ta

from app.models.state import (
    AnalysisState,
    DetectedPattern,
    TechnicalAnalysis,
    TechnicalIndicators,
)
from app.technicals.patterns import detect_chart_patterns
from app.technicals.support_resistance import find_support_resistance

logger = logging.getLogger(__name__)

# Bollinger Band Width threshold – values below this indicate a squeeze
_BBW_SQUEEZE_THRESHOLD = 0.04


def _bars_to_dataframe(bars: list) -> pd.DataFrame:
    """Convert a list of OHLCBar models into a pandas DataFrame."""
    records = [
        {
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "timestamp": bar.timestamp,
            "vwap": bar.vwap,
        }
        for bar in bars
    ]
    df = pd.DataFrame(records)
    if "timestamp" in df.columns and df["timestamp"].notna().any():
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df.sort_values("timestamp", inplace=True)
        df.reset_index(drop=True, inplace=True)
    return df


async def detect_technical_patterns(state: AnalysisState) -> dict:
    """Compute technical indicators and detect chart patterns.

    Runs the following analyses on OHLC history from ``state.market_data``:
    - RSI (14-period)
    - EMAs (9, 21, 50-period)
    - MACD (12, 26, 9)
    - VWAP
    - Bollinger Bands (20, 2) with squeeze detection
    - Support / resistance levels
    - Chart pattern detection (double top/bottom, head & shoulders, flags, etc.)
    - Consolidation detection

    Returns a dict keyed by ``technical_analysis`` for state merging.
    """
    if state.market_data is None or not state.market_data.ohlc_history:
        logger.warning("No market data available for technical analysis")
        return {"technical_analysis": TechnicalAnalysis()}

    bars = state.market_data.ohlc_history
    df = _bars_to_dataframe(bars)

    if len(df) < 26:
        logger.warning(
            "Insufficient bars (%d) for full technical analysis", len(df)
        )
        return {"technical_analysis": TechnicalAnalysis()}

    logger.info(
        "Running technical analysis on %d bars for %s", len(df), state.ticker
    )

    # ------------------------------------------------------------------
    # Compute indicators via pandas-ta
    # ------------------------------------------------------------------
    rsi_series = ta.rsi(df["close"], length=14)
    ema_9_series = ta.ema(df["close"], length=9)
    ema_21_series = ta.ema(df["close"], length=21)
    ema_50_series = ta.ema(df["close"], length=50)

    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
    # pandas-ta returns columns: MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
    macd_line_series = macd_df.iloc[:, 0] if macd_df is not None else None
    macd_hist_series = macd_df.iloc[:, 1] if macd_df is not None else None
    macd_signal_series = macd_df.iloc[:, 2] if macd_df is not None else None

    # VWAP – pandas-ta needs a DatetimeIndex with high/low/close/volume
    vwap_val = 0.0
    if "timestamp" in df.columns and df["timestamp"].notna().all():
        try:
            vwap_df = df.set_index("timestamp")
            vwap_series = ta.vwap(
                vwap_df["high"], vwap_df["low"], vwap_df["close"], vwap_df["volume"]
            )
            if vwap_series is not None and not vwap_series.empty:
                vwap_val = float(vwap_series.iloc[-1])
        except Exception:
            logger.debug("VWAP calculation failed; falling back to 0.0")

    # Bollinger Bands (20, 2)
    bb_df = ta.bbands(df["close"], length=20, std=2)
    bb_lower = bb_df.iloc[:, 0] if bb_df is not None else None
    bb_mid = bb_df.iloc[:, 1] if bb_df is not None else None
    bb_upper = bb_df.iloc[:, 2] if bb_df is not None else None
    bb_bandwidth = bb_df.iloc[:, 3] if bb_df is not None and bb_df.shape[1] > 3 else None

    # ------------------------------------------------------------------
    # Extract latest scalar values
    # ------------------------------------------------------------------
    def _last(series: pd.Series | None) -> float:
        if series is None or series.empty:
            return 0.0
        val = series.iloc[-1]
        return float(val) if pd.notna(val) else 0.0

    current_price = float(df["close"].iloc[-1])
    rsi_14 = _last(rsi_series)
    ema_9 = _last(ema_9_series)
    ema_21 = _last(ema_21_series)
    ema_50 = _last(ema_50_series)
    macd_line = _last(macd_line_series)
    signal_line = _last(macd_signal_series)
    macd_histogram = _last(macd_hist_series)

    # Trend from EMA crossover
    trend = "neutral"
    if ema_9 and ema_21:
        if ema_9 > ema_21:
            trend = "bullish"
        elif ema_9 < ema_21:
            trend = "bearish"

    # MACD signal
    macd_signal_label = "neutral"
    if macd_histogram > 0:
        macd_signal_label = "bullish"
    elif macd_histogram < 0:
        macd_signal_label = "bearish"

    indicators = TechnicalIndicators(
        rsi_14=rsi_14,
        ema_9=ema_9,
        ema_21=ema_21,
        ema_50=ema_50,
        macd_line=macd_line,
        signal_line=signal_line,
        macd_histogram=macd_histogram,
        vwap=vwap_val,
        current_price=current_price,
        trend=trend,
        macd_signal=macd_signal_label,
    )

    # ------------------------------------------------------------------
    # Support / resistance (pass the DataFrame)
    # ------------------------------------------------------------------
    sr_result = find_support_resistance(df)
    support_levels: list[float] = sr_result.get("support_levels", [])
    resistance_levels: list[float] = sr_result.get("resistance_levels", [])

    # ------------------------------------------------------------------
    # Chart patterns (pass the DataFrame)
    # ------------------------------------------------------------------
    raw_patterns = detect_chart_patterns(df)

    detected_patterns: list[DetectedPattern] = [
        DetectedPattern(
            name=p.get("name", p.get("pattern", "")),
            type=p.get("type", p.get("direction", "")),
            confidence=float(p.get("confidence", 0.0)),
            price_level=float(p.get("price_level", p.get("price", 0.0))),
        )
        for p in raw_patterns
    ]

    # ------------------------------------------------------------------
    # Bollinger Band squeeze detection
    # ------------------------------------------------------------------
    if bb_bandwidth is not None and not bb_bandwidth.empty:
        latest_bbw = float(bb_bandwidth.iloc[-1]) if pd.notna(bb_bandwidth.iloc[-1]) else None
        if latest_bbw is not None and latest_bbw < _BBW_SQUEEZE_THRESHOLD:
            detected_patterns.append(
                DetectedPattern(
                    name="Bollinger Squeeze",
                    type="neutral",
                    confidence=round(
                        min(1.0, (_BBW_SQUEEZE_THRESHOLD - latest_bbw) / _BBW_SQUEEZE_THRESHOLD),
                        2,
                    ),
                    price_level=current_price,
                )
            )

    # ------------------------------------------------------------------
    # Consolidation detection (low range / ATR contraction)
    # ------------------------------------------------------------------
    if len(df) >= 20:
        recent = df.tail(10)
        range_pct = (recent["high"].max() - recent["low"].min()) / current_price
        if range_pct < 0.03:
            detected_patterns.append(
                DetectedPattern(
                    name="Consolidation",
                    type="neutral",
                    confidence=round(min(1.0, (0.03 - range_pct) / 0.03), 2),
                    price_level=current_price,
                )
            )

    # ------------------------------------------------------------------
    # Build summary
    # ------------------------------------------------------------------
    summary_parts = [
        f"Trend: {trend} (EMA 9/21 crossover)",
        f"RSI(14): {rsi_14:.1f}",
        f"MACD: {macd_signal_label}",
    ]
    if detected_patterns:
        pattern_names = [p.name for p in detected_patterns]
        summary_parts.append(f"Patterns: {', '.join(pattern_names)}")
    if support_levels:
        summary_parts.append(
            f"Support: {', '.join(f'${s:.2f}' for s in support_levels[:3])}"
        )
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
