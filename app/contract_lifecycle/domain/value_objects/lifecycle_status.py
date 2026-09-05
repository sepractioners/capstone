"""LifecycleStatus value object and its allowed transition table."""
from __future__ import annotations

from enum import Enum


class LifecycleStatus(str, Enum):
    INTAKE = "intake"
    DRAFTING = "drafting"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    PENDING_SIGNATURE = "pending_signature"
    SIGNATURE_FAILED = "signature_failed"
    EXECUTED = "executed"
    ACTIVE = "active"
    TERMINATING = "terminating"
    TERMINATED = "terminated"
    RENEWED = "renewed"
    EXPIRED = "expired"
    ARCHIVED = "archived"


# Allowed forward transitions, per the DDD document's lifecycle diagram.
ALLOWED_TRANSITIONS: dict[LifecycleStatus, frozenset[LifecycleStatus]] = {
    LifecycleStatus.INTAKE: frozenset({LifecycleStatus.DRAFTING}),
    LifecycleStatus.DRAFTING: frozenset(
        {LifecycleStatus.IN_REVIEW, LifecycleStatus.CANCELLED}
    ),
    LifecycleStatus.IN_REVIEW: frozenset(
        {LifecycleStatus.APPROVED, LifecycleStatus.REJECTED}
    ),
    LifecycleStatus.APPROVED: frozenset({LifecycleStatus.PENDING_SIGNATURE}),
    LifecycleStatus.REJECTED: frozenset({LifecycleStatus.DRAFTING}),
    LifecycleStatus.PENDING_SIGNATURE: frozenset(
        {LifecycleStatus.EXECUTED, LifecycleStatus.SIGNATURE_FAILED}
    ),
    LifecycleStatus.SIGNATURE_FAILED: frozenset({LifecycleStatus.PENDING_SIGNATURE}),
    LifecycleStatus.EXECUTED: frozenset({LifecycleStatus.ACTIVE}),
    LifecycleStatus.ACTIVE: frozenset(
        {
            LifecycleStatus.TERMINATING,
            LifecycleStatus.RENEWED,
            LifecycleStatus.EXPIRED,
        }
    ),
    LifecycleStatus.TERMINATING: frozenset({LifecycleStatus.TERMINATED}),
    LifecycleStatus.RENEWED: frozenset({LifecycleStatus.ACTIVE}),
    LifecycleStatus.EXPIRED: frozenset({LifecycleStatus.ARCHIVED}),
    LifecycleStatus.TERMINATED: frozenset({LifecycleStatus.ARCHIVED}),
    LifecycleStatus.CANCELLED: frozenset(),
    LifecycleStatus.ARCHIVED: frozenset(),
}
