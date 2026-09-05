"""ContractExecutionService: signature package creation, execution
confirmation, activation, and the amendments that produce new executed
versions.

Depends on the AuthorityChecker abstraction to verify the actor may sign
or amend before invoking the aggregate.
"""
from __future__ import annotations

from ...domain.aggregates import Contract
from ...domain.entities import Amendment
from ...domain.exceptions import AuthorizationError
from ...domain.services import AuthorityChecker
from ..commands import (
    ActivateContractCommand,
    CreateAmendmentCommand,
    ExecuteAmendmentCommand,
    MarkExecutedCommand,
    RecordSignatureCommand,
    RecordSignatureFailureCommand,
    RequestSignatureCommand,
)
from .application_service import ApplicationService


class ContractExecutionService(ApplicationService):
    def __init__(self, repository, publisher, authority_checker: AuthorityChecker, seen_commands=None) -> None:
        super().__init__(repository, publisher, seen_commands)
        self._authority_checker = authority_checker

    def handle_request_signature(self, command: RequestSignatureCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.request_signature(
            package_id=command.package_id,
            signers=command.signers,
            actor=command.actor,
            correlation_id=command.correlation_id,
            provider_reference=command.provider_reference,
            deadline=command.deadline,
        )
        self._finish(contract, command)
        return contract

    def handle_record_signature(self, command: RecordSignatureCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract
        if not self._authority_checker.can_sign(command.actor, contract):
            raise AuthorizationError(f"{command.actor.actor_id} is not authorized to sign this contract")

        contract.record_signer_signed(
            package_id=command.package_id,
            party_id=command.party_id,
            signed_at=command.signed_at,
        )
        self._finish(contract, command)
        return contract

    def handle_record_signature_failure(self, command: RecordSignatureFailureCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.record_signature_failure(
            package_id=command.package_id,
            reason=command.reason,
            actor=command.actor,
            correlation_id=command.correlation_id,
        )
        self._finish(contract, command)
        return contract

    def handle_mark_executed(self, command: MarkExecutedCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.mark_executed(
            package_id=command.package_id, actor=command.actor, correlation_id=command.correlation_id
        )
        self._finish(contract, command)
        return contract

    def handle_activate(self, command: ActivateContractCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.activate_contract(
            effective_date=command.effective_date,
            actor=command.actor,
            correlation_id=command.correlation_id,
        )
        self._finish(contract, command)
        return contract

    def handle_create_amendment(self, command: CreateAmendmentCommand) -> Amendment:
        contract = self._repository.get(command.contract_id)
        if not self._authority_checker.can_amend(command.actor, contract):
            raise AuthorizationError(f"{command.actor.actor_id} is not authorized to amend this contract")

        amendment = contract.create_amendment(
            amendment_id=command.amendment_id,
            affected_clause_ids=command.affected_clause_ids,
            effective_date=command.effective_date,
            actor=command.actor,
            correlation_id=command.correlation_id,
        )
        self._repository.save(contract)
        return amendment

    def handle_execute_amendment(self, command: ExecuteAmendmentCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.execute_amendment(
            amendment_id=command.amendment_id,
            document=command.document,
            author_id=command.author_id,
            actor=command.actor,
            correlation_id=command.correlation_id,
        )
        self._finish(contract, command)
        return contract
