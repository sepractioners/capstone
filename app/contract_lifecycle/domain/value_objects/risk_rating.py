"""RiskRating value object."""
from __future__ import annotations

from dataclasses import dataclass, field

from .risk_factor import RiskFactor
from .risk_level import RiskLevel


@dataclass(frozen=True)
class RiskRating:
    level: RiskLevel
    factors: tuple[RiskFactor, ...] = field(default_factory=tuple)
