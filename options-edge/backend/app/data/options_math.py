"""Pure-math helpers for options spread valuation and risk metrics.

All functions are synchronous and stateless -- they operate on simple numeric
inputs so they can be used anywhere in the codebase without async overhead.
"""

from __future__ import annotations

import math
from typing import Sequence


# ------------------------------------------------------------------
# Spread value
# ------------------------------------------------------------------

def calculate_spread_value(legs: list[dict]) -> float:
    """Compute the net mark-to-market value of a multi-leg spread.

    Each *leg* dict must contain:
      - ``quantity``: int (positive for long, negative for short)
      - ``mid_price``: float (current midpoint of bid/ask)
      - ``multiplier``: int (usually 100 for equity options)

    Returns the net value in dollars.
    """
    total = 0.0
    for leg in legs:
        qty = leg["quantity"]
        mid = leg["mid_price"]
        mult = leg.get("multiplier", 100)
        total += qty * mid * mult
    return round(total, 2)


# ------------------------------------------------------------------
# Implied-volatility context
# ------------------------------------------------------------------

def calculate_iv_rank(current_iv: float, iv_history: Sequence[float]) -> float:
    """IV Rank: where current IV sits relative to the 52-week high/low.

    Formula: (current - min) / (max - min) * 100
    Returns a value between 0 and 100, or 0.0 when history is empty.
    """
    if not iv_history:
        return 0.0
    iv_min = min(iv_history)
    iv_max = max(iv_history)
    if iv_max == iv_min:
        return 50.0  # no range -- return midpoint
    return round((current_iv - iv_min) / (iv_max - iv_min) * 100, 2)


def calculate_iv_percentile(
    current_iv: float, iv_history: Sequence[float]
) -> float:
    """IV Percentile: % of days in *iv_history* where IV was below *current_iv*.

    Returns a value between 0 and 100, or 0.0 when history is empty.
    """
    if not iv_history:
        return 0.0
    count_below = sum(1 for iv in iv_history if iv < current_iv)
    return round(count_below / len(iv_history) * 100, 2)


# ------------------------------------------------------------------
# Expected move
# ------------------------------------------------------------------

def calculate_expected_move(price: float, iv: float, dte: int) -> float:
    """One standard-deviation expected move over *dte* calendar days.

    Uses the annualised IV and scales it to the given time horizon:
      expected_move = price * iv * sqrt(dte / 365)
    """
    if dte <= 0 or iv <= 0:
        return 0.0
    return round(price * iv * math.sqrt(dte / 365.0), 2)


# ------------------------------------------------------------------
# P&L boundaries
# ------------------------------------------------------------------

def calculate_max_profit(
    spread_type: str,
    entry_price: float,
    strikes: tuple[float, float],
) -> float:
    """Maximum theoretical profit for a vertical spread.

    Parameters
    ----------
    spread_type
        One of ``"bull_put_credit"``, ``"bear_call_credit"``,
        ``"bull_call_debit"``, ``"bear_put_debit"``.
    entry_price
        Net credit received (positive) or net debit paid (positive value).
    strikes
        (short_strike, long_strike) for credit spreads or
        (long_strike, short_strike) for debit spreads.
    """
    width = abs(strikes[0] - strikes[1])

    if spread_type in ("bull_put_credit", "bear_call_credit"):
        # Credit spread: max profit = premium received
        return round(entry_price * 100, 2)
    elif spread_type in ("bull_call_debit", "bear_put_debit"):
        # Debit spread: max profit = width - premium paid
        return round((width - entry_price) * 100, 2)
    else:
        return 0.0


def calculate_max_loss(
    spread_type: str,
    entry_price: float,
    strikes: tuple[float, float],
) -> float:
    """Maximum theoretical loss for a vertical spread.

    Same parameter semantics as :func:`calculate_max_profit`.
    """
    width = abs(strikes[0] - strikes[1])

    if spread_type in ("bull_put_credit", "bear_call_credit"):
        # Credit spread: max loss = width - premium received
        return round((width - entry_price) * 100, 2)
    elif spread_type in ("bull_call_debit", "bear_put_debit"):
        # Debit spread: max loss = premium paid
        return round(entry_price * 100, 2)
    else:
        return 0.0


# ------------------------------------------------------------------
# Live P&L
# ------------------------------------------------------------------

def calculate_pnl(
    entry_price: float,
    current_price: float,
    spread_type: str,
) -> float:
    """Unrealised P&L in dollars (per-contract, 100 multiplier).

    For credit spreads the entry_price is the credit received and a
    *decrease* in current_price is profitable.  For debit spreads the
    entry_price is the debit paid and an *increase* is profitable.
    """
    if spread_type in ("bull_put_credit", "bear_call_credit"):
        return round((entry_price - current_price) * 100, 2)
    elif spread_type in ("bull_call_debit", "bear_put_debit"):
        return round((current_price - entry_price) * 100, 2)
    else:
        return 0.0
