"""Jurisdiction value object."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class Jurisdiction:
    country_code: str
    subdivision: Optional[str] = None

    def __post_init__(self) -> None:
        if not re.match(r"^[A-Z]{2}$", self.country_code):
            raise InvalidValueError(
                f"Jurisdiction country_code must be an ISO 3166-1 alpha-2 code: {self.country_code!r}"
            )
