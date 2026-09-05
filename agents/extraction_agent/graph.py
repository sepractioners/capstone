"""The LangGraph pipeline: load -> extract -> ingest.

`extract` internally branches on format: PDF pages go through the
per-page LLM extraction + merge; JSON/CSV records skip the LLM entirely
and go straight through structured_mapper.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from . import loaders, structured_mapper
from .extraction_node import extract_page
from .loaders import LoadedDocument, content_hash_for, media_type_for_format
from .mcp_client import ingest_via_mcp
from .merge_node import merge_page_extractions
from .schema import ContractCandidate, PageExtraction


class PipelineState(TypedDict, total=False):
    """State passed between the load, extract, and ingest graph nodes."""

    file_path: str
    database_path: Optional[str]
    loaded: LoadedDocument
    candidates: list[ContractCandidate]
    results: list[dict[str, Any]]


def load_node(state: PipelineState) -> dict[str, Any]:
    """Load the input file named in the graph state."""
    return {"loaded": loaders.load(state["file_path"])}


async def extract_node(state: PipelineState) -> dict[str, Any]:
    """Extract candidates from a loaded PDF, JSON file, or CSV file.

    PDFs are sent page by page to the LLM and then merged. Structured inputs
    are mapped directly, with one candidate produced for each record.
    """
    loaded = state["loaded"]

    if loaded.format == "pdf":
        page_extractions: list[PageExtraction] = []
        preceding_tail = ""
        for chunk in loaded.chunks:
            extraction = await extract_page(chunk.index + 1, chunk.text or "", preceding_tail)
            page_extractions.append(extraction)
            preceding_tail = (chunk.text or "")[-200:]
        candidate = merge_page_extractions(
            page_extractions,
            source_uri=loaded.file_path,
            source_document_hash=loaded.file_content_hash,
            source_media_type=media_type_for_format(loaded.format),
            source_content_base64=base64.b64encode(loaded.file_bytes).decode("ascii"),
            source_original_filename=Path(loaded.file_path).name,
        )
        return {"candidates": [candidate]}

    candidates: list[ContractCandidate] = []
    for chunk in loaded.chunks:
        record = chunk.structured or {}
        record_bytes = json.dumps(record, sort_keys=True, default=str, indent=2).encode()
        record_hash = content_hash_for(record_bytes)
        candidates.append(
            structured_mapper.from_structured_record(
                record,
                source_uri=f"{loaded.file_path}#record-{chunk.index}",
                content_hash=record_hash,
                source_media_type="application/json",
                source_content_base64=base64.b64encode(record_bytes).decode("ascii"),
                source_original_filename=f"{Path(loaded.file_path).name}#record-{chunk.index}",
            )
        )
    return {"candidates": candidates}


async def ingest_node(state: PipelineState) -> dict[str, Any]:
    """Persist every extracted candidate through the MCP server."""
    results = []
    for candidate in state.get("candidates", []):
        results.append(await ingest_via_mcp(candidate, state.get("database_path")))
    return {"results": results}


def build_graph():
    """Compile the load -> extract -> ingest LangGraph pipeline."""
    graph = StateGraph(PipelineState)
    graph.add_node("load", load_node)
    graph.add_node("extract", extract_node)
    graph.add_node("ingest", ingest_node)
    graph.set_entry_point("load")
    graph.add_edge("load", "extract")
    graph.add_edge("extract", "ingest")
    graph.add_edge("ingest", END)
    return graph.compile()
