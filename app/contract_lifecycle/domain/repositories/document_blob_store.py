"""DocumentBlobStore: persists the original source bytes (a PDF, or a
JSON/CSV record's raw content) that a Contract's DocumentReference points
to, keyed by the same content_hash already used for idempotency.

Without this, a DocumentReference.uri only points at wherever the source
happened to live at ingestion time (a download cache, a temp file) - not
durable, and not fetchable later for verifying extraction quality against
the original. This port makes the original content itself part of what
gets persisted, addressed by content_hash rather than a location.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol


@dataclass(frozen=True)
class StoredDocument:
    content_hash: str
    media_type: str
    data: bytes
    original_filename: Optional[str] = None


class DocumentBlobStore(Protocol):
    def put(
        self,
        content_hash: str,
        media_type: str,
        data: bytes,
        original_filename: Optional[str] = None,
    ) -> None:
        ...

    def get(self, content_hash: str) -> Optional[StoredDocument]:
        ...
