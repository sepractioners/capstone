"""TerminateContractCommand."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ...domain.value_objects import ContractId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class TerminateContractCommand(Command):
    contract_id: ContractId
    effective_date: date
