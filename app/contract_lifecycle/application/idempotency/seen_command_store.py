"""SeenCommandStore: tracks which idempotency keys have already been
processed, so a retried command is not applied twice.

A Protocol so the in-memory default can be swapped for a persistent store
(a table, Redis, ...) without any application service changing.
"""
from __future__ import annotations

from typing import Protocol


class SeenCommandStore(Protocol):
    def already_processed(self, idempotency_key: str) -> bool:
        ...

    def mark_processed(self, idempotency_key: str) -> None:
        ...
