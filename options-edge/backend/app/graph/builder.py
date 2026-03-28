"""Build and compile the LangGraph analysis pipeline."""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from app.models.state import AnalysisState

from app.graph.nodes.fetch_market_data import fetch_market_data
from app.graph.nodes.fetch_options_chain import fetch_options_chain
from app.graph.nodes.detect_technical_patterns import detect_technical_patterns
from app.graph.nodes.detect_unusual_activity import detect_unusual_activity
from app.graph.nodes.fetch_news_context import fetch_news_context
from app.graph.nodes.classify_context import classify_context
from app.graph.nodes.analyze_catalyst import analyze_catalyst_setup
from app.graph.nodes.analyze_technical import analyze_technical_setup
from app.graph.nodes.analyze_mean_reversion import analyze_mean_reversion_setup
from app.graph.nodes.analyze_flow_driven import analyze_flow_driven_setup
from app.graph.nodes.analyze_range_bound import analyze_range_bound_setup
from app.graph.nodes.check_trap_detection import check_trap_detection
from app.graph.nodes.synthesize_thesis import synthesize_thesis
from app.graph.nodes.save_thesis import save_thesis
from app.graph.routing import ALL_BRANCH_NODES, route_to_branches

logger = logging.getLogger(__name__)


def build_analysis_graph() -> StateGraph:
    """Construct the full options analysis StateGraph.

    Graph topology:

        START
          |
          v
        ┌──────────────────────────────────────────────┐
        │  Phase 1 -- Parallel data gathering          │
        │  fetch_market_data                           │
        │  fetch_options_chain                         │
        │  detect_technical_patterns (after market)    │
        │  detect_unusual_activity (after options)     │
        │  fetch_news_context                          │
        └──────────────────────────────────────────────┘
          |
          v
        classify_context
          |
          v  (conditional fan-out)
        ┌──────────────────────────────────────────────┐
        │  Phase 3 -- Analysis branches (conditional)  │
        │  analyze_catalyst                            │
        │  analyze_technical                           │
        │  analyze_mean_reversion                      │
        │  analyze_flow_driven                         │
        │  analyze_range_bound                         │
        └──────────────────────────────────────────────┘
          |
          v
        check_trap_detection
          |
          v
        synthesize_thesis
          |
          v
        save_thesis
          |
          v
        END
    """
    graph = StateGraph(AnalysisState)

    # ── Phase 1: Data gathering nodes ────────────────────────────────────
    graph.add_node("fetch_market_data", fetch_market_data)
    graph.add_node("fetch_options_chain", fetch_options_chain)
    graph.add_node("detect_technical_patterns", detect_technical_patterns)
    graph.add_node("detect_unusual_activity", detect_unusual_activity)
    graph.add_node("fetch_news_context", fetch_news_context)

    # ── Phase 2: Classification ──────────────────────────────────────────
    graph.add_node("classify_context", classify_context)

    # ── Phase 3: Analysis branches ───────────────────────────────────────
    graph.add_node("analyze_catalyst", analyze_catalyst_setup)
    graph.add_node("analyze_technical", analyze_technical_setup)
    graph.add_node("analyze_mean_reversion", analyze_mean_reversion_setup)
    graph.add_node("analyze_flow_driven", analyze_flow_driven_setup)
    graph.add_node("analyze_range_bound", analyze_range_bound_setup)

    # ── Phase 4: Synthesis ───────────────────────────────────────────────
    graph.add_node("check_trap_detection", check_trap_detection)
    graph.add_node("synthesize_thesis", synthesize_thesis)
    graph.add_node("save_thesis", save_thesis)

    # ── Edges: START -> Phase 1 (parallel fan-out) ───────────────────────
    # All three independent data fetches start from the entry point.
    graph.set_entry_point("fetch_market_data")

    # fetch_market_data and fetch_options_chain run first;
    # technical patterns needs market_data, unusual activity needs options_chain.
    # fetch_news_context is fully independent.
    graph.add_edge("fetch_market_data", "detect_technical_patterns")
    graph.add_edge("fetch_options_chain", "detect_unusual_activity")

    # We also want fetch_options_chain and fetch_news_context to start in
    # parallel with fetch_market_data.  LangGraph supports multiple entry
    # points via fan-out from __start__.  We add explicit edges from __start__
    # to the other two roots so they are all kicked off concurrently.
    graph.add_edge("__start__", "fetch_options_chain")
    graph.add_edge("__start__", "fetch_news_context")

    # ── Edges: Phase 1 -> Phase 2 (fan-in) ───────────────────────────────
    # classify_context must wait for ALL phase-1 nodes to complete.
    graph.add_edge("detect_technical_patterns", "classify_context")
    graph.add_edge("detect_unusual_activity", "classify_context")
    graph.add_edge("fetch_news_context", "classify_context")

    # ── Edges: Phase 2 -> Phase 3 (conditional fan-out) ──────────────────
    # route_to_branches returns a list of node names to execute.
    graph.add_conditional_edges(
        "classify_context",
        route_to_branches,
        # Map each possible return value to its node name (identity mapping)
        {node: node for node in ALL_BRANCH_NODES},
    )

    # ── Edges: Phase 3 -> Phase 4 (fan-in) ───────────────────────────────
    # All analysis branches converge into trap detection.
    for branch_node in ALL_BRANCH_NODES:
        graph.add_edge(branch_node, "check_trap_detection")

    # ── Edges: Phase 4 (sequential) ─────────────────────────────────────
    graph.add_edge("check_trap_detection", "synthesize_thesis")
    graph.add_edge("synthesize_thesis", "save_thesis")
    graph.add_edge("save_thesis", END)

    return graph


def _get_checkpointer():
    """Create a LangGraph async Postgres checkpointer for crash recovery.

    Uses the same database connection string as the main application.
    Returns ``None`` if the checkpointer cannot be initialised (e.g.
    missing dependency), in which case the graph runs without
    checkpoint persistence.
    """
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from app.config import get_settings

        settings = get_settings()
        db_url = settings.DATABASE_URL

        # langgraph-checkpoint-postgres expects a raw asyncpg DSN
        # (postgresql+asyncpg:// -> postgresql://)
        if "+asyncpg" in db_url:
            db_url = db_url.replace("+asyncpg", "")

        return AsyncPostgresSaver.from_conn_string(db_url)
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-postgres not installed; "
            "running without checkpoint persistence"
        )
        return None
    except Exception:
        logger.warning(
            "Failed to initialise Postgres checkpointer; "
            "running without checkpoint persistence",
            exc_info=True,
        )
        return None


# Compile the graph once at module level for reuse.
# The checkpointer enables crash recovery: if a long-running discovery
# run is interrupted, it can resume from the last completed node.
_checkpointer = _get_checkpointer()
analysis_graph = build_analysis_graph().compile(checkpointer=_checkpointer)
