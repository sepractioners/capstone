"""AmountThresholdApprovalPolicy: a concrete ApprovalPolicy.

Requires an approval from `threshold.required_role` whenever the
contract's commercial value meets or exceeds `threshold.max_amount`. One
of potentially many ApprovalPolicy implementations that can be plugged
into ApprovalPolicyEvaluator.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..entities import ApprovalDecision
from ..value_objects import ApprovalThreshold
from .policy_result import PolicyResult

if TYPE_CHECKING:
    from ..aggregates import Contract


class AmountThresholdApprovalPolicy:
    POLICY_VERSION = "1.0"

    def __init__(self, threshold: ApprovalThreshold) -> None:
        self._threshold = threshold

    def evaluate(self, contract: "Contract") -> PolicyResult:
        total_value = contract.commercial_terms.total_value
        if total_value is None or total_value.amount < self._threshold.max_amount.amount:
            return PolicyResult(
                rule="amount-threshold",
                decision=True,
                policy_version=self.POLICY_VERSION,
                inputs={"total_value": total_value},
                explanation="Contract value is below the threshold; no extra approval required.",
            )

        has_required_approval = any(
            a.decision == ApprovalDecision.APPROVED
            and a.authority_basis == self._threshold.required_role
            for a in contract.approvals
        )
        return PolicyResult(
            rule="amount-threshold",
            decision=has_required_approval,
            policy_version=self.POLICY_VERSION,
            inputs={
                "total_value": total_value,
                "required_role": self._threshold.required_role,
            },
            explanation=(
                "Required approval present"
                if has_required_approval
                else f"Requires approval from {self._threshold.required_role}"
            ),
        )
