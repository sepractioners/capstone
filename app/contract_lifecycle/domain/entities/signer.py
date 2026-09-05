"""Signer entity: one signatory within a SignaturePackage."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..value_objects import PartyId


@dataclass
class Signer:
    party_id: PartyId
    signer_role: str
    order: int
    signed_at: Optional[datetime] = None
