"""RenewalManagementService: renewal window detection and initiation.

Depends on the RenewalEvaluator domain service to decide whether a
renewal window is open, rather than embedding that date arithmetic here.
"""
from __future__ import annotations

from datetime import date

from ...domain.aggregates import Contract
from ...domain.services import RenewalEvaluator
from ...domain.value_objects import Actor, ContractId


class RenewalManagementService:
    def __init__(self, repository, publisher, evaluator: RenewalEvaluator) -> None:
        self._repository = repository
        self._publisher = publisher
        self._evaluator = evaluator

    def evaluate_and_initiate(
        self, contract_id: ContractId, today: date, actor: Actor, correlation_id: str
    ) -> Contract:
        contract = self._repository.get(contract_id)
        if self._evaluator.is_window_open(contract, today):
            contract.initiate_renewal(actor=actor, correlation_id=correlation_id)
            events = self._repository.save(contract)
            self._publisher.publish(events)
        return contract

    def complete_renewal(self, contract_id: ContractId, actor: Actor, correlation_id: str) -> Contract:
        contract = self._repository.get(contract_id)
        contract.complete_renewal(actor=actor, correlation_id=correlation_id)
        events = self._repository.save(contract)
        self._publisher.publish(events)
        return contract
