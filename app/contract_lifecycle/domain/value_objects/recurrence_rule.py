"""RecurrenceRule value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..exceptions import InvalidValueError
from .recurrence_frequency import RecurrenceFrequency


@dataclass(frozen=True)
class RecurrenceRule:
    frequency: RecurrenceFrequency
    interval: int = 1
    count: Optional[int] = None
    until: Optional[date] = None

    def __post_init__(self) -> None:
        if self.interval <= 0:
            raise InvalidValueError("RecurrenceRule interval must be positive")
        if self.count is not None and self.count <= 0:
            raise InvalidValueError("RecurrenceRule count must be positive if set")
