"""RecordContractTermsCommand."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...domain.value_objects import ContractId, KeyDates, RenewalTerms, TerminationTerms
from .command import Command


@dataclass(frozen=True, kw_only=True)
class RecordContractTermsCommand(Command):
    contract_id: ContractId
    key_dates: Optional[KeyDates] = None
    renewal_terms: Optional[RenewalTerms] = None
    termination_terms: Optional[TerminationTerms] = None
