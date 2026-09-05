"""PolicyResult value object returned by policy-evaluating domain services."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PolicyResult:
    """An explainable policy outcome: the rule, inputs, decision, and the
    policy version used - never a hidden side effect."""

    rule: str
    decision: bool
    policy_version: str
    inputs: dict[str, Any] = field(default_factory=dict)
    explanation: str = ""
