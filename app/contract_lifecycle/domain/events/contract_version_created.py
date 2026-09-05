"""ContractVersionCreated event."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class ContractVersionCreated(DomainEvent):
    change_summary: Optional[str] = None
