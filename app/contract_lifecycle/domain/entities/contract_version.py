"""ContractVersion entity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..exceptions import InvalidValueError
from ..value_objects import DocumentReference, VersionNumber
from .version_status import VersionStatus


@dataclass
class ContractVersion:
    """A particular legal representation of the contract.

    A signed version is immutable; only one version can be the executed
    version for a given execution event.
    """

    version_number: VersionNumber
    document: DocumentReference
    author_id: str
    created_at: datetime
    change_summary: Optional[str] = None
    superseded_version: Optional[VersionNumber] = None
    status: VersionStatus = VersionStatus.DRAFT

    def mark_executed(self) -> None:
        if self.status not in (VersionStatus.APPROVED, VersionStatus.DRAFT):
            raise InvalidValueError(
                f"Version {self.version_number.value} cannot be executed from status {self.status}"
            )
        self.status = VersionStatus.EXECUTED

    def supersede(self) -> None:
        self.status = VersionStatus.SUPERSEDED
