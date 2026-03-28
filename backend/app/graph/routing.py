"""Routing logic for conditional branching in the analysis graph."""

from __future__ import annotations

from typing import Literal

from app.models.state import AnalysisState

# Maps classification categories to their corresponding analysis node names
CLASSIFICATION_TO_NODE: dict[str, str] = {
    "catalyst": "analyze_catalyst",
    "technical": "analyze_technical",
    "mean_reversion": "analyze_mean_reversion",
    "flow_driven": "analyze_flow_driven",
    "range_bound": "analyze_range_bound",
}

ALL_BRANCH_NODES = list(CLASSIFICATION_TO_NODE.values())


def route_to_branches(state: AnalysisState) -> list[str]:
    """Determine which analysis branch nodes to execute based on setup classifications.

    Reads ``state.setup_classifications`` and maps each classification to its
    corresponding ``analyze_*`` node name. This function is used as conditional
    edge logic in the LangGraph ``StateGraph``.

    Returns:
        A list of node names to execute in parallel. Falls back to
        ``["analyze_technical"]`` if no classifications are present.
    """
    classifications = state.setup_classifications or []

    if not classifications:
        return ["analyze_technical"]

    nodes = []
    for classification in classifications:
        node_name = CLASSIFICATION_TO_NODE.get(classification)
        if node_name:
            nodes.append(node_name)

    # Fallback if no valid classifications mapped
    return nodes if nodes else ["analyze_technical"]
