"""ReviewDecision enum."""
from __future__ import annotations

from enum import Enum


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    REJECTED = "rejected"
