"""DueDate value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class DueDate:
    value: date
    grace_period_days: int = 0

    def __post_init__(self) -> None:
        if self.grace_period_days < 0:
            raise InvalidValueError("grace_period_days must not be negative")

    @property
    def final_due_date(self) -> date:
        return self.value + timedelta(days=self.grace_period_days)
