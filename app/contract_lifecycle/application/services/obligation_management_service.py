"""ObligationManagementService: obligation registration and scheduling.

The Contract aggregate owns the obligation *definition* (see docs); the
resulting schedule of occurrences is computed here via the
ObligationScheduler domain service and handed back to the caller, who is
responsible for persisting it into whatever store backs the Obligation
Plan aggregate for that contract - out of scope for this scaffold.
"""
from __future__ import annotations

from ...domain.aggregates import Contract
from ...domain.entities import ObligationOccurrence
from ...domain.services import ObligationScheduler
from ..commands import RegisterObligationCommand
from .application_service import ApplicationService


class ObligationManagementService(ApplicationService):
    def __init__(self, repository, publisher, scheduler: ObligationScheduler, seen_commands=None) -> None:
        super().__init__(repository, publisher, seen_commands)
        self._scheduler = scheduler

    def handle_register(self, command: RegisterObligationCommand) -> tuple[Contract, list[ObligationOccurrence]]:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract, []

        contract.register_obligation(
            obligation=command.obligation, actor=command.actor, correlation_id=command.correlation_id
        )
        self._finish(contract, command)
        occurrences = self._scheduler.schedule(command.obligation)
        return contract, occurrences
