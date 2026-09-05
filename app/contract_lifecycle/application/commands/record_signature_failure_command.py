"""RecordSignatureFailureCommand."""
from __future__ import annotations

from dataclasses import dataclass

from ...domain.value_objects import ContractId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class RecordSignatureFailureCommand(Command):
    contract_id: ContractId
    package_id: str
    reason: str
