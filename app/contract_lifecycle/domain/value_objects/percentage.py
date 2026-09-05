"""Percentage value object."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class Percentage:
    value: Decimal

    def __post_init__(self) -> None:
        if not (Decimal("0") <= self.value <= Decimal("100")):
            raise InvalidValueError("Percentage must be between 0 and 100")
