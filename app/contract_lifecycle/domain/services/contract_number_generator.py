"""ContractNumberGenerator: pluggable numbering strategy.

A Protocol so an organization can supply its own numbering scheme
(fiscal-year-based, per-business-unit, ...) without modifying callers -
callers depend only on this abstraction (dependency inversion).
"""
from __future__ import annotations

from typing import Protocol

from ..value_objects import ContractNumber, ContractType


class ContractNumberGenerator(Protocol):
    def generate(self, contract_type: ContractType) -> ContractNumber:
        ...
