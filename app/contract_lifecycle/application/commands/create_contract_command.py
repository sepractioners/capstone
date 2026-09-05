"""CreateContractCommand."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ...domain.entities import ContractParty
from ...domain.value_objects import ContractType
from .command import Command


@dataclass(frozen=True, kw_only=True)
class CreateContractCommand(Command):
    contract_type: ContractType
    title: str
    parties: list[ContractParty] = field(default_factory=list)
    contract_number: Optional[str] = None
