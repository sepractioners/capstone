"""EffectiveDate value object."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class EffectiveDate:
    value: date
