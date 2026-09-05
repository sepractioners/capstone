"""ChangeSummary value object."""
from __future__ import annotations

from dataclasses import dataclass

from ..exceptions import InvalidValueError


@dataclass(frozen=True)
class ChangeSummary:
    text: str

    def __post_init__(self) -> None:
        if not self.text or not self.text.strip():
            raise InvalidValueError("ChangeSummary must not be empty")
