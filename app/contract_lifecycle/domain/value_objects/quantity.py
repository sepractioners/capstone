"""Quantity value object."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        if self.value < 0:
            raise InvalidValueError("Quantity value must not be negative")
        if not self.unit:
            raise InvalidValueError("Quantity requires a unit")
