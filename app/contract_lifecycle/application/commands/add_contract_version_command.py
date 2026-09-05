"""AddContractVersionCommand: supporting command for drafting a new version."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...domain.value_objects import ContractId, DocumentReference
from .command import Command


@dataclass(frozen=True, kw_only=True)
class AddContractVersionCommand(Command):
    contract_id: ContractId
    document: DocumentReference
    author_id: str
    change_summary: Optional[str] = None
