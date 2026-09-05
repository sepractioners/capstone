"""ClauseStatus enum."""
from __future__ import annotations

from enum import Enum


class ClauseStatus(str, Enum):
    DRAFT = "draft"
    NEGOTIATED = "negotiated"
    APPROVED = "approved"
    IMMUTABLE = "immutable"
