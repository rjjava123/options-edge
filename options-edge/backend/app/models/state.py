"""LangGraph state schema for the options analysis pipeline."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class MarketData(BaseModel):
    """Current and historical market data for the underlying ticker."""

    price: float
    volume: int
    ohlc_history: list[dict] = Field(default_factory=list)
    quote: dict = Field(default_factory=dict)


class OptionsChain(BaseModel):
    """Options chain snapshot including contracts, expirations, and greeks."""

    contracts: list[dict] = Field(default_factory=list)
    expirations: list[str] = Field(default_factory=list)
    greeks: dict = Field(default_factory=dict)


class TechnicalAnalysis(BaseModel):
    """Technical analysis output: patterns, indicators, and key levels."""

    patterns: list[str] = Field(default_factory=list)
    indicators: dict = Field(default_factory=dict)
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    summary: str = ""


class UnusualActivity(BaseModel):
    """Unusual options activity signals."""

    flow_anomalies: list[dict] = Field(default_factory=list)
    block_trades: list[dict] = Field(default_factory=list)
    put_call_ratio: float = 0.0
    oi_changes: list[dict] = Field(default_factory=list)


class NewsContext(BaseModel):
    """News and sentiment context for the ticker."""

    headlines: list[str] = Field(default_factory=list)
    summaries: list[str] = Field(default_factory=list)
    sentiment: str = "neutral"
    analyst_actions: list[dict] = Field(default_factory=list)


class BranchAnalysis(BaseModel):
    """Analysis result for a specific setup classification branch."""

    classification: str
    spread_recommendations: list[dict] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0


class TrapWarning(BaseModel):
    """Warning generated from historical thesis similarity matching."""

    similar_thesis_id: str
    similarity_score: float
    outcome: str
    warning: str


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
