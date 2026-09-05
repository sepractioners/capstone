"""Raised when a requested aggregate or entity does not exist."""
from .domain_error import DomainError


class NotFoundError(DomainError):
    """A requested aggregate or entity does not exist."""
