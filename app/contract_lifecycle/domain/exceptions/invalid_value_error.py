"""Raised when a value object is constructed with an invalid value."""
from .domain_error import DomainError


class InvalidValueError(DomainError):
    """A value object was constructed with an invalid value."""
