"""Check whether a thesis has hit an exit condition."""

from __future__ import annotations

from datetime import date
from typing import Optional


def check_exit_conditions(thesis, latest_snapshot: dict) -> Optional[str]:
    """Evaluate exit conditions for a thesis given the latest snapshot data.

    Checks are applied in priority order:

    1. **Expiration passed** -- the thesis expiration date is today or earlier.
    2. **Profit target reached** -- current P&L percent meets or exceeds the
       profit target expressed as a percentage of max loss.
    3. **Stop loss hit** -- current P&L percent has breached the stop loss
       threshold (i.e. losses exceed the allowed adverse move).

    Parameters
    ----------
    thesis:
        The ORM ``Thesis`` instance with ``expiration_date``, ``profit_target``,
        ``stop_loss``, ``entry_price``, and ``max_loss`` attributes.
    latest_snapshot:
        A dict (or snapshot-like object) with at minimum ``pnl_percent`` and
        ``pnl_dollars`` keys representing current mark-to-market P&L.

    Returns
    -------
    str or None
        One of ``"closed_expiry"``, ``"closed_target"``, ``"closed_stop"``,
        or ``None`` if no exit condition is met.
    """
    today = date.today()

    # 1. Expiration check
    if thesis.expiration_date <= today:
        return "closed_expiry"

    pnl_dollars = latest_snapshot.get("pnl_dollars", 0.0)

    # 2. Profit target check
    # profit_target on the thesis is stored as a dollar amount representing
    # the target credit to capture (e.g., 0.35 on a 0.50 credit spread means
    # close when you've captured $0.35 of the $0.50 credit).
    if pnl_dollars >= thesis.profit_target:
        return "closed_target"

    # 3. Stop loss check
    # stop_loss is stored as a negative dollar amount (e.g., -1.50 means
    # close if losses exceed $1.50 per contract).
    if thesis.stop_loss < 0 and pnl_dollars <= thesis.stop_loss:
        return "closed_stop"
    elif thesis.stop_loss > 0 and pnl_dollars <= -thesis.stop_loss:
        # Handle case where stop_loss is stored as a positive magnitude
        return "closed_stop"

    return None
