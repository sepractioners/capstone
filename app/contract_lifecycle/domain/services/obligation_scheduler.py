"""ObligationScheduler domain service.

Creates ObligationOccurrence instances from an obligation's due-date and
recurrence rule. Pure and stateless: given the same obligation it always
produces the same schedule.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from ..entities import Obligation, ObligationOccurrence
from ..value_objects import RecurrenceFrequency

_APPROX_DAYS_PER_FREQUENCY = {
    RecurrenceFrequency.DAILY: 1,
    RecurrenceFrequency.WEEKLY: 7,
    RecurrenceFrequency.MONTHLY: 30,
    RecurrenceFrequency.QUARTERLY: 91,
    RecurrenceFrequency.YEARLY: 365,
}


class ObligationScheduler:
    def schedule(self, obligation: Obligation, horizon: Optional[date] = None) -> list[ObligationOccurrence]:
        first_due = obligation.due_date_rule.value
        if obligation.recurrence is None:
            return [
                ObligationOccurrence(
                    obligation_id=obligation.obligation_id,
                    sequence=1,
                    due_date=first_due,
                )
            ]

        rule = obligation.recurrence
        step_days = _APPROX_DAYS_PER_FREQUENCY[rule.frequency] * rule.interval
        occurrences: list[ObligationOccurrence] = []
        due = first_due
        sequence = 1
        while True:
            if rule.until is not None and due > rule.until:
                break
            if horizon is not None and due > horizon:
                break
            occurrences.append(
                ObligationOccurrence(
                    obligation_id=obligation.obligation_id,
                    sequence=sequence,
                    due_date=due,
                )
            )
            if rule.count is not None and sequence >= rule.count:
                break
            sequence += 1
            due = due + timedelta(days=step_days)
            if horizon is None and rule.until is None and rule.count is None:
                # Without an explicit bound, a single occurrence is returned
                # and the caller is expected to schedule the next one closer
                # to its due date rather than generating an unbounded list.
                break
        return occurrences
