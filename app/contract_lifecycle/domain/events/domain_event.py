"""Base type for all domain events.

Every event describes a fact that has already happened and carries an
event ID, aggregate ID, aggregate version, occurred-at timestamp, actor or
system source, correlation ID, and (when relevant) the contract version
the fact pertains to.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    event_id: str
    aggregate_id: str
    aggregate_version: int
    occurred_at: datetime
    actor_id: str
    correlation_id: str
    version_reference: Optional[int] = None
