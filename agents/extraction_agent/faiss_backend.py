"""Optional FAISS semantic index for the hybrid retrieval store."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

DEFAULT_INDEX_PATH = Path(os.environ.get("EXTRACTION_RAG_FAISS_INDEX", "synthetic_data_loader/rag_knowledge.faiss"))
DEFAULT_METADATA_PATH = DEFAULT_INDEX_PATH.with_suffix(".metadata.json")


def _load_faiss():
    """Load FAISS lazily so lexical retrieval works without FAISS installed."""
    import faiss

    return faiss


def build_index(db_path: str | Path, index_path: str | Path = DEFAULT_INDEX_PATH) -> Path:
    """Build a normalized inner-product FAISS index from SQLite embeddings."""
    faiss = _load_faiss()
    import numpy as np

    connection = sqlite3.connect(db_path)
    rows = connection.execute("SELECT id, embedding FROM rag_documents ORDER BY id").fetchall()
    connection.close()
    if not rows:
        raise ValueError(f"No RAG embeddings found in {db_path}")
    vectors = np.asarray([json.loads(row[1]) for row in rows], dtype="float32")
    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    index_path = Path(index_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, str(index_path))
    index_path.with_suffix(".metadata.json").write_text(
        json.dumps({"ids": [row[0] for row in rows], "dimension": vectors.shape[1]}),
        encoding="utf-8",
    )
    return index_path


def search(query_vector: list[float], index_path: str | Path = DEFAULT_INDEX_PATH, top_k: int = 5) -> list[tuple[str, float]]:
    """Return document ids and cosine-equivalent scores from FAISS."""
    faiss = _load_faiss()
    import numpy as np

    index_path = Path(index_path)
    index = faiss.read_index(str(index_path))
    metadata = json.loads(index_path.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    vector = np.asarray([query_vector], dtype="float32")
    faiss.normalize_L2(vector)
    scores, positions = index.search(vector, min(top_k, index.ntotal))
    return [(metadata["ids"][position], float(score)) for score, position in zip(scores[0], positions[0]) if position >= 0]
