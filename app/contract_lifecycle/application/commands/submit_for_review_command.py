"""SubmitForReviewCommand."""
from __future__ import annotations

from dataclasses import dataclass

from ...domain.value_objects import ContractId
from .command import Command


@dataclass(frozen=True, kw_only=True)
class SubmitForReviewCommand(Command):
    contract_id: ContractId
