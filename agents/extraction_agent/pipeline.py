"""The single entry point the driver script (sythetic_data_loader) calls:
run one file through load -> extract -> ingest and get back the MCP
server's IngestResult(s) for it (a CSV/JSON file can yield more than one).
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from .graph import build_graph

_graph = build_graph()


async def arun(file_path: str, database_path: Optional[str] = None) -> list[dict[str, Any]]:
    """Run one source file asynchronously and return MCP ingest results."""
    final_state = await _graph.ainvoke({"file_path": file_path, "database_path": database_path})
    return final_state.get("results", [])


def run(file_path: str, database_path: Optional[str] = None) -> list[dict[str, Any]]:
    """Run the extraction pipeline synchronously from a normal Python caller."""
    return asyncio.run(arun(file_path, database_path))
