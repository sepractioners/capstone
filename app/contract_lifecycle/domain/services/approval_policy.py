"""ApprovalPolicy: the pluggable strategy evaluated by ApprovalPolicyEvaluator.

Defined as a Protocol so new approval policies (a higher-threshold policy
for a new contract type, a jurisdiction-specific policy, ...) can be added
by writing a new class, without modifying ApprovalPolicyEvaluator - the
open/closed principle applied to policy logic.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .policy_result import PolicyResult

if TYPE_CHECKING:
    from ..aggregates import Contract


class ApprovalPolicy(Protocol):
    def evaluate(self, contract: "Contract") -> PolicyResult:
        ...
