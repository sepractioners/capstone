"""ApplicationService: shared plumbing for command handlers.

Application services depend only on the domain's repository and publisher
abstractions (dependency inversion) - never on a concrete SQLite class.
This base class owns the idempotency check and the
persist-then-publish sequence described in the DDD document's command
flow, so each concrete service only has to invoke aggregate behavior.
"""
from __future__ import annotations

from ...domain.events import DomainEvent
from ...domain.repositories import ContractRepository, DomainEventPublisher
from ..commands import Command
from ..idempotency import InMemorySeenCommandStore, SeenCommandStore


class ApplicationService:
    def __init__(
        self,
        repository: ContractRepository,
        publisher: DomainEventPublisher,
        seen_commands: SeenCommandStore | None = None,
    ) -> None:
        self._repository = repository
        self._publisher = publisher
        self._seen_commands = seen_commands or InMemorySeenCommandStore()

    def _already_handled(self, command: Command) -> bool:
        return self._seen_commands.already_processed(command.idempotency_key)

    def _finish(self, contract, command: Command) -> list[DomainEvent]:
        events = self._repository.save(contract)
        self._publisher.publish(events)
        self._seen_commands.mark_processed(command.idempotency_key)
        return events
