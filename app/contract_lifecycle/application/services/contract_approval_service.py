"""ContractApprovalService: policy-driven approval with immutable decisions.

Depends on the AuthorityChecker abstraction to verify the actor may
approve before invoking the aggregate (dependency inversion): swapping in
a real delegated-authority checker requires no change here.
"""
from __future__ import annotations

from ...domain.aggregates import Contract
from ...domain.exceptions import AuthorizationError
from ...domain.services import AuthorityChecker
from ..commands import ApproveContractCommand, RejectContractCommand
from .application_service import ApplicationService


class ContractApprovalService(ApplicationService):
    def __init__(self, repository, publisher, authority_checker: AuthorityChecker, seen_commands=None) -> None:
        super().__init__(repository, publisher, seen_commands)
        self._authority_checker = authority_checker

    def handle_approve(self, command: ApproveContractCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract
        if not self._authority_checker.can_approve(command.actor, contract):
            raise AuthorizationError(f"{command.actor.actor_id} is not authorized to approve this contract")

        contract.approve_contract(
            approver_id=command.approver_id,
            authority_basis=command.authority_basis,
            scope=command.scope,
            actor=command.actor,
            correlation_id=command.correlation_id,
            conditions=command.conditions,
            expires_at=command.expires_at,
        )
        self._finish(contract, command)
        return contract

    def handle_reject(self, command: RejectContractCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.reject_contract(
            reason=command.reason, actor=command.actor, correlation_id=command.correlation_id
        )
        self._finish(contract, command)
        return contract
