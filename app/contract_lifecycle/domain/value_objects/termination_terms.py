"""TerminationTerms value object."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .notice_period import NoticePeriod


@dataclass(frozen=True)
class TerminationTerms:
    notice_period: Optional[NoticePeriod] = None
    cure_period_days: int = 0
    termination_for_convenience: bool = False
