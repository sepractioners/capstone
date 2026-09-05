"""ContractReview entity."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..value_objects import VersionNumber
from .review_decision import ReviewDecision


@dataclass
class ContractReview:
    """A review assignment or decision by a person or organizational role."""

    reviewer_id: str
    review_type: str
    version_reviewed: VersionNumber
    decision: ReviewDecision = ReviewDecision.PENDING
    comments: Optional[str] = None
    conditions: tuple[str, ...] = field(default_factory=tuple)
    decided_at: Optional[datetime] = None
