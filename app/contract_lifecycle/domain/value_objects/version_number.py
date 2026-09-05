"""VersionNumber value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class VersionNumber:
    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise InvalidValueError("VersionNumber must be >= 1")

    def next(self) -> "VersionNumber":
        return VersionNumber(self.value + 1)

    def __int__(self) -> int:
        return self.value
