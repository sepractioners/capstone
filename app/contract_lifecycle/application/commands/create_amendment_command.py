"""CreateAmendmentCommand."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.value_objects import ContractId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class CreateAmendmentCommand(Command):
    contract_id: ContractId
    amendment_id: str
    affected_clause_ids: tuple[str, ...]
    effective_date: date
