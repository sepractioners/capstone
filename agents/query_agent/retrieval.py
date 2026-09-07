"""Evidence ranking for the query agent's reasoning loop.

Semantic ranking uses a local embedding model (the same one the extraction
hybrid store uses). If the embedding service is unavailable it falls back to
deterministic token-overlap ranking, so the agent still works offline.
"""
from __future__ import annotations

import logging
import math
from typing import Any

from agent_llm.embeddings import embed as _embed
from .config import config
from .evidence import EvidenceRecord, keyword_rank

logger = logging.getLogger(__name__)

POOL_MIN = 48  # lexical prefilter floor before semantic re-ranking


def embed(text: str) -> list[float]:
    """One local embedding (shared implementation, endpoint from agent_llm)."""
    return _embed(text, max_chars=8000, timeout=60.0)


def _cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(v * v for v in left)) * math.sqrt(sum(v * v for v in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def rank_with_scores(
    query: str,
    records: list[EvidenceRecord],
    k: int,
    cache: dict[str, list[float]] | None = None,
) -> tuple[list[tuple[float, EvidenceRecord]], dict[str, Any]]:
    """Rank evidence and return ``(score, record)`` pairs plus retrieval metadata.

    A cheap lexical prefilter bounds how many records are embedded, so an
    organization-wide question over hundreds of contracts does not fan out to
    thousands of embedding calls. ``cache`` (shared across calls within one
    request) avoids re-embedding the same text.
    """
    meta: dict[str, Any] = {"query": query, "corpus": len(records), "k": k}
    if not records:
        return [], {**meta, "mode": "empty"}
    cache = cache if cache is not None else {}
    pool_size = max(k * 8, POOL_MIN)
    prefiltered = len(records) > pool_size
    pool = keyword_rank(query, records, pool_size) if prefiltered else list(records)
    meta["prefiltered_to"] = len(pool)

    def _vec(text: str) -> list[float]:
        key = text[:2000]
        if key not in cache:
            cache[key] = embed(key)
        return cache[key]

    try:
        query_vector = _vec(query)
        scored = sorted(
            ((_cosine(query_vector, _vec(f"{r['label']} {r['evidence']}")), i, r) for i, r in enumerate(pool)),
            key=lambda item: (-item[0], item[1]),
        )
        top = [(round(score, 4), record) for score, _, record in scored[:k]]
        return top, {**meta, "mode": "embedding", "embedding_model": config.embedding_model}
    except Exception as exc:  # noqa: BLE001 - offline fallback is expected
        logger.debug("embedding rank unavailable (%s); using keyword fallback", type(exc).__name__)
        fallback = keyword_rank(query, records, k)
        return [(0.0, record) for record in fallback], {**meta, "mode": "keyword_fallback", "reason": type(exc).__name__}


def rank_evidence(
    query: str,
    records: list[EvidenceRecord],
    k: int,
    cache: dict[str, list[float]] | None = None,
) -> list[EvidenceRecord]:
    """Rank evidence records by semantic similarity, falling back to keywords."""
    ranked, _meta = rank_with_scores(query, records, k, cache)
    return [record for _score, record in ranked]
