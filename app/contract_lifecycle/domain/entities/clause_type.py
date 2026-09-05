"""ClauseType enum."""
from __future__ import annotations

from enum import Enum


class ClauseType(str, Enum):
    RIGHT = "right"
    OBLIGATION = "obligation"
    CONDITION = "condition"
    REMEDY = "remedy"
    DEFINITION = "definition"
    GENERAL_PROVISION = "general_provision"
