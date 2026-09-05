"""NoticeDeadlineCalculator domain service.

Calculates a notice deadline using a contract's notice period and an
injected business calendar (constructor injection keeps this service
testable and decoupled from any single calendar's holiday list).
"""
from __future__ import annotations

from datetime import date

from ..value_objects import BusinessCalendar, NoticePeriod


class NoticeDeadlineCalculator:
    def __init__(self, calendar: BusinessCalendar) -> None:
        self._calendar = calendar

    def calculate(self, base_date: date, notice_period: NoticePeriod) -> date:
        return self._calendar.add_business_days(base_date, notice_period.days)
