"""DateRange value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class DateRange:
    start: date
    end: Optional[date] = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise InvalidValueError("DateRange end must not precede start")

    def contains(self, on: date) -> bool:
        if on < self.start:
            return False
        return self.end is None or on <= self.end
