"""RequestSignatureCommand."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ...domain.entities import Signer
from ...domain.value_objects import ContractId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class RequestSignatureCommand(Command):
    contract_id: ContractId
    package_id: str
    signers: list[Signer]
    provider_reference: Optional[str] = None
    deadline: Optional[datetime] = None
