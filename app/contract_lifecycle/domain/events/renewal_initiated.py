"""RenewalInitiated event."""
from __future__ import annotations

from dataclasses import dataclass

from .domain_event import DomainEvent


@dataclass(frozen=True, kw_only=True)
class RenewalInitiated(DomainEvent):
    pass
