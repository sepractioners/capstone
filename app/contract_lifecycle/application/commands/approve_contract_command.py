"""ApproveContractCommand."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...domain.value_objects import ContractId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class ApproveContractCommand(Command):
    contract_id: ContractId
    approver_id: str
    authority_basis: str
    scope: str
    conditions: tuple[str, ...] = ()
    expires_at: Optional[datetime] = None
