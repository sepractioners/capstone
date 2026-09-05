"""ContractTerminated event."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ContractTerminated(DomainEvent):
    effective_date: date
