"""VersionStatus enum."""
from __future__ import annotations

from enum import Enum


class VersionStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    EXECUTED = "executed"
    SUPERSEDED = "superseded"
