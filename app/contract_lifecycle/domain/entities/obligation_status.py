"""ObligationStatus enum."""
from __future__ import annotations

from enum import Enum


class ObligationStatus(str, Enum):
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    BREACHED = "breached"
    WAIVED = "waived"
    CANCELLED = "cancelled"
