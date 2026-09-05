"""PolicyException entity (the DDD doc's `Exception` entity, renamed to
avoid shadowing the Python builtin)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..exceptions import InvalidValueError


@dataclass
class PolicyException:
    """An approved deviation from a policy, standard clause, approval
    threshold, or obligation process."""

    exception_id: str
    owner_actor_id: str
    rationale: str
    scope: str
    approver_actor_id: str
    expires_at: Optional[date] = None

    def __post_init__(self) -> None:
        if not self.rationale:
            raise InvalidValueError("PolicyException requires a rationale")
