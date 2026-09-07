"""Shared deterministic date/money helpers - no LLM."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from contract_calc import (
    add_days,
    average_value,
    days_between,
    parse_date,
    parse_money,
    resolve_timeframe_days,
    sum_values,
    total_value,
)


def test_parse_date_accepts_iso_and_datetime_and_date() -> None:
    assert parse_date("2024-03-01") == date(2024, 3, 1)
    assert parse_date("2024-03-01T12:00:00+00:00") == date(2024, 3, 1)
    assert parse_date(date(2024, 3, 1)) == date(2024, 3, 1)
    assert parse_date("") is None and parse_date("not-a-date") is None


def test_parse_money_scales() -> None:
    assert parse_money("$1.5M") == Decimal("1500000.0")
    assert parse_money("1,000,000") == Decimal("1000000")
    assert parse_money("500k") == Decimal("500000")
    assert parse_money("2 billion") == Decimal("2000000000")
    assert parse_money("no number here") is None


def test_resolve_timeframe_days() -> None:
    assert resolve_timeframe_days("expiring in the next quarter") == 90
    assert resolve_timeframe_days("within 45 days") == 45
    assert resolve_timeframe_days("next month") == 30
    assert resolve_timeframe_days("next year") == 365
    assert resolve_timeframe_days("some day") is None


def test_value_helpers() -> None:
    contracts = [
        {"commercial_terms": {"total_value": {"amount": "1000"}}},
        {"commercial_terms": {"total_value": {"amount": "3000"}}},
        {"commercial_terms": {}},
    ]
    assert total_value(contracts[0]) == Decimal("1000")
    assert sum_values(contracts) == Decimal("4000")
    assert average_value(contracts) == Decimal("2000")
    assert average_value([{"commercial_terms": {}}]) is None


def test_date_arithmetic() -> None:
    assert days_between("2024-01-01", "2024-01-31") == 30
    assert days_between("2024-01-01", None) is None
    assert add_days("2024-01-31", -30) == date(2024, 1, 1)
