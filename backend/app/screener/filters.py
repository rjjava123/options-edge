"""Sequential funnel filters for the options screener.

Each filter takes a list of candidate dicts and a
:class:`~app.models.screener.ScreenerFilters` config, returning only those
candidates that pass.  The intended execution order is:

    universe (grouped daily) -> liquidity -> IV rank -> unusual activity -> technical momentum

The first stage uses Polygon's ``get_grouped_daily()`` endpoint — a *single*
API call that returns one bar per ticker for the entire US market — to perform
the initial universe, price, and volume filtering.  This avoids making 3 000+
individual snapshot requests.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from app.data.polygon_client import PolygonClient, get_polygon_client
from app.models.screener import ScreenerCandidate, ScreenerFilters

logger = logging.getLogger(__name__)

# Default price / volume gates for the universe filter
_DEFAULT_MIN_PRICE = 5.0
_DEFAULT_MAX_PRICE = 500.0
_DEFAULT_MIN_VOLUME = 500_000


# ------------------------------------------------------------------
# Stage 0: Universe filter via grouped daily aggregates
# ------------------------------------------------------------------


async def universe_filter(
    config: ScreenerFilters,
    client: PolygonClient | None = None,
) -> list[ScreenerCandidate]:
    """Build the initial universe from a single grouped-daily API call.

    Uses ``/v2/aggs/grouped/locale/us/market/stocks/{date}`` which returns
    one bar per ticker for the most recent trading day.  This is a single
    API call regardless of universe size.

    Applies quick filters:
    - Price between ``min_price`` and ``max_price``
    - Stock volume above ``min_stock_volume``
    - Excludes penny stocks and illiquid names immediately

    Returns ``ScreenerCandidate`` objects enriched with price / volume so
    downstream filters can use the data without extra API calls.
    """
    if client is None:
        client = get_polygon_client()

    min_price = getattr(config, "min_price", None) or _DEFAULT_MIN_PRICE
    max_price = getattr(config, "max_price", None) or _DEFAULT_MAX_PRICE
    min_volume = getattr(config, "min_stock_volume", None) or _DEFAULT_MIN_VOLUME

    logger.info(
        "Running universe filter (price $%.0f-$%.0f, vol >= %s)",
        min_price,
        max_price,
        f"{min_volume:,}",
    )

    bars = await client.get_grouped_daily()

    passed: list[ScreenerCandidate] = []
    for bar in bars:
        ticker = bar.get("T", "")
        close = bar.get("c", 0.0)
        volume = int(bar.get("v", 0))

        # Quick price / volume gate
        if close < min_price or close > max_price:
            continue
        if volume < min_volume:
            continue

        # Skip non-standard tickers (warrants, units, rights)
        if any(ch in ticker for ch in (".", "/", "-")):
            continue

        passed.append(
            ScreenerCandidate(
                ticker=ticker,
                price=close,
                stock_volume=volume,
                passed_filters=["universe"],
            )
        )

    logger.info(
        "Universe filter: %d/%d tickers passed", len(passed), len(bars)
    )
    return passed


# ------------------------------------------------------------------
# Stage 1: Liquidity filter (options volume + spread)
# ------------------------------------------------------------------


async def liquidity_filter(
    candidates: list[ScreenerCandidate],
    config: ScreenerFilters,
    client: PolygonClient,
    *,
    batch_size: int = 20,
) -> list[ScreenerCandidate]:
    """Filter tickers by options volume and bid-ask spread.

    For the candidates that passed the universe filter, we now pull options
    chain snapshots in batches to check option-specific liquidity.
    """
    import asyncio

    min_volume = config.min_options_volume or 100
    max_spread = config.max_bid_ask_spread or 0.10

    passed: list[ScreenerCandidate] = []

    async def _check(cand: ScreenerCandidate) -> ScreenerCandidate | None:
        try:
            chain = await client.get_options_chain(
                cand.ticker, min_dte=1, max_dte=14
            )
            if not chain:
                return None

            total_volume = sum(
                c.get("day", {}).get("volume", 0) for c in chain
            )
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

            if total_volume < min_volume:
                return None
            if avg_spread > max_spread:
                return None

            cand.options_volume = total_volume
            cand.open_interest = total_oi
            cand.passed_filters.append("liquidity")
            return cand
        except Exception:
            logger.debug(
                "Liquidity check failed for %s", cand.ticker, exc_info=True
            )
            return None

    for i in range(0, len(candidates), batch_size):
        batch = candidates[i : i + batch_size]
        tasks = [_check(c) for c in batch]
        results = await asyncio.gather(*tasks)
        passed.extend(r for r in results if r is not None)

    logger.info("Liquidity filter: %d/%d passed", len(passed), len(candidates))
    return passed


# ------------------------------------------------------------------
# Stage 2: IV rank filter
# ------------------------------------------------------------------


async def iv_rank_filter(
    candidates: list[ScreenerCandidate],
    config: ScreenerFilters,
    client: PolygonClient,
) -> list[ScreenerCandidate]:
    """Filter candidates by IV rank (requires historical IV data).

    Uses Polygon OHLC history to approximate historical IV from close-to-close
    realised vol as a proxy when per-contract IV history is unavailable.
    """
    import asyncio
    import math

    from app.data.options_math import calculate_iv_rank

    min_rank = config.min_iv_rank or 30.0
    max_rank = config.max_iv_rank or 80.0

    async def _check(cand: ScreenerCandidate) -> ScreenerCandidate | None:
        try:
            bars = await client.get_daily_bars(cand.ticker, days=365)
            if len(bars) < 30:
                return None
            closes = [b["c"] for b in bars if "c" in b]
            if len(closes) < 21:
                return None

            # 20-day rolling realised vol windows
            window = 20
            historical_rvs: list[float] = []
            for i in range(window, len(closes)):
                w = closes[i - window : i]
                log_rets = [
                    math.log(w[j] / w[j - 1])
                    for j in range(1, len(w))
                    if w[j - 1] > 0
                ]
                if log_rets:
                    mean_r = sum(log_rets) / len(log_rets)
                    var = sum((r - mean_r) ** 2 for r in log_rets) / len(
                        log_rets
                    )
                    historical_rvs.append(math.sqrt(var) * math.sqrt(252))

            if not historical_rvs:
                return None

            current_rv = historical_rvs[-1]
            rank = calculate_iv_rank(current_rv, historical_rvs)

            if min_rank <= rank <= max_rank:
                cand.iv_rank = rank
                cand.passed_filters.append("iv_rank")
                return cand
        except Exception:
            logger.debug(
                "IV rank check failed for %s", cand.ticker, exc_info=True
            )
        return None

    tasks = [_check(c) for c in candidates]
    results = await asyncio.gather(*tasks)
    passed = [r for r in results if r is not None]
    logger.info("IV rank filter: %d/%d passed", len(passed), len(candidates))
    return passed


# ------------------------------------------------------------------
# Stage 3: Unusual activity filter
# ------------------------------------------------------------------


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
            chain = await client.get_options_chain(
                cand.ticker, min_dte=1, max_dte=14
            )
            if not chain:
                if min_score <= 0:
                    passed.append(cand)
                continue

            total_vol = sum(
                c.get("day", {}).get("volume", 0) for c in chain
            )
            total_oi = sum(c.get("open_interest", 0) for c in chain)
            vol_oi_ratio = total_vol / max(total_oi, 1)

            # Simple score: ratio above 0.5 is noteworthy
            score = round(min(vol_oi_ratio / 2.0, 1.0), 2)

            if score >= min_score:
                cand.unusual_activity_score = score
                cand.passed_filters.append("unusual_activity")
                passed.append(cand)
        except Exception:
            logger.debug(
                "Unusual activity check failed for %s",
                cand.ticker,
                exc_info=True,
            )
            if min_score <= 0:
                passed.append(cand)

    logger.info(
        "Unusual activity filter: %d/%d passed", len(passed), len(candidates)
    )
    return passed


# ------------------------------------------------------------------
# Stage 4: Technical momentum filter
# ------------------------------------------------------------------


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
    import pandas_ta as ta

    min_rs = config.min_relative_strength or 0.0
    max_rs = config.max_relative_strength or 100.0

    passed: list[ScreenerCandidate] = []

    for cand in candidates:
        try:
            bars = await client.get_daily_bars(cand.ticker, days=90)
            if len(bars) < 50:
                continue

            df = pd.DataFrame(bars)
            df = df.rename(
                columns={
                    "o": "open",
                    "h": "high",
                    "l": "low",
                    "c": "close",
                    "v": "volume",
                }
            )

            rsi_series = ta.rsi(df["close"], length=14)
            ema_9 = ta.ema(df["close"], length=9)
            ema_21 = ta.ema(df["close"], length=21)
            ema_50 = ta.ema(df["close"], length=50)

            if rsi_series is None or rsi_series.empty:
                continue

            rsi = float(rsi_series.iloc[-1])
            if pd.isna(rsi):
                continue

            e9 = float(ema_9.iloc[-1]) if ema_9 is not None else 0
            e21 = float(ema_21.iloc[-1]) if ema_21 is not None else 0
            e50 = float(ema_50.iloc[-1]) if ema_50 is not None else 0

            alignment_score = 0.0
            if e9 > e21 > e50:
                alignment_score = 1.0  # fully bullish
            elif e9 < e21 < e50:
                alignment_score = 1.0  # fully bearish (still tradeable)
            elif e9 > e21:
                alignment_score = 0.5

            tech_score = round((alignment_score * 50) + (rsi / 2), 2)

            if min_rs <= tech_score <= max_rs:
                cand.technical_score = tech_score
                cand.passed_filters.append("technical_momentum")
                passed.append(cand)
        except Exception:
            logger.debug(
                "Technical filter failed for %s",
                cand.ticker,
                exc_info=True,
            )

    logger.info(
        "Technical momentum filter: %d/%d passed",
        len(passed),
        len(candidates),
    )
    return passed
