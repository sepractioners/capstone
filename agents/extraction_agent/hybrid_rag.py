"""Hybrid lexical plus vector retrieval for contract knowledge.

The SQLite FTS5 index preserves exact legal terms and entities while the
embedding column supports semantic matches. Source documents remain evidence;
procedural records and curated dataset examples are retrieval knowledge.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable

from agent_llm import EMBEDDING as _EMBEDDING
from agent_llm.embeddings import embed as _shared_embed

DEFAULT_DB_PATH = Path(os.environ.get("EXTRACTION_RAG_DB", "synthetic_data_loader/rag_knowledge.sqlite3"))
EMBEDDING_URL = _EMBEDDING.url
EMBEDDING_MODEL = _EMBEDDING.model
TOP_K = max(1, int(os.environ.get("EXTRACTION_RAG_TOP_K", "5")))
VECTOR_BACKEND = os.environ.get("EXTRACTION_RAG_VECTOR_BACKEND", "sqlite")


def embed(text: str) -> list[float]:
    """One local embedding (shared implementation, endpoint from agent_llm)."""
    return _shared_embed(text)


def cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    return sum(a * b for a, b in zip(left, right)) / denominator if denominator else 0.0


def initialize(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Create the hybrid SQLite schema with FTS5 and vector metadata."""
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE IF NOT EXISTS rag_documents (id TEXT PRIMARY KEY, dataset TEXT, knowledge_type TEXT, contract_type TEXT, text TEXT NOT NULL, metadata TEXT NOT NULL, embedding TEXT NOT NULL)")
    connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS rag_text USING fts5(id UNINDEXED, text, dataset, knowledge_type, contract_type)")
    connection.commit()
    return connection


def add_records(records: Iterable[dict[str, Any]], db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Insert procedural knowledge or dataset examples into both indexes."""
    connection = initialize(db_path)
    try:
        for record in records:
            document_id = record["id"]
            text = record["text"]
            dataset = record.get("dataset", "internal")
            knowledge_type = record.get("knowledge_type", "example")
            contract_type = record.get("contract_type", "unclassified")
            connection.execute("INSERT OR REPLACE INTO rag_documents VALUES (?, ?, ?, ?, ?, ?, ?)", (document_id, dataset, knowledge_type, contract_type, text, json.dumps(record), json.dumps(embed(text))))
            connection.execute("DELETE FROM rag_text WHERE id = ?", (document_id,))
            connection.execute("INSERT INTO rag_text(id, text, dataset, knowledge_type, contract_type) VALUES (?, ?, ?, ?, ?)", (document_id, text, dataset, knowledge_type, contract_type))
        connection.commit()
    finally:
        connection.close()


def retrieve(query: str, db_path: str | Path = DEFAULT_DB_PATH, top_k: int = TOP_K) -> dict[str, Any] | None:
    """Merge exact FTS matches and semantic vector matches into one result."""
    path = Path(db_path)
    if not path.exists():
        return None
    connection = initialize(path)
    try:
        lexical: dict[str, float] = {}
        tokens = [token for token in query.replace("-", " ").split() if len(token) > 2]
        if tokens:
            expression = " OR ".join(f'"{token.replace(chr(34), "")}"' for token in tokens)
            for rank, row in enumerate(connection.execute("SELECT id FROM rag_text WHERE rag_text MATCH ? LIMIT ?", (expression, top_k * 4))):
                lexical[row[0]] = 1.0 / (rank + 1)
        semantic_scores: dict[str, float] = {}
        query_embedding = embed(query)
        if VECTOR_BACKEND == "faiss":
            from .faiss_backend import DEFAULT_INDEX_PATH, search

            if Path(DEFAULT_INDEX_PATH).exists():
                semantic_scores.update(dict(search(query_embedding, DEFAULT_INDEX_PATH, top_k * 4)))
        if not semantic_scores:
            rows = connection.execute("SELECT id, embedding FROM rag_documents").fetchall()
            for document_id, vector_json in rows:
                semantic_scores[document_id] = cosine(query_embedding, json.loads(vector_json))
        ids = set(lexical) | {item[0] for item in sorted(semantic_scores.items(), key=lambda item: item[1], reverse=True)[: top_k * 4]}
        ranked = sorted(((0.55 * semantic_scores.get(document_id, 0.0) + 0.45 * lexical.get(document_id, 0.0), document_id) for document_id in ids), reverse=True)[:top_k]
        if not ranked:
            return None
        score, document_id = ranked[0]
        row = connection.execute("SELECT metadata FROM rag_documents WHERE id = ?", (document_id,)).fetchone()
        result = json.loads(row[0])
        result.update({"score": round(score, 4), "retrieval_mode": f"hybrid_fts_{VECTOR_BACKEND}", "vector_enabled": True, "lexical_match": document_id in lexical, "nearest_examples": [{"id": item_id, "score": round(item_score, 4)} for item_score, item_id in ranked]})
        return result
    finally:
        connection.close()
