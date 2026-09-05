"""InMemorySeenCommandStore: the default SeenCommandStore.

Suitable for a single process. A multi-process deployment should provide
a persistent implementation of the same SeenCommandStore protocol.
"""
from __future__ import annotations


class InMemorySeenCommandStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def already_processed(self, idempotency_key: str) -> bool:
        return idempotency_key in self._seen

    def mark_processed(self, idempotency_key: str) -> None:
        self._seen.add(idempotency_key)
