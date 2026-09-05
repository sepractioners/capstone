"""OrganizationalRole value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class OrganizationalRole:
    name: str

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidValueError("OrganizationalRole requires a name")
