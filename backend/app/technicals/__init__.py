"""Technical analysis package -- indicators, patterns, and S/R levels."""

from app.technicals.indicators import (
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_vwap,
)
from app.technicals.patterns import detect_chart_patterns
from app.technicals.support_resistance import find_support_resistance

# Aliases matching names used in some node imports
compute_ema = calculate_ema
compute_macd = calculate_macd
compute_rsi = calculate_rsi
compute_vwap = calculate_vwap

__all__ = [
    "calculate_ema",
    "calculate_macd",
    "calculate_rsi",
    "calculate_vwap",
    "compute_ema",
    "compute_macd",
    "compute_rsi",
    "compute_vwap",
    "detect_chart_patterns",
    "find_support_resistance",
]
