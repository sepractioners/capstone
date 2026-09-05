"""ClauseReference value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError
from .document_reference import DocumentReference


@dataclass(frozen=True)
class ClauseReference:
    clause_id: str
    document: DocumentReference
    location: str

    def __post_init__(self) -> None:
        if not self.clause_id:
            raise InvalidValueError("ClauseReference requires a clause_id")
        if not self.location:
            raise InvalidValueError("ClauseReference requires a location")
