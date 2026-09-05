"""SignaturePackage entity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..value_objects import VersionNumber
from .signature_status import SignatureStatus
from .signer import Signer


@dataclass
class SignaturePackage:
    """A coordinated request for signatures against one exact contract version."""

    package_id: str
    version_number: VersionNumber
    signers: list[Signer]
    provider_reference: Optional[str] = None
    deadline: Optional[datetime] = None
    status: SignatureStatus = SignatureStatus.PENDING

    def all_signed(self) -> bool:
        return all(s.signed_at is not None for s in self.signers)
