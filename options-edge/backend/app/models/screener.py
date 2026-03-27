"""Pydantic models for screener configuration and results."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ScreenerFilters(BaseModel):
    """Filter criteria used by the options screener."""

    # Volume & liquidity
    min_options_volume: Optional[int] = None
    max_bid_ask_spread: Optional[float] = None

    # Implied volatility
    min_iv_rank: Optional[float] = None
    max_iv_rank: Optional[float] = None

    # Activity ratios
    min_volume_oi_ratio: Optional[float] = None

    # Technical strength
    min_relative_strength: Optional[float] = None
    max_relative_strength: Optional[float] = None

    # Price filters
    min_price: Optional[float] = None
    max_price: Optional[float] = None

    # Market-cap filter (in millions)
    min_market_cap: Optional[float] = None
    max_market_cap: Optional[float] = None

    # Sector / industry inclusion lists
    sectors: Optional[list[str]] = None
    industries: Optional[list[str]] = None

    # Earnings proximity (days until next earnings)
    min_days_to_earnings: Optional[int] = None
    max_days_to_earnings: Optional[int] = None

    # Unusual activity threshold
    min_unusual_activity_score: Optional[float] = None


class ScreenerCandidate(BaseModel):
    """A single ticker that passed the screener filters."""

    ticker: str
    iv_rank: Optional[float] = None
    options_volume: Optional[int] = None
    unusual_activity_score: Optional[float] = None
    technical_score: Optional[float] = None
    passed_filters: list[str] = Field(default_factory=list)


class ScreenerResult(BaseModel):
    """Aggregated screener output."""

    candidates: list[ScreenerCandidate] = Field(default_factory=list)
    total_screened: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
