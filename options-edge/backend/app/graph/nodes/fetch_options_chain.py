"""Fetch full options chain with greeks, IV, and open interest."""

from __future__ import annotations

import logging
import math
from typing import Optional

from app.data.options_math import calculate_iv_rank
from app.data.polygon_client import get_polygon_client
from app.models.state import (
    AnalysisState,
    OptionsChain,
    OptionsChainSummary,
    OptionContract,
)

logger = logging.getLogger(__name__)

# Target DTE window for short-dated spread trading
MIN_DTE = 1
MAX_DTE = 14

# Rolling window for realized-volatility calculation (trading days)
_RV_WINDOW = 20
# Calendar days of daily bars to fetch for historical RV
_HIST_DAYS = 365


async def fetch_options_chain(state: AnalysisState) -> dict:
    """Retrieve the full options chain for expirations between 1-14 DTE.

    Pulls all available contracts within the target expiration window,
    including greeks (delta, gamma, theta, vega), implied volatility,
    and open interest for each strike.  After building the chain, computes
    IV rank by comparing the chain's average IV against a 365-day history
    of 20-day rolling realized volatility.

    Returns a dict keyed by ``options_chain`` for state merging.
    """
    client = get_polygon_client()
    ticker = state.ticker.upper()

    logger.info("Fetching options chain for %s (DTE %d-%d)", ticker, MIN_DTE, MAX_DTE)

    # Polygon options chain snapshot returns contracts with greeks
    raw_contracts = await client.get_options_chain(
        ticker,
        min_dte=MIN_DTE,
        max_dte=MAX_DTE,
    )

    contracts: list[OptionContract] = []
    expirations_set: set[str] = set()

    call_iv_values: list[float] = []
    put_iv_values: list[float] = []

    total_call_oi = 0
    total_put_oi = 0
    total_call_volume = 0
    total_put_volume = 0

    for raw in raw_contracts:
        details = raw.get("details", {})
        greeks = raw.get("greeks", {})
        day = raw.get("day", {})

        contract_type = details.get("contract_type", "").lower()
        expiration = details.get("expiration_date", "")
        strike = details.get("strike_price", 0.0)
        iv = raw.get("implied_volatility", 0.0)
        oi = raw.get("open_interest", 0)
        volume = day.get("volume", 0)

        option = OptionContract(
            ticker=details.get("ticker", ""),
            contract_type=contract_type,
            expiration_date=expiration,
            strike_price=strike,
            implied_volatility=iv,
            open_interest=oi,
            volume=volume,
            last_price=day.get("close", 0.0),
            bid=raw.get("last_quote", {}).get("bid", 0.0),
            ask=raw.get("last_quote", {}).get("ask", 0.0),
            delta=greeks.get("delta", 0.0),
            gamma=greeks.get("gamma", 0.0),
            theta=greeks.get("theta", 0.0),
            vega=greeks.get("vega", 0.0),
        )

        contracts.append(option)
        expirations_set.add(expiration)

        # Accumulate for summary
        if contract_type == "call":
            if iv:
                call_iv_values.append(iv)
            total_call_oi += oi
            total_call_volume += volume
        elif contract_type == "put":
            if iv:
                put_iv_values.append(iv)
            total_put_oi += oi
            total_put_volume += volume

    avg_call_iv = (sum(call_iv_values) / len(call_iv_values)) if call_iv_values else 0.0
    avg_put_iv = (sum(put_iv_values) / len(put_iv_values)) if put_iv_values else 0.0

    total_oi = total_call_oi + total_put_oi
    put_call_oi_ratio = (
        total_put_oi / total_call_oi if total_call_oi > 0 else 0.0
    )

    summary = OptionsChainSummary(
        avg_call_iv=avg_call_iv,
        avg_put_iv=avg_put_iv,
        total_call_oi=total_call_oi,
        total_put_oi=total_put_oi,
        total_call_volume=total_call_volume,
        total_put_volume=total_put_volume,
        put_call_oi_ratio=put_call_oi_ratio,
        total_oi=total_oi,
    )

    # ------------------------------------------------------------------
    # IV Rank: compare current chain IV to historical realized volatility
    # ------------------------------------------------------------------
    current_iv = (avg_call_iv + avg_put_iv) / 2.0
    iv_rank: Optional[float] = None

    if current_iv > 0:
        try:
            daily_bars = await client.get_daily_bars(ticker, days=_HIST_DAYS)

            if len(daily_bars) > _RV_WINDOW:
                # Compute 20-day rolling realized volatility from close prices
                closes = [bar["c"] for bar in daily_bars if "c" in bar]
                historical_rvs: list[float] = []

                for i in range(_RV_WINDOW, len(closes)):
                    window = closes[i - _RV_WINDOW : i]
                    log_returns = [
                        math.log(window[j] / window[j - 1])
                        for j in range(1, len(window))
                        if window[j - 1] > 0
                    ]
                    if log_returns:
                        mean_ret = sum(log_returns) / len(log_returns)
                        variance = sum(
                            (r - mean_ret) ** 2 for r in log_returns
                        ) / len(log_returns)
                        # Annualize: stdev * sqrt(252)
                        rv = math.sqrt(variance) * math.sqrt(252)
                        historical_rvs.append(rv)

                if historical_rvs:
                    iv_rank = calculate_iv_rank(current_iv, historical_rvs)
                    logger.info(
                        "IV rank for %s: %.1f (current IV=%.4f, %d RV samples)",
                        ticker,
                        iv_rank,
                        current_iv,
                        len(historical_rvs),
                    )
        except Exception:
            logger.warning(
                "Failed to compute IV rank for %s; continuing without it",
                ticker,
                exc_info=True,
            )

    summary.iv_rank = iv_rank

    options_chain = OptionsChain(
        contracts=contracts,
        expirations=sorted(expirations_set),
        summary=summary,
    )

    logger.info(
        "Options chain fetched: %d contracts across %d expirations",
        len(contracts),
        len(expirations_set),
    )

    return {"options_chain": options_chain}
