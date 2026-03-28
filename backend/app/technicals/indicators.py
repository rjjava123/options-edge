"""Technical indicator calculations using pandas and pandas-ta.

All functions expect a pandas DataFrame with standard OHLCV columns:
``open``, ``high``, ``low``, ``close``, ``volume`` (case-insensitive).
They return the input DataFrame with new indicator columns appended.
"""

from __future__ import annotations

import pandas as pd
import pandas_ta as ta


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure OHLCV columns are lowercase so pandas-ta can find them."""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    return df


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Append an ``rsi_{period}`` column using Wilder's RSI."""
    df = _normalise_columns(df)
    col = f"rsi_{period}"
    df[col] = ta.rsi(df["close"], length=period)
    return df


def calculate_ema(
    df: pd.DataFrame,
    periods: list[int] | None = None,
) -> pd.DataFrame:
    """Append EMA columns for each period in *periods* (default [9, 21, 50])."""
    if periods is None:
        periods = [9, 21, 50]
    df = _normalise_columns(df)
    for p in periods:
        df[f"ema_{p}"] = ta.ema(df["close"], length=p)
    return df


def calculate_macd(df: pd.DataFrame) -> pd.DataFrame:
    """Append MACD, signal, and histogram columns (12/26/9)."""
    df = _normalise_columns(df)
    macd_df = ta.macd(df["close"], fast=12, slow=26, signal=9)
    if macd_df is not None:
        df = pd.concat([df, macd_df], axis=1)
    return df


def calculate_vwap(df: pd.DataFrame) -> pd.DataFrame:
    """Append a ``vwap`` column.

    Requires ``high``, ``low``, ``close``, and ``volume`` columns.
    """
    df = _normalise_columns(df)
    vwap_series = ta.vwap(df["high"], df["low"], df["close"], df["volume"])
    if vwap_series is not None:
        df["vwap"] = vwap_series
    return df
