"""The single entry point the driver script (sythetic_data_loader) calls:
run one file through load -> extract -> ingest and get back the MCP
server's IngestResult(s) for it (a CSV/JSON file can yield more than one).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from agent_trace import TraceRecorder

from .graph import build_candidate_graph, build_graph

logger = logging.getLogger(__name__)

_graph = build_graph()
_candidate_graph = build_candidate_graph()


async def arun(
    file_path: str,
    database_path: Optional[str] = None,
    extraction_directive: dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
) -> list[dict[str, Any]]:
    """Run one source file asynchronously and return MCP ingest results."""
    logger.debug("pipeline start file=%s database=%s", file_path, database_path)
    recorder = TraceRecorder("extraction")
    try:
        final_state = await _graph.ainvoke({
            "file_path": file_path,
            "database_path": database_path,
            "extraction_directive": extraction_directive,
            "progress_callback": progress_callback,
            "debug": recorder,
        })
    except Exception as exc:  # keep the partial trace on failure
        exc.debug_trace = recorder.steps  # type: ignore[attr-defined]
        raise
    logger.debug("pipeline complete file=%s results=%s", file_path, len(final_state.get("results", [])))
    return final_state.get("results", [])


def run(file_path: str, database_path: Optional[str] = None) -> list[dict[str, Any]]:
    """Run the extraction pipeline synchronously from a normal Python caller."""
    return asyncio.run(arun(file_path, database_path))


async def acandidates(
    file_path: str,
    database_path: Optional[str] = None,
    extraction_directive: dict[str, Any] | None = None,
) -> list[Any]:
    """Run load -> extract -> review and return candidates WITHOUT ingesting.

    Used by the extraction eval harness to score fields against ground truth
    without persisting anything through the domain.
    """
    final_state = await _candidate_graph.ainvoke({
        "file_path": file_path,
        "database_path": database_path,
        "extraction_directive": extraction_directive,
        "debug": TraceRecorder("extraction"),
    })
    return final_state.get("candidates", [])
