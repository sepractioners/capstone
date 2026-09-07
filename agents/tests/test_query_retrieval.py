"""Evidence flattening + ranking, including the offline keyword fallback."""
from __future__ import annotations

from unittest.mock import patch

from query_agent.evidence import flatten_contract_evidence, keyword_rank
from query_agent import retrieval


CONTRACT = {
    "id": "c1",
    "title": "Co-Branding Agreement",
    "parties": [{"legal_name": "Acme Corp"}, {"legal_name": "Beta LLC"}],
    "clauses": [
        {"heading": "Termination", "text": "Either party may terminate on 30 days notice."},
        {"heading": "Payment", "text": "Fees are due monthly."},
    ],
}


def test_flatten_produces_labelled_records() -> None:
    records = flatten_contract_evidence(CONTRACT)
    labels = {r["label"] for r in records}
    assert "party" in labels
    assert "clause:Termination" in labels
    assert all(r["contract_id"] == "c1" for r in records)


def test_keyword_rank_prioritises_matching_records() -> None:
    records = flatten_contract_evidence(CONTRACT)
    top = keyword_rank("how do we terminate the agreement", records, 1)
    assert top[0]["label"] == "clause:Termination"


def test_rank_evidence_falls_back_to_keywords_when_embedding_unavailable() -> None:
    records = flatten_contract_evidence(CONTRACT)
    with patch.object(retrieval, "embed", side_effect=OSError("no ollama")):
        top = retrieval.rank_evidence("terminate the contract", records, 1)
    assert top[0]["label"] == "clause:Termination"
