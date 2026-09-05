"""DocumentReference value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class DocumentReference:
    uri: str
    media_type: str
    content_hash: str

    def __post_init__(self) -> None:
        if not self.uri:
            raise InvalidValueError("DocumentReference requires a uri")
        if not self.content_hash:
            raise InvalidValueError("DocumentReference requires a content_hash")
