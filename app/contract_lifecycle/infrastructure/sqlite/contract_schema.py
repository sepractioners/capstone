"""ContractSchema: creates the tables the SQLite adapter needs.

The aggregate is stored as a single JSON document per row (contracts
table), keyed by id, with a few columns pulled out for indexed lookups
(contract_number, lifecycle_status) and a row_version column used for
optimistic concurrency. row_version is a plain persistence counter
incremented on every save - independent of aggregate_version, which
counts domain events and would not change on a mutation that raises no
event (e.g. adding a party during intake). Domain events are appended to
a separate, append-only table so they can be replayed or published
independently of the aggregate snapshot.
"""
from __future__ import annotations

import sqlite3


class ContractSchema:
    def create_all(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS contracts (
                id TEXT PRIMARY KEY,
                contract_number TEXT NOT NULL UNIQUE,
                lifecycle_status TEXT NOT NULL,
                row_version INTEGER NOT NULL,
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_contracts_status
                ON contracts (lifecycle_status);

            CREATE TABLE IF NOT EXISTS domain_events (
                event_id TEXT PRIMARY KEY,
                aggregate_id TEXT NOT NULL,
                aggregate_version INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                data TEXT NOT NULL,
                published_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_domain_events_aggregate
                ON domain_events (aggregate_id, aggregate_version);
            """
        )
        connection.commit()
