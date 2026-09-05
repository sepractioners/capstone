"""PartyType enum."""
from __future__ import annotations

from enum import Enum


class PartyType(str, Enum):
    ORGANIZATION = "organization"
    INDIVIDUAL = "individual"
