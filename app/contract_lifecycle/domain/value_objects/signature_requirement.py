"""SignatureRequirement value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class SignatureRequirement:
    signer_role: str
    order: int

    def __post_init__(self) -> None:
        if not self.signer_role:
            raise InvalidValueError("SignatureRequirement requires a signer_role")
        if self.order < 1:
            raise InvalidValueError("SignatureRequirement order must be >= 1")
