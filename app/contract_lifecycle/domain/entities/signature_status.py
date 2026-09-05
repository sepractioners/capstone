"""SignatureStatus enum."""
from __future__ import annotations

from enum import Enum


class SignatureStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    PARTIALLY_SIGNED = "partially_signed"
    COMPLETED = "completed"
    FAILED = "failed"
    VOIDED = "voided"
