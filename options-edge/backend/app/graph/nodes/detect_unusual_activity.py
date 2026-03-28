"""Detect unusual options activity through volume, OI, and flow analysis."""

from __future__ import annotations

import logging
from statistics import mean, stdev

from app.models.state import AnalysisState, UnusualActivity, FlowAnomaly, BlockTrade, OIChange

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

    flow_anomalies: list[FlowAnomaly] = []
    block_trades: list[BlockTrade] = []
    oi_changes: list[OIChange] = []

    total_call_volume = 0
    total_put_volume = 0

    # -- Per-contract analysis ---------------------------------------------
    volume_oi_ratios: list[float] = []

    for contract in contracts:
        vol = contract.volume
        oi = contract.open_interest
        contract_type = contract.contract_type
        strike = contract.strike_price
        expiration = contract.expiration_date
        last_price = contract.last_price
        iv = contract.implied_volatility

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
                flow_anomalies.append(FlowAnomaly(
                    ticker=state.ticker,
                    contract_type=contract_type,
                    strike=strike,
                    expiration=expiration,
                    volume=vol,
                    oi=oi,
                    volume_oi_ratio=round(ratio, 2),
                    is_opening=vol > oi,
                ))

        # Block trade detection
        estimated_premium = vol * last_price * 100  # each contract = 100 shares
        if vol >= BLOCK_TRADE_MIN_SIZE and estimated_premium >= BLOCK_TRADE_MIN_PREMIUM:
            block_trades.append(BlockTrade(
                ticker=state.ticker,
                contract_type=contract_type,
                strike=strike,
                expiration=expiration,
                size=vol,
                premium=round(estimated_premium, 2),
                direction=_classify_block_trade(contract_type, vol, oi, strike, state),
            ))

    # -- Put/call ratio analysis -------------------------------------------
    if total_call_volume > 0:
        put_call_ratio = total_put_volume / total_call_volume
    else:
        put_call_ratio = 0.0

    if put_call_ratio > PUT_CALL_RATIO_EXTREME_HIGH:
        flow_anomalies.append(FlowAnomaly(
            ticker=state.ticker,
            contract_type="put",
            volume=total_put_volume,
            oi=0,
            volume_oi_ratio=round(put_call_ratio, 3),
            is_opening=False,
        ))
    elif put_call_ratio < PUT_CALL_RATIO_EXTREME_LOW and put_call_ratio > 0:
        flow_anomalies.append(FlowAnomaly(
            ticker=state.ticker,
            contract_type="call",
            volume=total_call_volume,
            oi=0,
            volume_oi_ratio=round(put_call_ratio, 3),
            is_opening=False,
        ))

    # -- OI change analysis ------------------------------------------------
    # Group contracts by strike+expiration to detect unusual OI concentrations
    all_oi_values = [c.open_interest for c in contracts if c.open_interest > 0]
    if len(all_oi_values) >= 5:
        oi_mean = mean(all_oi_values)
        oi_std = stdev(all_oi_values) if len(all_oi_values) > 1 else 0
        oi_threshold = oi_mean + (OI_CHANGE_STDDEV_MULTIPLIER * oi_std)

        for contract in contracts:
            current_oi = contract.open_interest
            if current_oi > oi_threshold:
                # Without historical data, use threshold as a proxy for prev_oi
                change_pct = ((current_oi - oi_mean) / oi_mean * 100) if oi_mean > 0 else 0.0
                oi_changes.append(OIChange(
                    ticker=state.ticker,
                    contract_type=contract.contract_type,
                    strike=contract.strike_price,
                    expiration=contract.expiration_date,
                    prev_oi=int(oi_mean),
                    current_oi=current_oi,
                    change_pct=round(change_pct, 1),
                ))

    # -- Sort by significance ----------------------------------------------
    flow_anomalies.sort(key=lambda x: x.volume_oi_ratio, reverse=True)
    block_trades.sort(key=lambda x: x.premium, reverse=True)
    oi_changes.sort(key=lambda x: x.current_oi, reverse=True)

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
    current_price = state.market_data.current_price if state.market_data else 0.0

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
