"""ContractParty entity."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..exceptions import InvalidValueError
from ..value_objects import Address, ContactDetails, Jurisdiction, LegalName, PartyId
from .party_role import PartyRole
from .party_type import PartyType


@dataclass
class ContractParty:
    """A legal entity or person bound by the agreement."""

    party_id: PartyId
    legal_name: LegalName
    party_type: PartyType
    jurisdiction: Jurisdiction
    roles: tuple[PartyRole, ...]
    registration_id: Optional[str] = None
    address: Optional[Address] = None
    contact: Optional[ContactDetails] = None

    def __post_init__(self) -> None:
        if not self.roles:
            raise InvalidValueError("ContractParty requires at least one role")
