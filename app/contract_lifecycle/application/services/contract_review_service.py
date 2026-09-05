"""ContractReviewService: versioned drafting and review."""
from __future__ import annotations

from ...domain.aggregates import Contract
from ..commands import RecordReviewCommand, SubmitForReviewCommand
from .application_service import ApplicationService


class ContractReviewService(ApplicationService):
    def handle_submit_for_review(self, command: SubmitForReviewCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.submit_for_review(actor=command.actor, correlation_id=command.correlation_id)
        self._finish(contract, command)
        return contract

    def handle_record_review(self, command: RecordReviewCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.add_review(
            reviewer_id=command.reviewer_id,
            review_type=command.review_type,
            decision=command.decision,
            actor=command.actor,
            correlation_id=command.correlation_id,
            comments=command.comments,
            conditions=command.conditions,
        )
        self._finish(contract, command)
        return contract
