"""ContractNumber value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class ContractNumber:
    value: str

    def __post_init__(self) -> None:
        if not self.value or not self.value.strip():
            raise InvalidValueError("ContractNumber must not be empty")

    def __str__(self) -> str:
        return self.value
