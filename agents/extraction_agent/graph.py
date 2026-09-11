"""The LangGraph pipeline: load -> extract -> review -> ingest.

`extract` branches on format: PDF pages go through per-page LLM extraction
+ merge; JSON/CSV records skip the LLM entirely and go straight through
structured_mapper. `review` is the one document-level reasoning pass - it
runs only for the PDF branch and is a pass-through for structured input.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional, TypedDict

from agent_trace import TraceRecorder
from langgraph.graph import END, StateGraph

from . import loaders, structured_mapper
from .extraction_node import extract_page
from .loaders import LoadedDocument, content_hash_for, media_type_for_format
from .mcp_client import ingest_via_mcp
from .merge_node import merge_page_extractions
from .review_node import has_blocker, review_candidate
from .vector_rag import retrieve_profile_with_vectors
from .schema import ContractCandidate, PageExtraction

logger = logging.getLogger(__name__)

PRECEDING_TAIL_CHARS = max(120, int(os.environ.get("EXTRACTION_PAGE_TAIL_CHARS", "400")))
# 0 = all pages. Cap the per-page LLM loop when a slow local model would
# otherwise take tens of minutes per contract; parties / title / dates /
# type live in the first pages of most contracts.
MAX_PAGES = max(0, int(os.environ.get("EXTRACTION_MAX_PAGES", "0")))
RAG_SAMPLE_PAGES = max(1, int(os.environ.get("EXTRACTION_RAG_SAMPLE_PAGES", "3")))
RAG_SAMPLE_CHARS = max(1000, int(os.environ.get("EXTRACTION_RAG_SAMPLE_CHARS", "6000")))
REVIEW_DOCUMENT_CHARS = max(4000, int(os.environ.get("EXTRACTION_REVIEW_DOCUMENT_CHARS", "30000")))


class PipelineState(TypedDict, total=False):
    """State passed between the load, extract, review, and ingest graph nodes."""

    file_path: str
    database_path: Optional[str]
    loaded: LoadedDocument
    candidates: list[ContractCandidate]
    results: list[dict[str, Any]]
    extraction_directive: dict[str, Any] | None
    progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None
    page_extractions: list[PageExtraction]
    document_text: str
    profile: dict[str, Any] | None
    debug: TraceRecorder


async def _progress(state: PipelineState, payload: dict[str, Any]) -> None:
    callback = state.get("progress_callback")
    if callback is not None:
        await callback(payload)


def _update_party_memory(memory: dict[str, Any], page: PageExtraction) -> None:
    """Keep JSON-safe party-name memory without mixing models and strings."""
    known = set(memory.get("parties", []))
    known.update(party.legal_name for party in page.parties)
    memory["parties"] = sorted(known)


def _update_document_memory(memory: dict[str, Any], page: PageExtraction) -> None:
    """Fold one page's observations into the per-document working memory.

    First-non-null wins for singletons; parties and defined terms accumulate.
    This memory is a local in ``extract_node`` for one ``ainvoke`` - it is
    never shared across documents.
    """
    if page.title and not memory.get("title"):
        memory["title"] = page.title
    if page.contract_type and not memory.get("contract_type"):
        memory["contract_type"] = page.contract_type
    _update_party_memory(memory, page)
    if page.defined_terms:
        memory.setdefault("defined_terms", {}).update(page.defined_terms)
    if page.clauses:
        memory["last_heading"] = page.clauses[-1].heading
    if not memory.get("renewal_terms") and page.renewal_terms.model_dump(exclude_defaults=True):
        memory["renewal_terms"] = page.renewal_terms.model_dump(mode="json", exclude_defaults=True)
    if not memory.get("termination_terms") and page.termination_terms.model_dump(exclude_defaults=True):
        memory["termination_terms"] = page.termination_terms.model_dump(mode="json", exclude_defaults=True)


def load_node(state: PipelineState) -> dict[str, Any]:
    """Load the input file named in the graph state."""
    return {"loaded": loaders.load(state["file_path"])}


async def extract_node(state: PipelineState) -> dict[str, Any]:
    """Extract candidates from a loaded PDF, JSON file, or CSV file.

    PDFs are sent page by page to the LLM and then merged. Structured inputs
    are mapped directly, with one candidate produced for each record.
    """
    loaded = state["loaded"]
    debug = state.get("debug") or TraceRecorder("extraction")
    logger.debug("extract_node format=%s chunks=%s file=%s", loaded.format, len(loaded.chunks), loaded.file_path)

    if loaded.format == "pdf":
        page_extractions: list[PageExtraction] = []
        preceding_tail = ""
        memory: dict[str, Any] = {}
        extraction_trace: list[dict[str, Any]] = []

        page_texts = [chunk.text or "" for chunk in loaded.chunks]
        sample_text = "\n\n".join(text for text in page_texts if text.strip())[:RAG_SAMPLE_CHARS]
        if RAG_SAMPLE_PAGES < len(page_texts):
            sample_text = "\n\n".join(
                text for text in page_texts[: RAG_SAMPLE_PAGES + 2] if text.strip()
            )[:RAG_SAMPLE_CHARS]
        rag_started = debug.start()
        profile = await retrieve_profile_with_vectors(loaded.file_path, sample_text)
        logger.debug("retrieved profile=%s mode=%s vector=%s score=%s", profile.get("id"), profile.get("retrieval_mode"), profile.get("vector_enabled"), profile.get("score"))
        debug.record(
            "rag_retrieval",
            context={"sample_text": sample_text, "sample_pages": RAG_SAMPLE_PAGES},
            retrieval=profile,
            started=rag_started,
        )

        pages = loaded.chunks if MAX_PAGES == 0 else loaded.chunks[:MAX_PAGES]
        for chunk in pages:
            await _progress(state, {"stage": "extracting", "page": chunk.index + 1, "total_pages": len(pages), "label": "Extracting contract"})
            extraction = await extract_page(chunk.index + 1, chunk.text or "", preceding_tail, memory, extraction_trace, profile, state.get("extraction_directive"), debug)
            page_extractions.append(extraction)
            preceding_tail = (chunk.text or "")[-PRECEDING_TAIL_CHARS:]
            _update_document_memory(memory, extraction)
            logger.debug(
                "page extraction payload page=%s payload=%s",
                chunk.index + 1,
                json.dumps(extraction.model_dump(mode="json"), ensure_ascii=False, default=str),
            )
        extraction_trace.append({
            "stage": "document_memory",
            "status": "completed",
            "memory_keys": sorted(memory.keys()),
            "defined_terms": len(memory.get("defined_terms", {})),
            "retrieval": {"enabled": profile.get("vector_enabled", False), "mode": profile.get("retrieval_mode"), "profile": profile.get("id"), "nearest_examples": profile.get("nearest_examples", []), "reason": profile.get("retrieval_error", "")},
        })
        candidate = merge_page_extractions(
            page_extractions,
            source_uri=loaded.file_path,
            source_document_hash=loaded.file_content_hash,
            source_media_type=media_type_for_format(loaded.format),
            source_content_base64=base64.b64encode(loaded.file_bytes).decode("ascii"),
            source_original_filename=Path(loaded.file_path).name,
            extraction_trace=extraction_trace,
        )
        debug.record("merge", output={"title": candidate.title, "contract_type": candidate.contract_type, "parties": [p.legal_name for p in candidate.parties], "clauses": len(candidate.clauses), "field_conflicts": [fc.model_dump() for fc in candidate.field_conflicts], "renewal_terms": candidate.renewal_terms.model_dump(mode="json"), "termination_terms": candidate.termination_terms.model_dump(mode="json")}, memory=dict(memory))
        document_text = "\n\n".join(text for text in page_texts if text.strip())[:REVIEW_DOCUMENT_CHARS]
        return {
            "candidates": [candidate],
            "page_extractions": page_extractions,
            "document_text": document_text,
            "profile": profile,
            "debug": debug,
        }

    candidates: list[ContractCandidate] = []
    for chunk in loaded.chunks:
        await _progress(state, {"stage": "mapping", "record": chunk.index + 1, "total_records": len(loaded.chunks), "label": "Mapping structured contract"})
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
                extraction_trace=[{"stage": "structured_mapping", "status": "completed", "record_index": chunk.index}],
            )
        )
    debug.record("structured_mapping", output={"records": len(candidates)}, note="no LLM call")
    return {"candidates": candidates, "debug": debug}


async def review_node(state: PipelineState) -> dict[str, Any]:
    """Run the document-level reasoning pass over a PDF-derived candidate.

    Structured (JSON/CSV) candidates have no ``page_extractions`` and pass
    through untouched - they never call the LLM.
    """
    page_extractions = state.get("page_extractions")
    if not page_extractions:
        return {}
    candidate = state["candidates"][0]
    await _progress(state, {"stage": "reviewing", "label": "Reviewing the assembled contract"})
    reviewed = await review_candidate(
        candidate,
        page_extractions,
        state.get("document_text", ""),
        state.get("profile"),
        state.get("extraction_directive"),
        state.get("debug"),
    )
    return {"candidates": [reviewed]}


async def ingest_node(state: PipelineState) -> dict[str, Any]:
    """Persist every extracted candidate, unless review raised a blocker."""
    debug = state.get("debug")
    debug_trace = debug.steps if debug is not None else []
    results = []
    for candidate in state.get("candidates", []):
        if has_blocker(candidate):
            results.append({
                "requires_human_confirmation": True,
                "review_findings": [finding.model_dump() for finding in candidate.review_findings],
                "review_summary": candidate.review_summary,
                "field_conflicts": [conflict.model_dump() for conflict in candidate.field_conflicts],
                "extraction_trace": candidate.extraction_trace,
                "debug_trace": debug_trace,
            })
            continue
        result = await ingest_via_mcp(candidate, state.get("database_path"))
        result["debug_trace"] = debug_trace
        results.append(result)
    return {"results": results}


def build_graph():
    """Compile the load -> extract -> review -> ingest LangGraph pipeline."""
    graph = StateGraph(PipelineState)
    graph.add_node("load", load_node)
    graph.add_node("extract", extract_node)
    graph.add_node("review", review_node)
    graph.add_node("ingest", ingest_node)
    graph.set_entry_point("load")
    graph.add_edge("load", "extract")
    graph.add_edge("extract", "review")
    graph.add_edge("review", "ingest")
    graph.add_edge("ingest", END)
    return graph.compile()


def build_candidate_graph():
    """load -> extract -> review, stopping before ingest (for evaluation)."""
    graph = StateGraph(PipelineState)
    graph.add_node("load", load_node)
    graph.add_node("extract", extract_node)
    graph.add_node("review", review_node)
    graph.set_entry_point("load")
    graph.add_edge("load", "extract")
    graph.add_edge("extract", "review")
    graph.add_edge("review", END)
    return graph.compile()
