"""StartTerminationCommand."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.value_objects import ContractId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class StartTerminationCommand(Command):
    contract_id: ContractId
    reason: str
    requested_effective_date: date
