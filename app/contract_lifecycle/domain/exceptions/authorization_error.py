"""Raised when an actor is not permitted to perform the requested action."""
from .domain_error import DomainError


class AuthorizationError(DomainError):
    """An actor is not permitted to perform the requested action."""
