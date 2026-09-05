"""Domain-level errors.

Raised by value objects, entities, the aggregate, and domain services when an
invariant is violated. Application and infrastructure code should catch
these and translate them, not swallow them.
"""
from .authorization_error import AuthorizationError
from .concurrency_conflict import ConcurrencyConflict
from .domain_error import DomainError
from .invalid_state_transition import InvalidStateTransition
from .invalid_value_error import InvalidValueError
from .invariant_violation import InvariantViolation
from .not_found_error import NotFoundError

__all__ = [
    "AuthorizationError",
    "ConcurrencyConflict",
    "DomainError",
    "InvalidStateTransition",
    "InvalidValueError",
    "InvariantViolation",
    "NotFoundError",
]
