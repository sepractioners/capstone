"""Build the local vector index from all downloaded Kaggle PDFs.

Usage:
    python -m extraction_agent.build_rag_index
"""
from __future__ import annotations

import os
from pathlib import Path

from .vector_rag import DEFAULT_INDEX_PATH, build_index
from .faiss_backend import build_index as build_faiss_index


if __name__ == "__main__":
    data_dir = Path(os.environ.get("EXTRACTION_RAG_DATA_DIR", "sythetic_data_loader/data/cuad_subset"))
    knowledge_path = Path(os.environ.get("EXTRACTION_RAG_KNOWLEDGE_PATH", Path(__file__).parent / "rag_knowledge.jsonl"))
    print(build_index(data_dir, DEFAULT_INDEX_PATH, knowledge_path))
    if os.environ.get("EXTRACTION_RAG_BUILD_FAISS", "0") == "1":
        print(build_faiss_index(os.environ.get("EXTRACTION_RAG_DB", "sythetic_data_loader/rag_knowledge.sqlite3")))
