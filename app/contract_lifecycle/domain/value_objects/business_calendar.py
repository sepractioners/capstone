"""BusinessCalendar value object."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class BusinessCalendar:
    """Minimal business-day calendar: weekends plus an explicit holiday set."""

    holidays: frozenset[date] = field(default_factory=frozenset)

    def is_business_day(self, on: date) -> bool:
        return on.weekday() < 5 and on not in self.holidays

    def add_business_days(self, start: date, days: int) -> date:
        if days < 0:
            raise InvalidValueError("days must not be negative")
        current = start
        remaining = days
        while remaining > 0:
            current += timedelta(days=1)
            if self.is_business_day(current):
                remaining -= 1
        return current
