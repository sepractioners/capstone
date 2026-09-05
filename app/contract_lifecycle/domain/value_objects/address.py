"""Address value object."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class Address:
    line1: str
    city: str
    country_code: str
    line2: Optional[str] = None
    state_or_province: Optional[str] = None
    postal_code: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.line1 or not self.city or not self.country_code:
            raise InvalidValueError("Address requires line1, city, and country_code")
