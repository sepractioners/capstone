"""Amendment entity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from ..value_objects import VersionNumber


@dataclass
class Amendment:
    """An agreed change to an executed contract."""

    amendment_id: str
    modifies_version: VersionNumber
    affected_clause_ids: tuple[str, ...]
    effective_date: date
    resulting_version: Optional[VersionNumber] = None
    approved: bool = False
    signed: bool = False
