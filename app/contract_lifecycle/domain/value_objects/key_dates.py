"""KeyDates value object: the dates that drive contract lifecycle timing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class KeyDates:
    effective_date: Optional[date] = None
    execution_date: Optional[date] = None
    expiration_date: Optional[date] = None
    renewal_deadline: Optional[date] = None
    termination_notice_deadline: Optional[date] = None
