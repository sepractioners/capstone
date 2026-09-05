"""ApprovalThreshold value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError
from .money import Money


@dataclass(frozen=True)
class ApprovalThreshold:
    max_amount: Money
    required_role: str

    def __post_init__(self) -> None:
        if not self.required_role:
            raise InvalidValueError("ApprovalThreshold requires a required_role")
