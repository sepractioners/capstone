"""DomainEventPublisher: where committed domain events go after save.

An abstraction so the application layer never depends on a concrete
message bus, outbox table, or webhook dispatcher directly (dependency
inversion).
"""
from __future__ import annotations

from typing import Protocol, Sequence

from ..events import DomainEvent


class DomainEventPublisher(Protocol):
    def publish(self, events: Sequence[DomainEvent]) -> None:
        ...
