"""TerminationService: termination and archival workflows.

Depends on the AuthorityChecker abstraction to verify the actor may
terminate before invoking the aggregate.
"""
from __future__ import annotations

from ...domain.aggregates import Contract
from ...domain.exceptions import AuthorizationError
from ...domain.services import AuthorityChecker
from ..commands import ArchiveContractCommand, StartTerminationCommand, TerminateContractCommand
from .application_service import ApplicationService


class TerminationService(ApplicationService):
    def __init__(self, repository, publisher, authority_checker: AuthorityChecker, seen_commands=None) -> None:
        super().__init__(repository, publisher, seen_commands)
        self._authority_checker = authority_checker

    def handle_start_termination(self, command: StartTerminationCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract
        if not self._authority_checker.can_terminate(command.actor, contract):
            raise AuthorizationError(
                f"{command.actor.actor_id} is not authorized to terminate this contract"
            )

        contract.start_termination(
            reason=command.reason,
            requested_effective_date=command.requested_effective_date,
            actor=command.actor,
            correlation_id=command.correlation_id,
        )
        self._finish(contract, command)
        return contract

    def handle_terminate(self, command: TerminateContractCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.terminate_contract(
            effective_date=command.effective_date,
            actor=command.actor,
            correlation_id=command.correlation_id,
        )
        self._finish(contract, command)
        return contract

    def handle_archive(self, command: ArchiveContractCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.archive_contract(actor=command.actor, correlation_id=command.correlation_id)
        self._finish(contract, command)
        return contract
