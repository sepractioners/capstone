"""NoticeType enum."""
from __future__ import annotations

from enum import Enum


class NoticeType(str, Enum):
    RENEWAL = "renewal"
    TERMINATION = "termination"
    BREACH = "breach"
    GENERAL = "general"
