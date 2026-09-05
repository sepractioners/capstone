"""ApprovalDecision enum."""
from __future__ import annotations

from enum import Enum


class ApprovalDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
