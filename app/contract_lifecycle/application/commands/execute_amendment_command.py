"""ExecuteAmendmentCommand."""
from __future__ import annotations

from dataclasses import dataclass

from ...domain.value_objects import ContractId, DocumentReference
from .command import Command


@dataclass(frozen=True, kw_only=True)
class ExecuteAmendmentCommand(Command):
    contract_id: ContractId
    amendment_id: str
    document: DocumentReference
    author_id: str
