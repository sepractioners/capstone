"""CommercialTerms value object."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .money import Money


@dataclass(frozen=True)
class CommercialTerms:
    total_value: Optional[Money] = None
    payment_terms: Optional[str] = None
    pricing_model: Optional[str] = None
