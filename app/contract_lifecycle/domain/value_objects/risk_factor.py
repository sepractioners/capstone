"""RiskFactor value object."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class RiskFactor:
    name: str
    weight: Decimal
    score: Decimal

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidValueError("RiskFactor requires a name")
        if self.weight < 0:
            raise InvalidValueError("RiskFactor weight must not be negative")
