"""ContractRepository: full read/write access, for callers that need both.

Application services typically depend on this; a read-only reporting
service should depend on ContractReader alone.
"""
from __future__ import annotations

from abc import ABC

from .contract_reader import ContractReader
from .contract_writer import ContractWriter


class ContractRepository(ContractReader, ContractWriter, ABC):
    pass
