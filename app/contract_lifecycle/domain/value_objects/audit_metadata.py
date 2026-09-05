"""AuditMetadata value object: a replaced-wholesale snapshot, not a mutable log."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class AuditMetadata:
    created_by: str
    created_at: datetime
    updated_by: Optional[str] = None
    updated_at: Optional[datetime] = None

    def touched_by(self, actor_id: str, at: datetime) -> "AuditMetadata":
        return AuditMetadata(
            created_by=self.created_by,
            created_at=self.created_at,
            updated_by=actor_id,
            updated_at=at,
        )
