"""Fetch full options chain with greeks, IV, and open interest."""

from __future__ import annotations

import logging
from datetime import date, timedelta

from app.config import get_settings
from app.data.polygon_client import get_polygon_client
from app.models.state import AnalysisState, OptionsChain

logger = logging.getLogger(__name__)

# Target DTE window for relevant expirations
MIN_DTE = 14
MAX_DTE = 60


async def fetch_options_chain(state: AnalysisState) -> dict:
    """Retrieve the full options chain for expirations between 14-60 DTE.

    Pulls all available contracts within the target expiration window,
    including greeks (delta, gamma, theta, vega), implied volatility,
    and open interest for each strike.

    Returns a dict keyed by ``options_chain`` for state merging.
    """
    settings = get_settings()
    client = get_polygon_client(settings.POLYGON_API_KEY)
    ticker = state.ticker.upper()

    logger.info("Fetching options chain for %s (DTE %d-%d)", ticker, MIN_DTE, MAX_DTE)

    today = date.today()
    exp_from = (today + timedelta(days=MIN_DTE)).isoformat()
    exp_to = (today + timedelta(days=MAX_DTE)).isoformat()

    # Polygon options chain snapshot returns contracts with greeks
    chain_data = await client.get_options_chain(
        underlying_ticker=ticker,
        expiration_date_gte=exp_from,
        expiration_date_lte=exp_to,
    )

    results = chain_data.get("results", [])

    contracts: list[dict] = []
    expirations_set: set[str] = set()
    greeks_summary: dict = {
        "avg_call_iv": 0.0,
        "avg_put_iv": 0.0,
        "total_call_oi": 0,
        "total_put_oi": 0,
        "total_call_volume": 0,
        "total_put_volume": 0,
    }

    call_iv_values: list[float] = []
    put_iv_values: list[float] = []

    for contract in results:
        details = contract.get("details", {})
        greeks = contract.get("greeks", {})
        day = contract.get("day", {})

        contract_type = details.get("contract_type", "").lower()
        expiration = details.get("expiration_date", "")
        strike = details.get("strike_price", 0.0)
        iv = contract.get("implied_volatility", 0.0)
        oi = contract.get("open_interest", 0)
        volume = day.get("volume", 0)

        parsed = {
            "ticker": details.get("ticker", ""),
            "contract_type": contract_type,
            "expiration_date": expiration,
            "strike_price": strike,
            "implied_volatility": iv,
            "open_interest": oi,
            "volume": volume,
            "last_price": day.get("close", 0.0),
            "bid": contract.get("last_quote", {}).get("bid", 0.0),
            "ask": contract.get("last_quote", {}).get("ask", 0.0),
            "delta": greeks.get("delta", 0.0),
            "gamma": greeks.get("gamma", 0.0),
            "theta": greeks.get("theta", 0.0),
            "vega": greeks.get("vega", 0.0),
        }

        contracts.append(parsed)
        expirations_set.add(expiration)

        # Accumulate for summary
        if contract_type == "call":
            if iv:
                call_iv_values.append(iv)
            greeks_summary["total_call_oi"] += oi
            greeks_summary["total_call_volume"] += volume
        elif contract_type == "put":
            if iv:
                put_iv_values.append(iv)
            greeks_summary["total_put_oi"] += oi
            greeks_summary["total_put_volume"] += volume

    if call_iv_values:
        greeks_summary["avg_call_iv"] = sum(call_iv_values) / len(call_iv_values)
    if put_iv_values:
        greeks_summary["avg_put_iv"] = sum(put_iv_values) / len(put_iv_values)

    total_oi = greeks_summary["total_call_oi"] + greeks_summary["total_put_oi"]
    if greeks_summary["total_call_oi"] > 0:
        greeks_summary["put_call_oi_ratio"] = (
            greeks_summary["total_put_oi"] / greeks_summary["total_call_oi"]
        )
    else:
        greeks_summary["put_call_oi_ratio"] = 0.0

    greeks_summary["total_oi"] = total_oi

    options_chain = OptionsChain(
        contracts=contracts,
        expirations=sorted(expirations_set),
        greeks=greeks_summary,
    )

    logger.info(
        "Options chain fetched: %d contracts across %d expirations",
        len(contracts),
        len(expirations_set),
    )

    return {"options_chain": options_chain}
