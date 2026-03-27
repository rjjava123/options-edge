"""Chart pattern detection on OHLCV DataFrames.

Returns structured dicts describing each detected pattern so downstream
consumers can filter by type, direction, and confidence.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _find_local_extrema(
    series: pd.Series, window: int = 5
) -> tuple[pd.Series, pd.Series]:
    """Return boolean masks for local maxima and minima."""
    maxima = (
        (series == series.rolling(window * 2 + 1, center=True).max())
        & (series.shift(1) < series)
        & (series.shift(-1) < series)
    )
    minima = (
        (series == series.rolling(window * 2 + 1, center=True).min())
        & (series.shift(1) > series)
        & (series.shift(-1) > series)
    )
    return maxima, minima


def _detect_double_top(
    highs: pd.Series, window: int = 5, tolerance: float = 0.02
) -> list[dict[str, Any]]:
    """Detect double-top patterns (bearish reversal)."""
    patterns: list[dict[str, Any]] = []
    maxima_mask, _ = _find_local_extrema(highs, window)
    peaks = highs[maxima_mask].dropna()

    for i in range(len(peaks) - 1):
        p1, p2 = peaks.iloc[i], peaks.iloc[i + 1]
        if abs(p1 - p2) / p1 <= tolerance:
            idx1 = peaks.index[i]
            idx2 = peaks.index[i + 1]
            separation = idx2 - idx1
            if 5 <= separation <= 60:
                confidence = max(0.4, 1.0 - abs(p1 - p2) / p1 * 10)
                patterns.append(
                    {
                        "name": "double_top",
                        "type": "bearish",
                        "confidence": round(min(confidence, 0.95), 2),
                        "start_idx": int(idx1),
                        "end_idx": int(idx2),
                        "price_level": round(float((p1 + p2) / 2), 2),
                    }
                )
    return patterns


def _detect_double_bottom(
    lows: pd.Series, window: int = 5, tolerance: float = 0.02
) -> list[dict[str, Any]]:
    """Detect double-bottom patterns (bullish reversal)."""
    patterns: list[dict[str, Any]] = []
    _, minima_mask = _find_local_extrema(lows, window)
    troughs = lows[minima_mask].dropna()

    for i in range(len(troughs) - 1):
        t1, t2 = troughs.iloc[i], troughs.iloc[i + 1]
        if abs(t1 - t2) / t1 <= tolerance:
            idx1 = troughs.index[i]
            idx2 = troughs.index[i + 1]
            separation = idx2 - idx1
            if 5 <= separation <= 60:
                confidence = max(0.4, 1.0 - abs(t1 - t2) / t1 * 10)
                patterns.append(
                    {
                        "name": "double_bottom",
                        "type": "bullish",
                        "confidence": round(min(confidence, 0.95), 2),
                        "start_idx": int(idx1),
                        "end_idx": int(idx2),
                        "price_level": round(float((t1 + t2) / 2), 2),
                    }
                )
    return patterns


def _detect_head_and_shoulders(
    highs: pd.Series, lows: pd.Series, window: int = 5
) -> list[dict[str, Any]]:
    """Detect head-and-shoulders (bearish) and inverse H&S (bullish)."""
    patterns: list[dict[str, Any]] = []
    maxima_mask, minima_mask = _find_local_extrema(highs, window)
    peaks = highs[maxima_mask].dropna()

    # Standard H&S: three peaks where middle is highest
    for i in range(len(peaks) - 2):
        left, head, right = peaks.iloc[i], peaks.iloc[i + 1], peaks.iloc[i + 2]
        if head > left and head > right:
            # Shoulders should be roughly equal
            shoulder_diff = abs(left - right) / left
            if shoulder_diff <= 0.05:
                confidence = max(0.5, 1.0 - shoulder_diff * 5)
                patterns.append(
                    {
                        "name": "head_and_shoulders",
                        "type": "bearish",
                        "confidence": round(min(confidence, 0.90), 2),
                        "start_idx": int(peaks.index[i]),
                        "end_idx": int(peaks.index[i + 2]),
                        "price_level": round(float(head), 2),
                    }
                )

    # Inverse H&S
    _, minima_mask_low = _find_local_extrema(lows, window)
    troughs = lows[minima_mask_low].dropna()

    for i in range(len(troughs) - 2):
        left, head, right = troughs.iloc[i], troughs.iloc[i + 1], troughs.iloc[i + 2]
        if head < left and head < right:
            shoulder_diff = abs(left - right) / left
            if shoulder_diff <= 0.05:
                confidence = max(0.5, 1.0 - shoulder_diff * 5)
                patterns.append(
                    {
                        "name": "inverse_head_and_shoulders",
                        "type": "bullish",
                        "confidence": round(min(confidence, 0.90), 2),
                        "start_idx": int(troughs.index[i]),
                        "end_idx": int(troughs.index[i + 2]),
                        "price_level": round(float(head), 2),
                    }
                )

    return patterns


def _detect_triangle(
    highs: pd.Series, lows: pd.Series, window: int = 5, min_points: int = 4
) -> list[dict[str, Any]]:
    """Detect symmetrical, ascending, and descending triangle patterns."""
    patterns: list[dict[str, Any]] = []
    maxima_mask, _ = _find_local_extrema(highs, window)
    _, minima_mask = _find_local_extrema(lows, window)

    peaks = highs[maxima_mask].dropna()
    troughs = lows[minima_mask].dropna()

    if len(peaks) < 2 or len(troughs) < 2:
        return patterns

    # Fit linear regression to recent peaks and troughs
    recent_peaks = peaks.tail(min_points)
    recent_troughs = troughs.tail(min_points)

    if len(recent_peaks) >= 2 and len(recent_troughs) >= 2:
        peak_x = np.arange(len(recent_peaks))
        trough_x = np.arange(len(recent_troughs))

        peak_slope = np.polyfit(peak_x, recent_peaks.values, 1)[0]
        trough_slope = np.polyfit(trough_x, recent_troughs.values, 1)[0]

        # Converging highs and lows -> triangle
        if peak_slope < 0 and trough_slope > 0:
            patterns.append(
                {
                    "name": "symmetrical_triangle",
                    "type": "neutral",
                    "confidence": 0.60,
                    "start_idx": int(min(recent_peaks.index[0], recent_troughs.index[0])),
                    "end_idx": int(max(recent_peaks.index[-1], recent_troughs.index[-1])),
                    "price_level": round(float(recent_peaks.iloc[-1] + recent_troughs.iloc[-1]) / 2, 2),
                }
            )
        elif abs(peak_slope) < 0.01 * highs.mean() and trough_slope > 0:
            patterns.append(
                {
                    "name": "ascending_triangle",
                    "type": "bullish",
                    "confidence": 0.65,
                    "start_idx": int(min(recent_peaks.index[0], recent_troughs.index[0])),
                    "end_idx": int(max(recent_peaks.index[-1], recent_troughs.index[-1])),
                    "price_level": round(float(recent_peaks.mean()), 2),
                }
            )
        elif peak_slope < 0 and abs(trough_slope) < 0.01 * lows.mean():
            patterns.append(
                {
                    "name": "descending_triangle",
                    "type": "bearish",
                    "confidence": 0.65,
                    "start_idx": int(min(recent_peaks.index[0], recent_troughs.index[0])),
                    "end_idx": int(max(recent_peaks.index[-1], recent_troughs.index[-1])),
                    "price_level": round(float(recent_troughs.mean()), 2),
                }
            )

    return patterns


def _detect_flag(
    df: pd.DataFrame, window: int = 5
) -> list[dict[str, Any]]:
    """Detect bull/bear flag consolidation patterns."""
    patterns: list[dict[str, Any]] = []
    close = df["close"] if "close" in df.columns else df["Close"]

    if len(close) < 20:
        return patterns

    # Look for a strong move followed by tight consolidation
    lookback = 20
    for i in range(lookback, len(close) - 5):
        # Impulse: the move from i-lookback to i-5
        impulse = close.iloc[i - 5] - close.iloc[i - lookback]
        impulse_pct = abs(impulse) / close.iloc[i - lookback]

        if impulse_pct < 0.05:
            continue

        # Consolidation: the range from i-5 to i
        consolidation = close.iloc[i - 5 : i + 1]
        cons_range = consolidation.max() - consolidation.min()
        cons_range_pct = cons_range / close.iloc[i - 5]

        if cons_range_pct < 0.03:
            direction = "bullish" if impulse > 0 else "bearish"
            patterns.append(
                {
                    "name": f"{direction.lower()}_flag",
                    "type": direction,
                    "confidence": round(min(0.70, impulse_pct * 5), 2),
                    "start_idx": i - lookback,
                    "end_idx": i,
                    "price_level": round(float(close.iloc[i]), 2),
                }
            )

    # Deduplicate overlapping flags, keep highest confidence
    if patterns:
        patterns.sort(key=lambda p: p["confidence"], reverse=True)
        seen_ranges: list[tuple[int, int]] = []
        unique: list[dict[str, Any]] = []
        for p in patterns:
            overlaps = any(
                p["start_idx"] < er and p["end_idx"] > sr
                for sr, er in seen_ranges
            )
            if not overlaps:
                unique.append(p)
                seen_ranges.append((p["start_idx"], p["end_idx"]))
        patterns = unique

    return patterns


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def detect_chart_patterns(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Run all pattern detectors on *df* and return a merged list.

    Parameters
    ----------
    df
        DataFrame with OHLCV columns (``open``, ``high``, ``low``,
        ``close``, ``volume`` -- case-insensitive).

    Returns
    -------
    list[dict]
        Each dict contains ``name``, ``type`` (bullish/bearish/neutral),
        ``confidence`` (0-1), ``start_idx``, ``end_idx``, ``price_level``.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df.reset_index(drop=True)

    highs = df["high"]
    lows = df["low"]

    all_patterns: list[dict[str, Any]] = []
    all_patterns.extend(_detect_double_top(highs))
    all_patterns.extend(_detect_double_bottom(lows))
    all_patterns.extend(_detect_head_and_shoulders(highs, lows))
    all_patterns.extend(_detect_triangle(highs, lows))
    all_patterns.extend(_detect_flag(df))

    # Sort by confidence descending
    all_patterns.sort(key=lambda p: p["confidence"], reverse=True)
    return all_patterns
