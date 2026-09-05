"""Actor value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError
from .organizational_role import OrganizationalRole


@dataclass(frozen=True)
class Actor:
    actor_id: str
    display_name: str
    role: OrganizationalRole
    is_system: bool = False

    def __post_init__(self) -> None:
        if not self.actor_id:
            raise InvalidValueError("Actor requires an actor_id")
