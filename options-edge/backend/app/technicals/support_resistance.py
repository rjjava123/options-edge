"""Support and resistance level detection from price action."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _cluster_levels(
    levels: list[float], tolerance_pct: float = 0.015
) -> list[float]:
    """Merge price levels that are within *tolerance_pct* of each other.

    Returns one representative level (mean) per cluster, sorted ascending.
    """
    if not levels:
        return []

    sorted_levels = sorted(levels)
    clusters: list[list[float]] = [[sorted_levels[0]]]

    for lvl in sorted_levels[1:]:
        if abs(lvl - clusters[-1][-1]) / clusters[-1][-1] <= tolerance_pct:
            clusters[-1].append(lvl)
        else:
            clusters.append([lvl])

    return sorted(round(float(np.mean(c)), 2) for c in clusters)


def find_support_resistance(
    df: pd.DataFrame,
    window: int = 20,
) -> dict[str, Any]:
    """Identify key support and resistance levels from OHLCV price data.

    Parameters
    ----------
    df
        DataFrame with OHLCV columns (case-insensitive).
    window
        Rolling-window size used to detect local extrema.

    Returns
    -------
    dict
        ``{"support_levels": [...], "resistance_levels": [...]}`` where each
        list contains price levels sorted ascending.  Nearby levels are
        clustered so the output contains distinct zones rather than noise.
    """
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    df = df.reset_index(drop=True)

    highs = df["high"]
    lows = df["low"]
    close = df["close"]
    current_price = float(close.iloc[-1])

    # --- Pivot-based detection: local maxima / minima ---
    resistance_candidates: list[float] = []
    support_candidates: list[float] = []

    half = window // 2
    for i in range(half, len(df) - half):
        high_window = highs.iloc[i - half : i + half + 1]
        low_window = lows.iloc[i - half : i + half + 1]

        if highs.iloc[i] == high_window.max():
            resistance_candidates.append(float(highs.iloc[i]))
        if lows.iloc[i] == low_window.min():
            support_candidates.append(float(lows.iloc[i]))

    # --- Volume-weighted price levels (high-volume pivots matter more) ---
    if "volume" in df.columns:
        vol_mean = df["volume"].mean()
        high_vol_mask = df["volume"] > vol_mean * 1.5
        for idx in df.index[high_vol_mask]:
            price = float(close.iloc[idx])
            if price > current_price:
                resistance_candidates.append(price)
            else:
                support_candidates.append(price)

    # --- Round-number levels near the current price ---
    magnitude = 10 ** max(0, int(np.log10(current_price)) - 1)
    for mult in range(-5, 6):
        round_level = round(current_price / magnitude) * magnitude + mult * magnitude
        if round_level > 0:
            if round_level > current_price:
                resistance_candidates.append(round_level)
            elif round_level < current_price:
                support_candidates.append(round_level)

    # --- Cluster and separate by current price ---
    support_levels = _cluster_levels(
        [s for s in support_candidates if s < current_price]
    )
    resistance_levels = _cluster_levels(
        [r for r in resistance_candidates if r > current_price]
    )

    # Keep only the closest N levels
    max_levels = 5
    support_levels = support_levels[-max_levels:]  # highest supports
    resistance_levels = resistance_levels[:max_levels]  # lowest resistances

    return {
        "support_levels": support_levels,
        "resistance_levels": resistance_levels,
        "current_price": current_price,
    }
