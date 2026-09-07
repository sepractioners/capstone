"""Deterministic portfolio queries - no LLM, no retrieval."""
from __future__ import annotations

from datetime import date, timedelta

from query_agent import portfolio

_SOON = (date.today() + timedelta(days=45)).isoformat()
_LATER = (date.today() + timedelta(days=400)).isoformat()

CONTRACTS = [
    {"id": "c1", "title": "A", "contract_number": "N1", "lifecycle_status": "active",
     "contract_type": "vendor-agreement",
     "key_dates": {"effective_date": "2024-03-01", "expiration_date": _SOON},
     "commercial_terms": {"total_value": {"amount": "1000", "currency": "USD"}},
     "parties": [{"legal_name": "Acme Corp"}],
     "clauses": [{"heading": "Insurance", "text": "Vendor shall maintain commercial general liability insurance."}],
     "obligations": []},
    {"id": "c2", "title": "B", "contract_number": "N2", "lifecycle_status": "active",
     "contract_type": "nda",
     "key_dates": {"effective_date": "2023-06-01", "expiration_date": _LATER},
     "commercial_terms": {"total_value": {"amount": "3000", "currency": "USD"}},
     "parties": [{"legal_name": "Beta LLC"}],
     "clauses": [{"heading": "Confidentiality", "text": "Keep it secret."}]},
    {"id": "c3", "title": "C", "contract_number": "N3", "lifecycle_status": "in_review",
     "contract_type": "nda", "key_dates": {"effective_date": "2024-11-01"},
     "commercial_terms": {},
     "parties": [{"legal_name": "Acme Corp"}],
     "clauses": [{"heading": "Insurance", "text": "Each party carries liability insurance."}]},
]


def test_count_total_and_breakdowns() -> None:
    result = portfolio.count_contracts(CONTRACTS)
    assert result["total"] == 3 and result["matched"] == 3
    assert result["by_lifecycle_status"] == {"active": 2, "in_review": 1}
    assert result["by_contract_type"] == {"nda": 2, "vendor-agreement": 1}


def test_count_with_filter_reports_matched_but_full_breakdowns() -> None:
    result = portfolio.count_contracts(CONTRACTS, lifecycle_status="active")
    assert result["matched"] == 2
    # breakdowns are always over the whole set, so one call answers every "how many"
    assert result["by_lifecycle_status"] == {"active": 2, "in_review": 1}
    assert result["by_contract_type"] == {"nda": 2, "vendor-agreement": 1}


def test_count_filter_is_case_insensitive() -> None:
    assert portfolio.count_contracts(CONTRACTS, contract_type="NDA")["matched"] == 2


def test_list_summary_rows() -> None:
    result = portfolio.list_contracts(CONTRACTS, lifecycle_status="active")
    assert result["matched"] == 2 and result["detail"] == "summary"
    row = next(r for r in result["contracts"] if r["id"] == "c1")
    assert row["total_value"] == "1000 USD"
    assert row["expiration_date"] == _SOON
    assert "clauses" not in row


def test_where_filters_by_effective_year_expiry_window_and_value() -> None:
    assert portfolio.count_contracts(CONTRACTS, where={"effective_year": 2024})["matched"] == 2
    expiring = portfolio.list_contracts(CONTRACTS, where={"expiring_within_days": 90})
    assert {r["id"] for r in expiring["contracts"]} == {"c1"}
    over_value = portfolio.list_contracts(CONTRACTS, where={"min_value": 2000})
    assert {r["id"] for r in over_value["contracts"]} == {"c2"}
    assert portfolio.count_contracts(CONTRACTS, where={"party": "acme"})["matched"] == 2


def test_aggregate_sum_and_avg_value() -> None:
    total = portfolio.aggregate_contracts(CONTRACTS, measure="sum_value")
    assert total["value"] == "4000" and total["matched"] == 3
    active_total = portfolio.aggregate_contracts(CONTRACTS, measure="sum_value", where={"lifecycle_status": "active"})
    assert active_total["value"] == "4000" and active_total["matched"] == 2
    avg = portfolio.aggregate_contracts(CONTRACTS, measure="avg_value")
    assert avg["value"] == "2000.00"


def test_aggregate_group_by_contract_type() -> None:
    grouped = portfolio.aggregate_contracts(CONTRACTS, measure="sum_value", group_by="contract_type")
    by_type = {row["group"]: row["value"] for row in grouped["results"]}
    assert by_type == {"nda": "3000", "vendor-agreement": "1000"}


def test_aggregate_count_by_party() -> None:
    grouped = portfolio.aggregate_contracts(CONTRACTS, measure="count", group_by="party")
    by_party = {row["group"]: row["value"] for row in grouped["results"]}
    assert by_party == {"Acme Corp": 2, "Beta LLC": 1}


def test_list_full_returns_whole_records_under_cap() -> None:
    result = portfolio.list_contracts(CONTRACTS, contract_type="vendor-agreement", detail="full")
    assert result["detail"] == "full"
    assert result["contracts"][0]["clauses"][0]["heading"] == "Insurance"
    assert result["note"] == ""


def test_list_full_falls_back_to_summary_when_too_many_match() -> None:
    result = portfolio.list_contracts(CONTRACTS, contract_type="nda", detail="full", full_max=1)
    assert result["detail"] == "summary"
    assert "Narrow the filter" in result["note"]


def test_match_terms_drops_question_words() -> None:
    assert portfolio.match_terms("Which contracts those need liability insurance?") == ["liability", "insurance"]


def test_find_contracts_enumerates_every_match_not_a_sample() -> None:
    result = portfolio.find_contracts(CONTRACTS, text="liability insurance")
    assert result["matched"] == 2
    assert {r["id"] for r in result["contracts"]} == {"c1", "c3"}
    assert result["contracts"][0]["matched_clauses"] == ["Insurance"]
    assert result["truncated"] is False


def test_find_contracts_requires_all_terms() -> None:
    assert portfolio.find_contracts(CONTRACTS, text="confidentiality")["matched"] == 1
    assert portfolio.find_contracts(CONTRACTS, text="liability confidentiality")["matched"] == 0


def test_find_contracts_honours_where_filter() -> None:
    result = portfolio.find_contracts(CONTRACTS, text="insurance", where={"lifecycle_status": "active"})
    assert {r["id"] for r in result["contracts"]} == {"c1"}


def test_facets_lists_present_values() -> None:
    f = portfolio.facets(CONTRACTS)
    assert set(f["lifecycle_status"]) == {"active", "in_review"}
    assert set(f["contract_type"]) == {"nda", "vendor-agreement"}
