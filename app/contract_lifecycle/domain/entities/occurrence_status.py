"""OccurrenceStatus enum."""
from __future__ import annotations

from enum import Enum


class OccurrenceStatus(str, Enum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    ACCEPTED = "accepted"
    OVERDUE = "overdue"
    BREACHED = "breached"
