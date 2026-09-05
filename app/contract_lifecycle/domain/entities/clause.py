"""Clause entity."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..value_objects import DocumentReference, VersionNumber
from .clause_status import ClauseStatus
from .clause_type import ClauseType


@dataclass
class Clause:
    """A legal provision within a contract version or clause-library entry.

    Immutable once its containing contract version is executed; a wording
    change requires a new version or amendment.

    `text_reference` + `location` say *where* this clause lives in the
    source document; `text` is the actual extracted wording, captured at
    extraction time so it can be shown side-by-side with the source
    without re-deriving it later. `text` is optional because a
    manually-curated clause-library entry may reasonably carry only a
    reference (a lawyer tagging a location) without duplicating wording.
    """

    clause_id: str
    heading: str
    text_reference: DocumentReference
    clause_type: ClauseType
    location: str
    version_number: VersionNumber
    text: Optional[str] = None
    status: ClauseStatus = ClauseStatus.DRAFT

    def lock(self) -> None:
        self.status = ClauseStatus.IMMUTABLE
