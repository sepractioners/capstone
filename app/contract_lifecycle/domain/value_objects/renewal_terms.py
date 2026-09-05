"""RenewalTerms value object."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .notice_period import NoticePeriod


@dataclass(frozen=True)
class RenewalTerms:
    auto_renew: bool = False
    renewal_notice: Optional[NoticePeriod] = None
    renewal_term_length_months: Optional[int] = None
