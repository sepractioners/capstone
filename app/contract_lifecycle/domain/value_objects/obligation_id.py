"""ObligationId value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError
from ._identifiers import new_id


@dataclass(frozen=True)
class ObligationId:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidValueError("ObligationId must not be empty")

    @classmethod
    def new(cls) -> "ObligationId":
        return cls(new_id("obligation"))

    def __str__(self) -> str:
        return self.value
