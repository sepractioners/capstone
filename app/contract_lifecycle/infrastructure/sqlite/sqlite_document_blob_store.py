"""SqliteDocumentBlobStore: the SQLite implementation of DocumentBlobStore.

`put` is idempotent by content_hash (INSERT OR IGNORE) - re-ingesting the
same document is expected (see ingest_contract_handler's idempotency
check) and should not error trying to store the same bytes twice.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from ...domain.repositories import DocumentBlobStore, StoredDocument
from .connection_factory import SqliteConnectionFactory
from .document_blob_schema import DocumentBlobSchema


class SqliteDocumentBlobStore(DocumentBlobStore):
    def __init__(self, connection_factory: SqliteConnectionFactory, schema: Optional[DocumentBlobSchema] = None) -> None:
        self._connections = connection_factory
        connection = self._connections.connect()
        try:
            (schema or DocumentBlobSchema()).create_all(connection)
        finally:
            connection.close()

    def put(
        self,
        content_hash: str,
        media_type: str,
        data: bytes,
        original_filename: Optional[str] = None,
    ) -> None:
        connection = self._connections.connect()
        try:
            connection.execute(
                """
                INSERT OR IGNORE INTO document_blobs
                    (content_hash, media_type, original_filename, data, stored_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (content_hash, media_type, original_filename, data, datetime.now(timezone.utc).isoformat()),
            )
            connection.commit()
        finally:
            connection.close()

    def get(self, content_hash: str) -> Optional[StoredDocument]:
        connection = self._connections.connect()
        try:
            row = connection.execute(
                "SELECT media_type, original_filename, data FROM document_blobs WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        return StoredDocument(
            content_hash=content_hash,
            media_type=row["media_type"],
            data=bytes(row["data"]),
            original_filename=row["original_filename"],
        )
