"""Raised when a lifecycle transition is attempted from an illegal source state."""
from .invariant_violation import InvariantViolation


class InvalidStateTransition(InvariantViolation):
    """A lifecycle transition was attempted from an illegal source state."""

    def __init__(self, current_status: str, attempted: str) -> None:
        super().__init__(
            f"Cannot transition from '{current_status}' to '{attempted}'"
        )
        self.current_status = current_status
        self.attempted = attempted
