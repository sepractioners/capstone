"""Deterministic date and money helpers for contract data.

Shared by the query agent's portfolio tools and the extraction agent's review
pass. Every calendar and currency computation in the system goes through here so
no LLM ever has to parse a date or add up money - and so both agents agree on
what "expiring within 90 days" or "$1.5M" means.

All functions are pure and take/return plain types (``date``, ``Decimal``,
``int``, ``str``).
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

__all__ = [
    "parse_date",
    "to_decimal",
    "parse_money",
    "resolve_timeframe_days",
    "total_value",
    "days_between",
    "add_days",
    "sum_values",
    "average_value",
]

_MONEY_RE = re.compile(r"\$?\s?([\d,]+(?:\.\d+)?)\s?(m|million|k|thousand|b|billion)?", re.I)
_MONEY_SCALE = {"m": Decimal(1_000_000), "million": Decimal(1_000_000), "b": Decimal(1_000_000_000),
                "billion": Decimal(1_000_000_000), "k": Decimal(1_000), "thousand": Decimal(1_000)}
_DAYS_EXPLICIT = re.compile(r"\b(?:next|within|coming|in)\s+(\d{1,4})\s+days?\b", re.I)


def parse_date(value: Any) -> date | None:
    """A ``date``, an ISO string (``2024-01-31`` / ``2024-01-31T...``), or None."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def to_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_money(text: str) -> Decimal | None:
    """"$1.5M" / "1,000,000" / "500k" / "2 billion" -> Decimal, or None."""
    match = _MONEY_RE.search(text or "")
    if not match:
        return None
    amount = to_decimal(match.group(1).replace(",", ""))
    if amount is None:
        return None
    return amount * _MONEY_SCALE.get((match.group(2) or "").lower(), Decimal(1))


def resolve_timeframe_days(phrase: str) -> int | None:
    """"next quarter" / "within 30 days" / "next year" / "in 6 months" -> a day count."""
    lowered = (phrase or "").lower()
    explicit = _DAYS_EXPLICIT.search(lowered)
    if explicit:
        return int(explicit.group(1))
    if re.search(r"\bnext (?:month|30 days)\b", lowered):
        return 30
    if re.search(r"\b(?:this|next|coming) quarter\b|\bnext 90 days\b|\bin q[1-4]\b", lowered):
        return 90
    if re.search(r"\b(?:next|coming|in) (?:6 months|half a? year)\b", lowered):
        return 182
    if re.search(r"\b(?:next|this|coming) year\b|\bnext 12 months\b", lowered):
        return 365
    return None


def total_value(contract: dict[str, Any]) -> Decimal | None:
    """The contract's total value as a Decimal, from ``commercial_terms``."""
    return to_decimal(((contract.get("commercial_terms") or {}).get("total_value") or {}).get("amount"))


def days_between(start: Any, end: Any) -> int | None:
    a, b = parse_date(start), parse_date(end)
    return (b - a).days if a and b else None


def add_days(value: Any, days: int) -> date | None:
    base = parse_date(value)
    return base + timedelta(days=days) if base else None


def sum_values(contracts: list[dict[str, Any]]) -> Decimal:
    return sum((v for v in (total_value(c) for c in contracts) if v is not None), Decimal(0))


def average_value(contracts: list[dict[str, Any]]) -> Decimal | None:
    values = [v for v in (total_value(c) for c in contracts) if v is not None]
    return (sum(values) / len(values)) if values else None
