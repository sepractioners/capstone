"""ContractType value object.

Its meaning is determined entirely by its normalized value. It has no
independent identity, lifecycle, or business behavior outside the contract
that uses it (see docs: `ContractType` section).

The supported vocabulary is open for extension (register new types from a
reference-data context) without modifying this class, per the
open/closed principle.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import ClassVar

from ..exceptions import InvalidValueError

_CONTRACT_TYPE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

_DEFAULT_SUPPORTED_TYPES = frozenset(
    {
        "master-services-agreement",
        "nda",
        "sow",
        "employment",
        "vendor",
        "license",
        "lease",
        "purchase-order",
        "amendment",
    }
)


@dataclass(frozen=True)
class ContractType:
    value: str

    _supported: ClassVar[set[str]] = set(_DEFAULT_SUPPORTED_TYPES)

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if not _CONTRACT_TYPE_RE.match(normalized):
            raise InvalidValueError(f"Invalid ContractType format: {self.value!r}")
        if normalized not in ContractType._supported:
            raise InvalidValueError(f"Unsupported ContractType: {self.value!r}")
        object.__setattr__(self, "value", normalized)

    @classmethod
    def register(cls, type_value: str) -> None:
        """Extend the supported vocabulary without modifying this class."""
        normalized = type_value.strip().lower()
        if not _CONTRACT_TYPE_RE.match(normalized):
            raise InvalidValueError(f"Invalid ContractType format: {type_value!r}")
        cls._supported.add(normalized)

    @classmethod
    def supported_types(cls) -> frozenset[str]:
        return frozenset(cls._supported)

    @classmethod
    def from_stored(cls, value: str) -> "ContractType":
        """Reconstruct a ContractType read back from storage.

        A value object's vocabulary registration (see `register`) lives
        only in this process's memory - it is never persisted. A value
        that was already written to storage was valid when some process
        wrote it, even if *this* process never registered it. Repository
        mappers should use this instead of the constructor when
        deserializing, so reloading a contract never fails purely because
        it happens to run in a fresh process.
        """
        normalized = value.strip().lower()
        if normalized not in cls._supported:
            cls.register(normalized)
        return cls(normalized)

    def __str__(self) -> str:
        return self.value
