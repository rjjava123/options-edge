"""Detect unusual options activity through volume, OI, and flow analysis."""

from __future__ import annotations

import logging
from statistics import mean, stdev

from app.models.state import AnalysisState, UnusualActivity

logger = logging.getLogger(__name__)

# Thresholds for flagging unusual activity
VOLUME_OI_RATIO_THRESHOLD = 1.5
BLOCK_TRADE_MIN_SIZE = 100  # contracts
BLOCK_TRADE_MIN_PREMIUM = 50_000  # dollars
PUT_CALL_RATIO_EXTREME_LOW = 0.5
PUT_CALL_RATIO_EXTREME_HIGH = 1.5
OI_CHANGE_STDDEV_MULTIPLIER = 2.0


async def detect_unusual_activity(state: AnalysisState) -> dict:
    """Analyze options chain for unusual activity signals.

    Pure-Python analysis (no external API calls) that examines:
    - Volume/OI ratio anomalies per contract
    - Block trades (large single-contract volume with significant premium)
    - Put/call ratio deviations from norms
    - Open interest changes that indicate new positioning

    Returns a dict keyed by ``unusual_activity`` for state merging.
    """
    if state.options_chain is None or not state.options_chain.contracts:
        logger.warning("No options chain data available for unusual activity detection")
        return {"unusual_activity": UnusualActivity()}

    contracts = state.options_chain.contracts
    logger.info("Scanning %d contracts for unusual activity on %s", len(contracts), state.ticker)

    flow_anomalies: list[dict] = []
    block_trades: list[dict] = []
    oi_changes: list[dict] = []

    total_call_volume = 0
    total_put_volume = 0

    # -- Per-contract analysis ---------------------------------------------
    volume_oi_ratios: list[float] = []

    for contract in contracts:
        vol = contract.get("volume", 0)
        oi = contract.get("open_interest", 0)
        contract_type = contract.get("contract_type", "")
        strike = contract.get("strike_price", 0.0)
        expiration = contract.get("expiration_date", "")
        last_price = contract.get("last_price", 0.0)
        iv = contract.get("implied_volatility", 0.0)

        # Accumulate totals for put/call ratio
        if contract_type == "call":
            total_call_volume += vol
        elif contract_type == "put":
            total_put_volume += vol

        # Volume/OI ratio
        if oi > 0:
            ratio = vol / oi
            volume_oi_ratios.append(ratio)

            if ratio >= VOLUME_OI_RATIO_THRESHOLD and vol > 50:
                flow_anomalies.append({
                    "type": "high_volume_oi_ratio",
                    "contract_type": contract_type,
                    "strike": strike,
                    "expiration": expiration,
                    "volume": vol,
                    "open_interest": oi,
                    "ratio": round(ratio, 2),
                    "implied_volatility": round(iv, 4) if iv else None,
                    "signal": (
                        "Likely new positioning - volume significantly exceeds "
                        "existing open interest"
                    ),
                })

        # Block trade detection
        estimated_premium = vol * last_price * 100  # each contract = 100 shares
        if vol >= BLOCK_TRADE_MIN_SIZE and estimated_premium >= BLOCK_TRADE_MIN_PREMIUM:
            block_trades.append({
                "contract_type": contract_type,
                "strike": strike,
                "expiration": expiration,
                "volume": vol,
                "estimated_premium": round(estimated_premium, 2),
                "last_price": last_price,
                "open_interest": oi,
                "is_opening": vol > oi,  # heuristic: if volume exceeds OI, likely opening
                "signal": _classify_block_trade(contract_type, vol, oi, strike, state),
            })

    # -- Put/call ratio analysis -------------------------------------------
    if total_call_volume > 0:
        put_call_ratio = total_put_volume / total_call_volume
    else:
        put_call_ratio = 0.0

    if put_call_ratio > PUT_CALL_RATIO_EXTREME_HIGH:
        flow_anomalies.append({
            "type": "extreme_put_call_ratio",
            "put_call_ratio": round(put_call_ratio, 3),
            "total_put_volume": total_put_volume,
            "total_call_volume": total_call_volume,
            "signal": "Elevated put/call ratio suggests bearish sentiment or hedging",
        })
    elif put_call_ratio < PUT_CALL_RATIO_EXTREME_LOW and put_call_ratio > 0:
        flow_anomalies.append({
            "type": "extreme_put_call_ratio",
            "put_call_ratio": round(put_call_ratio, 3),
            "total_put_volume": total_put_volume,
            "total_call_volume": total_call_volume,
            "signal": "Low put/call ratio suggests bullish sentiment or call buying",
        })

    # -- OI change analysis ------------------------------------------------
    # Group contracts by strike+expiration to detect unusual OI concentrations
    oi_by_strike: dict[str, list[dict]] = {}
    for contract in contracts:
        key = f"{contract.get('strike_price')}-{contract.get('expiration_date')}"
        oi_by_strike.setdefault(key, []).append(contract)

    all_oi_values = [c.get("open_interest", 0) for c in contracts if c.get("open_interest", 0) > 0]
    if len(all_oi_values) >= 5:
        oi_mean = mean(all_oi_values)
        oi_std = stdev(all_oi_values) if len(all_oi_values) > 1 else 0
        oi_threshold = oi_mean + (OI_CHANGE_STDDEV_MULTIPLIER * oi_std)

        for contract in contracts:
            oi = contract.get("open_interest", 0)
            if oi > oi_threshold:
                oi_changes.append({
                    "contract_type": contract.get("contract_type"),
                    "strike": contract.get("strike_price"),
                    "expiration": contract.get("expiration_date"),
                    "open_interest": oi,
                    "threshold": round(oi_threshold, 0),
                    "signal": (
                        f"OI of {oi:,} is {oi / oi_mean:.1f}x the average - "
                        f"significant positioning at this strike"
                    ),
                })

    # -- Sort by significance ----------------------------------------------
    flow_anomalies.sort(key=lambda x: x.get("ratio", x.get("put_call_ratio", 0)), reverse=True)
    block_trades.sort(key=lambda x: x.get("estimated_premium", 0), reverse=True)
    oi_changes.sort(key=lambda x: x.get("open_interest", 0), reverse=True)

    unusual_activity = UnusualActivity(
        flow_anomalies=flow_anomalies[:20],  # cap to top signals
        block_trades=block_trades[:10],
        put_call_ratio=round(put_call_ratio, 4),
        oi_changes=oi_changes[:15],
    )

    logger.info(
        "Unusual activity scan complete: %d flow anomalies, %d block trades, "
        "P/C ratio=%.3f, %d OI outliers",
        len(flow_anomalies),
        len(block_trades),
        put_call_ratio,
        len(oi_changes),
    )

    return {"unusual_activity": unusual_activity}


def _classify_block_trade(
    contract_type: str,
    volume: int,
    oi: int,
    strike: float,
    state: AnalysisState,
) -> str:
    """Heuristic classification of a block trade's likely intent."""
    is_opening = volume > oi
    current_price = state.market_data.price if state.market_data else 0.0

    if contract_type == "call":
        if is_opening:
            if strike > current_price:
                return "Likely bullish opening - OTM call buying"
            else:
                return "Likely bullish opening - ITM call (deep conviction or hedge)"
        else:
            return "Possible closing or rolling of existing call position"
    else:  # put
        if is_opening:
            if strike < current_price:
                return "Likely bearish opening or portfolio hedge - OTM put buying"
            else:
                return "Likely bearish opening - ITM put (high conviction)"
        else:
            return "Possible closing or rolling of existing put position"
