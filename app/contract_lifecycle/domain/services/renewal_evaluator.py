"""RenewalEvaluator domain service.

Determines whether a renewal window is open and what action is due, based
on the contract's key dates and renewal terms.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..aggregates import Contract


class RenewalEvaluator:
    def __init__(self, window_days_before_expiration: int = 90) -> None:
        self._window_days = window_days_before_expiration

    def window_opens_on(self, contract: "Contract") -> Optional[date]:
        expiration = contract.key_dates.expiration_date
        if expiration is None:
            return None
        return expiration - timedelta(days=self._window_days)

    def is_window_open(self, contract: "Contract", today: date) -> bool:
        opens_on = self.window_opens_on(contract)
        expiration = contract.key_dates.expiration_date
        if opens_on is None or expiration is None:
            return False
        return opens_on <= today <= expiration

    def is_auto_renewing(self, contract: "Contract") -> bool:
        return contract.renewal_terms.auto_renew
