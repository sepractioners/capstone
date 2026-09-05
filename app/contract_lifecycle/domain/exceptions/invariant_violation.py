"""Raised when an aggregate invariant would be violated."""
from .domain_error import DomainError


class InvariantViolation(DomainError):
    """An aggregate invariant would be violated by the requested change."""
