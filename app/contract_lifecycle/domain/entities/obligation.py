"""Obligation entity."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..exceptions import InvalidValueError
from ..value_objects import ClauseReference, DueDate, ObligationId, PartyId, RecurrenceRule
from .obligation_status import ObligationStatus


@dataclass
class Obligation:
    """An actionable commitment made by a party, derived from a contract term.

    Not a copy of the clause text - it retains a reference to its source
    clause when one exists.
    """

    obligation_id: ObligationId
    description: str
    responsible_party_id: PartyId
    owner_actor_id: str
    due_date_rule: DueDate
    source_clause: Optional[ClauseReference] = None
    recurrence: Optional[RecurrenceRule] = None
    evidence_requirements: tuple[str, ...] = field(default_factory=tuple)
    consequence_of_failure: Optional[str] = None
    status: ObligationStatus = ObligationStatus.ACTIVE

    def __post_init__(self) -> None:
        if not self.description:
            raise InvalidValueError("Obligation requires a description")
