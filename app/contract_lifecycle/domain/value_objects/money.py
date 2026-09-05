"""Money value object."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from ..exceptions import InvalidValueError

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise InvalidValueError("Money amount must not be negative")
        if not _CURRENCY_RE.match(self.currency):
            raise InvalidValueError(f"Invalid currency code: {self.currency!r}")

    def __add__(self, other: "Money") -> "Money":
        if other.currency != self.currency:
            raise InvalidValueError("Cannot add Money in different currencies")
        return Money(self.amount + other.amount, self.currency)
