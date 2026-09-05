"""AccessPolicy value object."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AccessPolicy:
    allowed_roles: tuple[str, ...] = field(default_factory=tuple)
    confidentiality_level: str = "standard"
