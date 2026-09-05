"""ContractId value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError
from ._identifiers import new_id


@dataclass(frozen=True)
class ContractId:
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise InvalidValueError("ContractId must not be empty")

    @classmethod
    def new(cls) -> "ContractId":
        return cls(new_id("contract"))

    def __str__(self) -> str:
        return self.value
