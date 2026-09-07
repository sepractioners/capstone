"""Scoring functions for the extraction eval - synthetic data, no LLM."""
from __future__ import annotations

from platform_testing.extraction_eval import evaluate, score_field


def test_title_uses_token_f1() -> None:
    assert score_field("title", "Co-Branding Agreement", "Co Branding Agreement") == 1.0
    assert 0.0 < score_field("title", "Co-Branding Agreement", "Co-Branding Services Agreement") < 1.0


def test_parties_match_on_normalised_overlap() -> None:
    assert score_field("parties", ["Acme Corp.", "Beta LLC"], ["Acme Corp", "Beta LLC"]) == 1.0
    assert score_field("parties", ["Acme Corp"], ["Acme Corp", "Beta LLC"]) < 1.0


def test_contract_type_is_exact_match() -> None:
    assert score_field("contract_type", "affiliate-agreement", "Affiliate-Agreement") == 1.0
    assert score_field("contract_type", "vendor-agreement", "affiliate-agreement") == 0.0


def test_dates_compare_iso_prefix() -> None:
    assert score_field("effective_date", "2001-05-15T00:00:00", "2001-05-15") == 1.0
    assert score_field("expiration_date", None, "2001-05-15") == 0.0


def test_clause_count_tolerates_small_deltas() -> None:
    assert score_field("clause_count", 10, 10) == 1.0
    assert score_field("clause_count", 8, 10) == 0.8
    assert score_field("clause_count", 0, 10) == 0.0


def test_null_expected_field_is_not_scored() -> None:
    assert score_field("title", "anything", None) == -1.0


def test_evaluate_reports_pdf_missing_without_crashing(tmp_path) -> None:
    truth = tmp_path / "truth.jsonl"
    truth.write_text('{"filename": "nope.pdf", "contract_type": "affiliate-agreement"}\n', encoding="utf-8")
    result = evaluate(tmp_path, truth, limit=5)
    assert result["documents"] == 1
    assert result["rows"][0]["error"] == "pdf_missing"
