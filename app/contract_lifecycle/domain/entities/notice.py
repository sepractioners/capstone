"""Notice entity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..value_objects import DeliveryMethod, PartyId
from .notice_type import NoticeType


@dataclass
class Notice:
    """A formal notice required or permitted by the contract."""

    notice_id: str
    notice_type: NoticeType
    recipient_party_id: PartyId
    delivery_method: DeliveryMethod
    notice_period_days: int
    sent_at: Optional[datetime] = None
    effective_at: Optional[datetime] = None
