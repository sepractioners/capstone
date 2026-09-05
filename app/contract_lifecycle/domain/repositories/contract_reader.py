"""ContractReader: the read half of the Contract repository interface.

Split from ContractWriter so read-only consumers (e.g. a search or
reporting service) can depend on just this interface instead of the full
read/write contract (interface segregation principle).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from ..value_objects import ContractNumber, LifecycleStatus

if TYPE_CHECKING:
    from ..aggregates import Contract
    from ..value_objects import ContractId


class ContractReader(ABC):
    @abstractmethod
    def get(self, contract_id: "ContractId") -> "Contract":
        """Raise domain.exceptions.NotFoundError if no such contract exists."""

    @abstractmethod
    def find_by_number(self, contract_number: ContractNumber) -> Optional["Contract"]:
        ...

    @abstractmethod
    def list_by_status(self, status: LifecycleStatus) -> list["Contract"]:
        ...
