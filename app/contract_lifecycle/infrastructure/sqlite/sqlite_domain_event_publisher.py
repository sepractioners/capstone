"""SqliteDomainEventPublisher: implements the domain's DomainEventPublisher
port on top of the same outbox table SqliteContractRepository writes to.

Marks each event's `published_at` column once its registered handlers have
run, so a crash between commit and publish leaves the event visible to a
future `republish_unpublished` sweep instead of silently dropping it.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Sequence

from ...domain.events import DomainEvent
from .connection_factory import SqliteConnectionFactory

EventHandler = Callable[[DomainEvent], None]


class SqliteDomainEventPublisher:
    def __init__(self, connection_factory: SqliteConnectionFactory) -> None:
        self._connections = connection_factory
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, events: Sequence[DomainEvent]) -> None:
        if not events:
            return
        connection = self._connections.connect()
        try:
            for event in events:
                for handler in self._handlers[type(event)]:
                    handler(event)
                connection.execute(
                    "UPDATE domain_events SET published_at = ? WHERE event_id = ?",
                    (datetime.now(timezone.utc).isoformat(), event.event_id),
                )
            connection.commit()
        finally:
            connection.close()
