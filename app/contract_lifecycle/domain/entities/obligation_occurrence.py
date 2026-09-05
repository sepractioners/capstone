"""ObligationOccurrence entity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from ..value_objects import DocumentReference, ObligationId
from .occurrence_status import OccurrenceStatus


@dataclass
class ObligationOccurrence:
    """One scheduled instance of a recurring or milestone obligation."""

    obligation_id: ObligationId
    sequence: int
    due_date: date
    status: OccurrenceStatus = OccurrenceStatus.SCHEDULED
    completed_at: Optional[datetime] = None
    evidence_reference: Optional[DocumentReference] = None
    accepted_by_actor_id: Optional[str] = None
