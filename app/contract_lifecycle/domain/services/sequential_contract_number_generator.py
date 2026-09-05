"""SequentialContractNumberGenerator: the default ContractNumberGenerator.

Formats numbers as `<PREFIX>-<contract-type>-<zero-padded-sequence>`. A
different organizational policy can be introduced by implementing
ContractNumberGenerator directly, leaving this class untouched.
"""
from __future__ import annotations

from ..value_objects import ContractNumber, ContractType


class SequentialContractNumberGenerator:
    def __init__(self, prefix: str = "CLM", start: int = 1) -> None:
        self._prefix = prefix
        self._next = start

    def generate(self, contract_type: ContractType) -> ContractNumber:
        number = ContractNumber(f"{self._prefix}-{contract_type}-{self._next:06d}")
        self._next += 1
        return number
