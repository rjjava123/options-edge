"""Validation routes: run the full analysis graph for a single ticker."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.graph.builder import analysis_graph
from app.models.state import AnalysisState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/validate", tags=["validation"])


@router.post("/{ticker}")
async def validate_ticker(ticker: str, flow_type: str = "manual"):
    """Run the full analysis graph for a single ticker.

    Streams real-time updates as the graph progresses through each node,
    sending Server-Sent Events (SSE) to the client so the UI can display
    incremental progress.

    **Important**: the graph is invoked exactly once.  We stream events from
    ``astream_events`` and capture the final state from the last
    ``on_chain_end`` event rather than calling ``ainvoke`` a second time.
    """

    async def _event_stream():
        initial_state = AnalysisState(
            ticker=ticker.upper(),
            flow_type=flow_type,
        )

        try:
            # Track the final state as we stream -- the outermost
            # on_chain_end event contains the complete state dict.
            final_output: dict | None = None

            async for event in analysis_graph.astream_events(
                initial_state.model_dump(),
                version="v2",
            ):
                kind = event.get("event", "")
                name = event.get("name", "")

                if kind == "on_chain_start" and name != "LangGraph":
                    yield _sse_event("node_start", {"node": name})

                elif kind == "on_chain_end":
                    output = event.get("data", {}).get("output", {})

                    if name == "LangGraph":
                        # This is the outermost graph completing -- output
                        # is the final AnalysisState dict.
                        final_output = output
                    else:
                        summary = _summarize_output(name, output)
                        yield _sse_event(
                            "node_complete", {"node": name, "summary": summary}
                        )

                elif kind == "on_chain_error":
                    error_msg = str(
                        event.get("data", {}).get("error", "Unknown error")
                    )
                    yield _sse_event(
                        "node_error", {"node": name, "error": error_msg}
                    )

            # Extract thesis from the captured final state (no second invocation)
            if final_output is not None:
                thesis = final_output.get("thesis")
                if thesis:
                    yield _sse_event(
                        "thesis",
                        thesis if isinstance(thesis, dict) else thesis.model_dump(),
                    )
                else:
                    yield _sse_event("error", {"message": "No thesis generated"})
            else:
                yield _sse_event(
                    "error", {"message": "Graph completed without final output"}
                )

            yield _sse_event("complete", {"ticker": ticker.upper()})

        except Exception as exc:
            logger.exception("Validation failed for %s", ticker)
            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    payload = json.dumps(data, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


def _summarize_output(node_name: str, output: dict) -> dict:
    """Build a lightweight summary of a node's output for streaming."""
    summary: dict = {"node": node_name}

    if "market_data" in output and output["market_data"]:
        md = output["market_data"]
        if isinstance(md, dict):
            summary["price"] = md.get("current_price")
        else:
            summary["price"] = getattr(md, "current_price", None)

    if "options_chain" in output and output["options_chain"]:
        oc = output["options_chain"]
        contracts = (
            oc.get("contracts", [])
            if isinstance(oc, dict)
            else getattr(oc, "contracts", [])
        )
        summary["contracts_count"] = len(contracts)

    if "setup_classifications" in output:
        summary["classifications"] = output["setup_classifications"]

    if "thesis" in output and output["thesis"]:
        summary["thesis_generated"] = True

    return summary
