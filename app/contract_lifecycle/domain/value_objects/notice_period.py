"""NoticePeriod value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class NoticePeriod:
    days: int

    def __post_init__(self) -> None:
        if self.days <= 0:
            raise InvalidValueError("NoticePeriod must be a positive number of days")
