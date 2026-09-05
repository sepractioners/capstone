"""DocumentBlobSchema: creates the table SqliteDocumentBlobStore needs.

Kept separate from ContractSchema (one class, one table, one
responsibility) even though both live in the same database file.
"""
from __future__ import annotations

import sqlite3


class DocumentBlobSchema:
    def create_all(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS document_blobs (
                content_hash TEXT PRIMARY KEY,
                media_type TEXT NOT NULL,
                original_filename TEXT,
                data BLOB NOT NULL,
                stored_at TEXT NOT NULL
            );
            """
        )
        connection.commit()
