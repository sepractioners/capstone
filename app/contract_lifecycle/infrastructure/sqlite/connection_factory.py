"""SqliteConnectionFactory: the single place that knows how to open a
connection to the contract lifecycle SQLite database."""
from __future__ import annotations

import sqlite3


class SqliteConnectionFactory:
    def __init__(self, database_path: str) -> None:
        self._database_path = database_path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.row_factory = sqlite3.Row
        return connection
