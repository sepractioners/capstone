"""Approval entity."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..value_objects import VersionNumber
from .approval_decision import ApprovalDecision


@dataclass
class Approval:
    """An approval decision made under a defined approval policy."""

    approver_id: str
    authority_basis: str
    version_approved: VersionNumber
    scope: str
    decision: ApprovalDecision = ApprovalDecision.PENDING
    conditions: tuple[str, ...] = field(default_factory=tuple)
    decided_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None

    def is_valid_for(self, version: VersionNumber, at: datetime) -> bool:
        if self.decision != ApprovalDecision.APPROVED:
            return False
        if self.version_approved != version:
            return False
        if self.expires_at is not None and at > self.expires_at:
            return False
        return True
