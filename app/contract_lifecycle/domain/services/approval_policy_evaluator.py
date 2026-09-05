"""ApprovalPolicyEvaluator domain service.

Determines required approvals from contract facts and policy. It depends
only on the ApprovalPolicy abstraction (dependency inversion): callers
inject whichever concrete policies apply, and the evaluator does not
change when a new policy is introduced.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from .approval_policy import ApprovalPolicy
from .policy_result import PolicyResult

if TYPE_CHECKING:
    from ..aggregates import Contract


class ApprovalPolicyEvaluator:
    def __init__(self, policies: Iterable[ApprovalPolicy]) -> None:
        self._policies = list(policies)

    def evaluate(self, contract: "Contract") -> list[PolicyResult]:
        return [policy.evaluate(contract) for policy in self._policies]

    def all_satisfied(self, contract: "Contract") -> bool:
        return all(result.decision for result in self.evaluate(contract))
