"""DeliveryMethod value object."""
from __future__ import annotations

from enum import Enum


class DeliveryMethod(str, Enum):
    EMAIL = "email"
    MAIL = "mail"
    COURIER = "courier"
    PORTAL = "portal"
