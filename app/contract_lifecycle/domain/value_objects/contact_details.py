"""ContactDetails value object."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class ContactDetails:
    email: Optional[str] = None
    phone: Optional[str] = None

    def __post_init__(self) -> None:
        if self.email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", self.email):
            raise InvalidValueError(f"Invalid email address: {self.email!r}")
        if not self.email and not self.phone:
            raise InvalidValueError("ContactDetails requires an email or phone")
