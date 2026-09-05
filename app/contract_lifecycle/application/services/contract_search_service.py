"""ContractSearchService: read-oriented queries.

Depends only on ContractReader, not the full ContractRepository -
interface segregation: a read-only service should not be able to write.
"""
from __future__ import annotations

from typing import Optional

from ...domain.aggregates import Contract
from ...domain.repositories import ContractReader
from ...domain.value_objects import ContractId, ContractNumber, LifecycleStatus


class ContractSearchService:
    def __init__(self, reader: ContractReader) -> None:
        self._reader = reader

    def get(self, contract_id: ContractId) -> Contract:
        return self._reader.get(contract_id)

    def find_by_number(self, contract_number: ContractNumber) -> Optional[Contract]:
        return self._reader.find_by_number(contract_number)

    def list_by_status(self, status: LifecycleStatus) -> list[Contract]:
        return self._reader.list_by_status(status)
