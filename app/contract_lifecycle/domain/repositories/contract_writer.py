"""ContractWriter: the write half of the Contract repository interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..aggregates import Contract
    from ..events import DomainEvent
    from ..value_objects import ContractId


class ContractWriter(ABC):
    @abstractmethod
    def save(self, contract: "Contract") -> list["DomainEvent"]:
        """Persist the aggregate and drain its pending domain events as
        part of the same transaction, returning them so the caller can
        publish them after commit.

        Must raise domain.exceptions.ConcurrencyConflict if the stored
        row version has advanced past the version this `contract` was
        loaded at (see Contract.version_at_load).
        """

    @abstractmethod
    def next_identity(self) -> "ContractId":
        ...
