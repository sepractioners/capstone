"""RecordSignatureCommand: supporting command for a signer completion callback."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ...domain.value_objects import ContractId, PartyId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class RecordSignatureCommand(Command):
    contract_id: ContractId
    package_id: str
    party_id: PartyId
    signed_at: datetime
