"""Raised when an optimistic concurrency check fails on save."""
from .domain_error import DomainError


class ConcurrencyConflict(DomainError):
    """Optimistic concurrency check failed on save."""

    def __init__(self, aggregate_id: str, expected_version: int, actual_version: int) -> None:
        super().__init__(
            f"Aggregate {aggregate_id} version conflict: "
            f"expected {expected_version}, found {actual_version}"
        )
        self.aggregate_id = aggregate_id
        self.expected_version = expected_version
        self.actual_version = actual_version
