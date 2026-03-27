"""LangGraph state schema for the options analysis pipeline."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# MarketData sub-models
# ---------------------------------------------------------------------------

class OHLCBar(BaseModel):
    """Single OHLCV bar."""

    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    timestamp: str = ""
    vwap: float = 0.0


class MarketData(BaseModel):
    """Current and historical market data for the underlying ticker."""

    current_price: float = 0.0
    prev_close: float = 0.0
    volume: int = 0
    today_change_pct: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    vwap: float = 0.0
    ohlc_history: list[OHLCBar] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# OptionsChain sub-models
# ---------------------------------------------------------------------------

class OptionContract(BaseModel):
    """A single options contract with greeks."""

    ticker: str = ""
    contract_type: str = ""
    expiration_date: str = ""
    strike_price: float = 0.0
    implied_volatility: float = 0.0
    open_interest: int = 0
    volume: int = 0
    last_price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0


class OptionsChainSummary(BaseModel):
    """Aggregate summary statistics for the options chain."""

    avg_call_iv: float = 0.0
    avg_put_iv: float = 0.0
    total_call_oi: int = 0
    total_put_oi: int = 0
    total_call_volume: int = 0
    total_put_volume: int = 0
    put_call_oi_ratio: float = 0.0
    total_oi: int = 0
    iv_rank: Optional[float] = None


class OptionsChain(BaseModel):
    """Options chain snapshot including contracts, expirations, and summary."""

    contracts: list[OptionContract] = Field(default_factory=list)
    expirations: list[str] = Field(default_factory=list)
    summary: Optional[OptionsChainSummary] = None


# ---------------------------------------------------------------------------
# TechnicalAnalysis sub-models
# ---------------------------------------------------------------------------

class DetectedPattern(BaseModel):
    """A single detected chart pattern."""

    name: str = ""
    type: str = ""
    confidence: float = 0.0
    price_level: float = 0.0


class TechnicalIndicators(BaseModel):
    """Computed technical indicator values."""

    rsi_14: float = 0.0
    ema_9: float = 0.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    macd_line: float = 0.0
    signal_line: float = 0.0
    macd_histogram: float = 0.0
    vwap: float = 0.0
    current_price: float = 0.0
    trend: str = ""
    macd_signal: str = ""


class TechnicalAnalysis(BaseModel):
    """Technical analysis output: patterns, indicators, and key levels."""

    patterns: list[DetectedPattern] = Field(default_factory=list)
    indicators: Optional[TechnicalIndicators] = None
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# UnusualActivity sub-models
# ---------------------------------------------------------------------------

class FlowAnomaly(BaseModel):
    """A single unusual flow anomaly."""

    ticker: str = ""
    contract_type: str = ""
    strike: float = 0.0
    expiration: str = ""
    volume: int = 0
    oi: int = 0
    volume_oi_ratio: float = 0.0
    is_opening: bool = False


class BlockTrade(BaseModel):
    """A single block trade."""

    ticker: str = ""
    contract_type: str = ""
    strike: float = 0.0
    expiration: str = ""
    size: int = 0
    premium: float = 0.0
    direction: str = ""


class OIChange(BaseModel):
    """Open interest change for a contract."""

    ticker: str = ""
    contract_type: str = ""
    strike: float = 0.0
    expiration: str = ""
    prev_oi: int = 0
    current_oi: int = 0
    change_pct: float = 0.0


class UnusualActivity(BaseModel):
    """Unusual options activity signals."""

    flow_anomalies: list[FlowAnomaly] = Field(default_factory=list)
    block_trades: list[BlockTrade] = Field(default_factory=list)
    put_call_ratio: float = 0.0
    oi_changes: list[OIChange] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# NewsContext (unchanged)
# ---------------------------------------------------------------------------

class NewsContext(BaseModel):
    """News and sentiment context for the ticker."""

    headlines: list[str] = Field(default_factory=list)
    summaries: list[str] = Field(default_factory=list)
    sentiment: str = "neutral"
    analyst_actions: list[dict] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# BranchAnalysis sub-models
# ---------------------------------------------------------------------------

class SpreadLeg(BaseModel):
    """A single leg of a spread."""

    contract_type: str = ""
    strike: float = 0.0
    expiration: str = ""
    action: Literal["buy", "sell"] = "buy"


class SpreadCandidate(BaseModel):
    """A recommended spread trade candidate."""

    spread_type: str = ""
    direction: str = ""
    legs: list[SpreadLeg] = Field(default_factory=list)
    entry_price: float = 0.0
    max_profit: float = 0.0
    max_loss: float = 0.0
    breakevens: list[float] = Field(default_factory=list)
    probability_of_profit: float = 0.0
    confidence: float = 0.0
    rationale: str = ""


class BranchAnalysis(BaseModel):
    """Analysis result for a specific setup classification branch."""

    classification: str = ""
    spread_recommendations: list[SpreadCandidate] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# TrapWarning (unchanged)
# ---------------------------------------------------------------------------

class TrapWarning(BaseModel):
    """Warning generated from historical thesis similarity matching."""

    similar_thesis_id: str
    similarity_score: float
    outcome: str
    warning: str


# ---------------------------------------------------------------------------
# Thesis (unchanged)
# ---------------------------------------------------------------------------

class Thesis(BaseModel):
    """Final trade thesis output from the analysis pipeline."""

    ticker: str
    direction: str
    spread_type: str
    short_strike: float
    long_strike: float
    expiration_date: str
    entry_price: float
    max_profit: float
    max_loss: float
    profit_target: float
    stop_loss: float
    confidence: float
    reasoning: str
    setup_classifications: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level pipeline state
# ---------------------------------------------------------------------------

class AnalysisState(BaseModel):
    """Main LangGraph state that flows through the analysis graph.

    This is the top-level state object passed between graph nodes. All fields
    except ``ticker`` and ``flow_type`` are optional so nodes can populate them
    incrementally.
    """

    # Required inputs
    ticker: str
    flow_type: str

    # Populated by data-fetching nodes
    market_data: Optional[MarketData] = None
    options_chain: Optional[OptionsChain] = None

    # Populated by analysis nodes
    technical_analysis: Optional[TechnicalAnalysis] = None
    unusual_activity: Optional[UnusualActivity] = None
    news_context: Optional[NewsContext] = None

    # Populated by classification / branching nodes
    setup_classifications: Optional[list[str]] = None
    branch_analyses: Optional[dict[str, BranchAnalysis]] = None

    # Populated by trap-detection node
    trap_warnings: Optional[list[TrapWarning]] = None

    # Final output
    thesis: Optional[Thesis] = None
