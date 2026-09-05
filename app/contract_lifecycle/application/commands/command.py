"""Command: the base envelope every application command carries.

Per the DDD document: "An application command should carry an
idempotency key and actor context."
"""
from __future__ import annotations

from dataclasses import dataclass

from ...domain.value_objects import Actor


@dataclass(frozen=True, kw_only=True)
class Command:
    idempotency_key: str
    actor: Actor
    correlation_id: str
