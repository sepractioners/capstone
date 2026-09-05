"""RecordReviewCommand: supporting command for logging a review decision."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...domain.entities import ReviewDecision
from ...domain.value_objects import ContractId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class RecordReviewCommand(Command):
    contract_id: ContractId
    reviewer_id: str
    review_type: str
    decision: ReviewDecision
    comments: Optional[str] = None
    conditions: tuple[str, ...] = ()
