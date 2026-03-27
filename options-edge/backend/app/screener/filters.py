"""Sequential funnel filters for the options screener.

Each filter takes a list of candidate dicts and a
:class:`~app.models.screener.ScreenerFilters` config, returning only those
candidates that pass.  The intended execution order is:

    liquidity -> IV rank -> unusual activity -> technical momentum
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Sequence

from app.data.polygon_client import PolygonClient
from app.models.screener import ScreenerCandidate, ScreenerFilters

logger = logging.getLogger(__name__)


async def _fetch_snapshot(
    client: PolygonClient, ticker: str
) -> dict[str, Any] | None:
    """Best-effort fetch of a ticker's options snapshot for filtering."""
    try:
        chain = await client.get_options_chain(ticker, min_dte=14, max_dte=60)
        if not chain:
            return None
        # Aggregate volume and OI across the chain
        total_volume = sum(c.get("day", {}).get("volume", 0) for c in chain)
        total_oi = sum(c.get("open_interest", 0) for c in chain)
        avg_spread = 0.0
        spread_count = 0
        for c in chain:
            bid = c.get("last_quote", {}).get("bid", 0)
            ask = c.get("last_quote", {}).get("ask", 0)
            if bid > 0 and ask > 0:
                avg_spread += (ask - bid) / ((ask + bid) / 2)
                spread_count += 1
        if spread_count:
            avg_spread /= spread_count

        return {
            "ticker": ticker,
            "options_volume": total_volume,
            "open_interest": total_oi,
            "avg_bid_ask_spread": round(avg_spread, 4),
            "contract_count": len(chain),
        }
    except Exception:
        logger.debug("Snapshot fetch failed for %s", ticker, exc_info=True)
        return None


# ------------------------------------------------------------------
# Filter functions
# ------------------------------------------------------------------


async def liquidity_filter(
    candidates: Sequence[str],
    config: ScreenerFilters,
    client: PolygonClient,
    *,
    batch_size: int = 20,
) -> list[ScreenerCandidate]:
    """Filter tickers by options volume and bid-ask spread.

    This is the first (widest) filter in the funnel and also enriches
    candidates with basic volume data for downstream filters.
    """
    min_volume = config.min_options_volume or 100
    max_spread = config.max_bid_ask_spread or 0.10

    passed: list[ScreenerCandidate] = []

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        tasks = [_fetch_snapshot(client, t) for t in batch]
        results = await asyncio.gather(*tasks)

        for snap in results:
            if snap is None:
                continue
            if snap["options_volume"] < min_volume:
                continue
            if snap["avg_bid_ask_spread"] > max_spread:
                continue
            passed.append(
                ScreenerCandidate(
                    ticker=snap["ticker"],
                    options_volume=snap["options_volume"],
                    passed_filters=["liquidity"],
                )
            )

    logger.info("Liquidity filter: %d/%d passed", len(passed), len(candidates))
    return passed


async def iv_rank_filter(
    candidates: list[ScreenerCandidate],
    config: ScreenerFilters,
    client: PolygonClient,
) -> list[ScreenerCandidate]:
    """Filter candidates by IV rank (requires historical IV data).

    Uses Polygon OHLC history to approximate historical IV from close-to-close
    realised vol as a proxy when per-contract IV history is unavailable.
    """
    from app.data.options_math import calculate_iv_rank

    min_rank = config.min_iv_rank or 30.0
    max_rank = config.max_iv_rank or 80.0

    passed: list[ScreenerCandidate] = []

    async def _check(cand: ScreenerCandidate) -> ScreenerCandidate | None:
        try:
            bars = await client.get_ohlc_history(cand.ticker, days=365)
            if len(bars) < 30:
                return None
            closes = [b["c"] for b in bars if "c" in b]
            # Use 20-day realised vol as IV proxy
            import numpy as np

            returns = np.diff(np.log(closes))
            window = 20
            if len(returns) < window:
                return None
            current_rv = float(np.std(returns[-window:]) * np.sqrt(252))
            historical_rvs = [
                float(np.std(returns[j : j + window]) * np.sqrt(252))
                for j in range(0, len(returns) - window, 5)
            ]
            rank = calculate_iv_rank(current_rv, historical_rvs)
            if min_rank <= rank <= max_rank:
                cand.iv_rank = rank
                cand.passed_filters.append("iv_rank")
                return cand
        except Exception:
            logger.debug("IV rank check failed for %s", cand.ticker, exc_info=True)
        return None

    tasks = [_check(c) for c in candidates]
    results = await asyncio.gather(*tasks)
    passed = [r for r in results if r is not None]
    logger.info("IV rank filter: %d/%d passed", len(passed), len(candidates))
    return passed


async def unusual_activity_filter(
    candidates: list[ScreenerCandidate],
    config: ScreenerFilters,
    client: PolygonClient,
) -> list[ScreenerCandidate]:
    """Flag candidates exhibiting unusual options activity.

    Scores based on volume/OI ratio and checks against the minimum
    threshold from config.
    """
    min_score = config.min_unusual_activity_score or 0.0

    passed: list[ScreenerCandidate] = []
    for cand in candidates:
        try:
            chain = await client.get_options_chain(cand.ticker, min_dte=7, max_dte=45)
            if not chain:
                if min_score <= 0:
                    passed.append(cand)
                continue

            total_vol = sum(c.get("day", {}).get("volume", 0) for c in chain)
            total_oi = sum(c.get("open_interest", 0) for c in chain)
            vol_oi_ratio = total_vol / max(total_oi, 1)

            # Simple score: ratio above 0.5 is noteworthy
            score = round(min(vol_oi_ratio / 2.0, 1.0), 2)

            if score >= min_score:
                cand.unusual_activity_score = score
                cand.passed_filters.append("unusual_activity")
                passed.append(cand)
        except Exception:
            logger.debug("Unusual activity check failed for %s", cand.ticker, exc_info=True)
            if min_score <= 0:
                passed.append(cand)

    logger.info("Unusual activity filter: %d/%d passed", len(passed), len(candidates))
    return passed


async def technical_momentum_filter(
    candidates: list[ScreenerCandidate],
    config: ScreenerFilters,
    client: PolygonClient,
) -> list[ScreenerCandidate]:
    """Filter by technical momentum (RSI, EMA alignment).

    Keeps candidates whose RSI is within a reasonable range (not overbought
    or oversold beyond thresholds) and whose short EMA is aligned with trend.
    """
    import pandas as pd

    from app.technicals.indicators import calculate_ema, calculate_rsi

    min_rs = config.min_relative_strength or 0.0
    max_rs = config.max_relative_strength or 100.0

    passed: list[ScreenerCandidate] = []

    for cand in candidates:
        try:
            bars = await client.get_ohlc_history(cand.ticker, days=90)
            if len(bars) < 50:
                continue

            df = pd.DataFrame(bars)
            df = df.rename(
                columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
            )
            df = calculate_rsi(df, period=14)
            df = calculate_ema(df, periods=[9, 21, 50])

            latest = df.iloc[-1]
            rsi = latest.get("rsi_14")
            if rsi is None or pd.isna(rsi):
                continue

            # Technical score: 0-100 based on RSI + EMA alignment
            ema_9 = latest.get("ema_9", 0)
            ema_21 = latest.get("ema_21", 0)
            ema_50 = latest.get("ema_50", 0)

            alignment_score = 0.0
            if ema_9 > ema_21 > ema_50:
                alignment_score = 1.0  # fully bullish
            elif ema_9 < ema_21 < ema_50:
                alignment_score = 1.0  # fully bearish (still tradeable)
            elif ema_9 > ema_21:
                alignment_score = 0.5

            tech_score = round((alignment_score * 50) + (rsi / 2), 2)

            if min_rs <= tech_score <= max_rs:
                cand.technical_score = tech_score
                cand.passed_filters.append("technical_momentum")
                passed.append(cand)
        except Exception:
            logger.debug("Technical filter failed for %s", cand.ticker, exc_info=True)

    logger.info("Technical momentum filter: %d/%d passed", len(passed), len(candidates))
    return passed
