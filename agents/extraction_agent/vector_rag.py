"""Compatibility layer for the hybrid lexical/vector RAG store."""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from pathlib import Path
from typing import Any

from agent_llm import EMBEDDING as _EMBEDDING
from agent_llm.embeddings import embed as _shared_embed

from .loaders import _load_pdf
from .hybrid_rag import DEFAULT_DB_PATH as DEFAULT_HYBRID_DB, add_records as add_hybrid_records, retrieve as hybrid_retrieve

logger = logging.getLogger(__name__)
UNCLASSIFIED = {
    "id": "unclassified",
    "name": "Unclassified contract",
    "score": 0.0,
    "required_fields": ["title", "parties"],
    "recommended_fields": ["contract_type", "key_dates", "clauses", "obligations", "commercial_terms", "signers"],
}

DEFAULT_INDEX_PATH = Path(os.environ.get("EXTRACTION_RAG_INDEX", "sythetic_data_loader/data/cuad_vector_index.json"))
DEFAULT_EMBEDDING_URL = _EMBEDDING.url
DEFAULT_EMBEDDING_MODEL = _EMBEDDING.model
DEFAULT_TOP_K = max(1, int(os.environ.get("EXTRACTION_RAG_TOP_K", "3")))


def _embedding(text: str) -> list[float]:
    """One local embedding (shared implementation, endpoint from agent_llm)."""
    return _shared_embed(text)


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def build_index(
    data_dir: str | Path,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    knowledge_path: str | Path | None = None,
) -> Path:
    """Embed procedural knowledge and Kaggle examples into a reusable index."""
    data_dir = Path(data_dir)
    index_path = Path(index_path)
    records: list[dict[str, Any]] = []
    if knowledge_path:
        knowledge_file = Path(knowledge_path)
        if knowledge_file.exists():
            for line in knowledge_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    record = json.loads(line)
                    record["embedding"] = _embedding(record["text"])
                    records.append(record)
    for path in sorted(data_dir.glob("*.pdf")):
        chunks = _load_pdf(path)
        first_page = chunks[0].text if chunks else ""
        if not first_page:
            continue
        records.append({
            "id": f"kaggle:{path.name}",
            "source": str(path),
            "name": path.name,
            "knowledge_type": "kaggle_example",
            "contract_type": "unclassified",
            "text": first_page[:12000],
            "embedding": _embedding(first_page),
        })
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps({"model": DEFAULT_EMBEDDING_MODEL, "records": records}, separators=(",", ":")), encoding="utf-8")
    add_hybrid_records(
        [{key: value for key, value in record.items() if key != "embedding"} for record in records],
        os.environ.get("EXTRACTION_RAG_DB", str(DEFAULT_HYBRID_DB)),
    )
    return index_path


def retrieve_vector_profile(source_uri: str, first_page_text: str, index_path: str | Path = DEFAULT_INDEX_PATH) -> dict[str, Any] | None:
    """Retrieve procedural knowledge and relevant Kaggle examples."""
    path = Path(index_path)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    query = _embedding(first_page_text)
    ranked = sorted(((_cosine(query, record["embedding"]), record) for record in payload.get("records", [])), key=lambda item: item[0], reverse=True)[:DEFAULT_TOP_K]
    if not ranked:
        return None
    score, best = ranked[0]
    procedural = [record for record in ranked if record[1].get("knowledge_type") == "contract_profile"]
    best_procedure = procedural[0][1] if procedural else None
    contract_type = best_procedure.get("contract_type", "unclassified") if best_procedure else best["contract_type"]
    return {
        **UNCLASSIFIED,
        "id": contract_type,
        "name": best_procedure.get("name", contract_type) if best_procedure else contract_type,
        "score": round(score, 4),
        "retrieval_mode": "ollama_vector_knowledge",
        "vector_enabled": True,
        "required_fields": best_procedure.get("required_fields", UNCLASSIFIED["required_fields"]) if best_procedure else UNCLASSIFIED["required_fields"],
        "recommended_fields": best_procedure.get("recommended_fields", UNCLASSIFIED["recommended_fields"]) if best_procedure else UNCLASSIFIED["recommended_fields"],
        "guidance": best_procedure.get("guidance", "") if best_procedure else "",
        "nearest_examples": [{"name": record.get("name", record.get("id", "unknown")), "knowledge_type": record.get("knowledge_type"), "score": round(item_score, 4)} for item_score, record in ranked],
    }


async def retrieve_profile_with_vectors(source_uri: str, sample_text: str) -> dict[str, Any]:
    """Use the local vector index without blocking LangGraph's event loop.

    ``sample_text`` should be the first few non-empty pages joined, not just
    page one - a cover sheet or table of contents is a poor retrieval query.
    """
    if os.environ.get("EXTRACTION_RAG_ENABLED", "0") != "1":
        logger.debug("RAG disabled source=%s", source_uri)
        return {**UNCLASSIFIED, "vector_enabled": False, "retrieval_mode": "rag_unavailable", "nearest_examples": [], "retrieval_error": "EXTRACTION_RAG_ENABLED is not set to 1"}
    try:
        result = await asyncio.to_thread(
            hybrid_retrieve,
            sample_text,
            os.environ.get("EXTRACTION_RAG_DB", str(DEFAULT_HYBRID_DB)),
        )
        if result:
            logger.debug("hybrid RAG result source=%s mode=%s id=%s score=%s", source_uri, result.get("retrieval_mode"), result.get("id"), result.get("score"))
            return {
                **UNCLASSIFIED,
                "id": result.get("contract_type", "unclassified"),
                "name": result.get("name", result.get("contract_type", "unclassified")),
                "score": result.get("score", 0.0),
                "required_fields": result.get("required_fields", UNCLASSIFIED["required_fields"]),
                "recommended_fields": result.get("recommended_fields", UNCLASSIFIED["recommended_fields"]),
                "guidance": result.get("guidance", ""),
                "retrieval_mode": result.get("retrieval_mode", "hybrid_fts_vector"),
                "vector_enabled": True,
                "nearest_examples": result.get("nearest_examples", []),
            }
    except Exception as exc:
        return {**UNCLASSIFIED, "vector_enabled": False, "retrieval_mode": "rag_fallback", "nearest_examples": [], "retrieval_error": type(exc).__name__}
    return {**UNCLASSIFIED, "vector_enabled": False, "retrieval_mode": "rag_fallback", "nearest_examples": []}
