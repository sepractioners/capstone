"""Format detection and loading.

PDF -> one text chunk per page (needs LLM extraction downstream).
JSON/CSV -> one already-structured record per chunk (no LLM needed - the
extraction node passes these straight through to a ContractCandidate).
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


def content_hash_for(payload: bytes) -> str:
    """Return the SHA-256 hex digest for raw source bytes."""
    return hashlib.sha256(payload).hexdigest()


_MEDIA_TYPES = {"pdf": "application/pdf", "json": "application/json", "csv": "text/csv"}


def media_type_for_format(fmt: str) -> str:
    """Map a supported format name to its MIME type."""
    return _MEDIA_TYPES.get(fmt, "application/octet-stream")


@dataclass
class LoadedChunk:
    """One page or structured record produced by a source loader."""

    index: int
    metadata: dict[str, Any] = field(default_factory=dict)
    text: Optional[str] = None
    structured: Optional[dict[str, Any]] = None


@dataclass
class LoadedDocument:
    """Loaded source bytes plus the chunks used by the extraction graph."""

    format: str
    file_path: str
    file_content_hash: str
    file_bytes: bytes
    chunks: list[LoadedChunk]


class UnsupportedFormatError(ValueError):
    """Raised when a source file extension is not supported."""

    pass


def load(file_path: str) -> LoadedDocument:
    """Read and dispatch a PDF, JSON, or CSV file by its extension."""
    path = Path(file_path)
    suffix = path.suffix.lower().lstrip(".")
    raw_bytes = path.read_bytes()
    file_hash = content_hash_for(raw_bytes)

    if suffix == "pdf":
        chunks = _load_pdf(path)
    elif suffix == "json":
        chunks = _load_json(raw_bytes)
    elif suffix == "csv":
        chunks = _load_csv(raw_bytes)
    else:
        raise UnsupportedFormatError(f"Unsupported file format: {suffix!r} ({file_path})")

    return LoadedDocument(
        format=suffix, file_path=str(path), file_content_hash=file_hash, file_bytes=raw_bytes, chunks=chunks
    )


def _load_pdf(path: Path) -> list[LoadedChunk]:
    """Load a PDF as one text chunk per page using LlamaIndex."""
    from llama_index.readers.file import PDFReader

    reader = PDFReader(return_full_document=False)
    documents = reader.load_data(path)
    return [
        LoadedChunk(index=i, metadata=dict(doc.metadata), text=doc.text)
        for i, doc in enumerate(documents)
    ]


def _load_json(raw_bytes: bytes) -> list[LoadedChunk]:
    """Decode JSON as one record, or one chunk for each list element."""
    data = json.loads(raw_bytes.decode("utf-8"))
    records = data if isinstance(data, list) else [data]
    return [LoadedChunk(index=i, structured=record) for i, record in enumerate(records)]


def _load_csv(raw_bytes: bytes) -> list[LoadedChunk]:
    """Decode UTF-8 CSV rows as structured record chunks."""
    text = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    return [LoadedChunk(index=i, structured=dict(row)) for i, row in enumerate(reader)]
