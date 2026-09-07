"""Document-level review reasoning pass - deterministic checks + mocked LLM."""
from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent_llm import client as llm_client
from extraction_agent import review_node
from extraction_agent.review_node import has_blocker, review_candidate
from extraction_agent.schema import (
    ContractCandidate,
    ExtractedCommercialTerms,
    ExtractedKeyDates,
    ExtractedObligation,
    ExtractedParty,
    ExtractedRenewalTerms,
    ExtractedTerminationTerms,
    PageExtraction,
)


def _candidate(**overrides) -> ContractCandidate:
    base = dict(
        source_document_hash="h",
        source_uri="file:///c.pdf",
        source_media_type="application/pdf",
        source_content_base64="ZmFrZQ==",
        title="Services Agreement",
        contract_type="services-agreement",
        parties=[ExtractedParty(legal_name="Acme Corp"), ExtractedParty(legal_name="Beta LLC")],
    )
    base.update(overrides)
    return ContractCandidate(**base)


def _review_response(**fields):
    parsed = review_node._ReviewResult(**fields)
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])


def _run(candidate, pages=None, directive=None, profile=None):
    return asyncio.run(
        review_candidate(candidate, pages or [PageExtraction(page_number=1)], "full contract text", profile, directive)
    )


def test_obligation_referencing_unknown_party_is_flagged() -> None:
    candidate = _candidate(
        obligations=[ExtractedObligation(description="Pay the fee", responsible_party_legal_name="Ghost Inc")]
    )
    with patch.object(llm_client, "acompletion", new=AsyncMock(return_value=_review_response())):
        reviewed = _run(candidate)
    assert any(f.field == "obligations" for f in reviewed.review_findings)
    assert not has_blocker(reviewed)


def test_expiration_before_effective_is_a_blocker() -> None:
    candidate = _candidate(
        key_dates=ExtractedKeyDates(effective_date=date(2021, 1, 1), expiration_date=date(2020, 1, 1))
    )
    with patch.object(llm_client, "acompletion", new=AsyncMock(return_value=_review_response())):
        reviewed = _run(candidate)
    assert has_blocker(reviewed)


def test_directive_disagreement_is_a_blocker_and_conflict() -> None:
    candidate = _candidate(contract_type="services-agreement")
    with patch.object(llm_client, "acompletion", new=AsyncMock(return_value=_review_response())):
        reviewed = _run(candidate, directive={"requested_contract_type": "vendor-agreement"})
    assert has_blocker(reviewed)
    assert any(c.field == "contract_type_instruction" for c in reviewed.field_conflicts)


def test_review_adopts_classification_only_when_page_pass_had_none() -> None:
    candidate = _candidate(contract_type="unclassified")
    with patch.object(
        llm_client, "acompletion", new=AsyncMock(return_value=_review_response(contract_type="co-branding-agreement"))
    ):
        reviewed = _run(candidate)
    assert reviewed.contract_type == "co-branding-agreement"


def test_review_never_overwrites_a_specific_page_classification() -> None:
    candidate = _candidate(contract_type="services-agreement")
    with patch.object(
        llm_client, "acompletion", new=AsyncMock(return_value=_review_response(contract_type="vendor-agreement"))
    ):
        reviewed = _run(candidate)
    assert reviewed.contract_type == "services-agreement"
    assert any(f.field == "contract_type" for f in reviewed.review_findings)


def test_self_consistency_vote_flags_missing_party() -> None:
    candidate = _candidate()
    with patch.object(
        llm_client,
        "acompletion",
        new=AsyncMock(return_value=_review_response(parties=["Acme Corp", "Beta LLC", "Gamma Co"])),
    ):
        reviewed = _run(candidate)
    assert any("Gamma Co" in f.issue for f in reviewed.review_findings)


def test_review_survives_an_llm_failure() -> None:
    candidate = _candidate()
    with patch.object(llm_client, "acompletion", new=AsyncMock(side_effect=RuntimeError("provider down"))):
        reviewed = _run(candidate)
    assert reviewed.review_summary == ""
    assert any(e.get("stage") == "document_review" and e.get("status") == "unavailable" for e in reviewed.extraction_trace)


def test_auto_renew_without_a_notice_window_is_flagged() -> None:
    candidate = _candidate(renewal_terms=ExtractedRenewalTerms(auto_renew=True))
    with patch.object(llm_client, "acompletion", new=AsyncMock(return_value=_review_response())):
        reviewed = _run(candidate)
    assert any(f.field == "renewal_terms" for f in reviewed.review_findings)
    assert not has_blocker(reviewed)


def test_termination_for_convenience_without_notice_is_flagged() -> None:
    candidate = _candidate(
        termination_terms=ExtractedTerminationTerms(termination_for_convenience=True)
    )
    with patch.object(llm_client, "acompletion", new=AsyncMock(return_value=_review_response())):
        reviewed = _run(candidate)
    assert any(f.field == "termination_terms" for f in reviewed.review_findings)


def test_obligation_due_after_expiration_is_flagged() -> None:
    candidate = _candidate(
        key_dates=ExtractedKeyDates(effective_date=date(2024, 1, 1), expiration_date=date(2024, 12, 31)),
        obligations=[
            ExtractedObligation(
                description="Final report", responsible_party_legal_name="Acme Corp", due_date=date(2025, 3, 1)
            )
        ],
    )
    with patch.object(llm_client, "acompletion", new=AsyncMock(return_value=_review_response())):
        reviewed = _run(candidate)
    assert any("after the contract expires" in f.issue for f in reviewed.review_findings)


def test_auto_renewal_opt_out_deadline_is_computed() -> None:
    candidate = _candidate(
        key_dates=ExtractedKeyDates(effective_date=date(2024, 1, 1), expiration_date=date(2024, 12, 31)),
        renewal_terms=ExtractedRenewalTerms(auto_renew=True, renewal_notice_days=60),
    )
    with patch.object(llm_client, "acompletion", new=AsyncMock(return_value=_review_response())):
        reviewed = _run(candidate)
    assert any("2024-11-01" in f.issue for f in reviewed.review_findings)


def test_high_materiality_obligation_without_consequence_is_flagged() -> None:
    candidate = _candidate()
    insight = review_node._ObligationInsight(
        description="Indemnify for IP claims", responsible_party="Acme Corp", materiality="high"
    )
    with patch.object(
        llm_client,
        "acompletion",
        new=AsyncMock(return_value=_review_response(obligation_analysis=[insight])),
    ):
        reviewed = _run(candidate)
    assert any("no recorded consequence" in f.issue for f in reviewed.review_findings)
    assert any(e.get("stage") == "obligation_analysis" for e in reviewed.extraction_trace)
