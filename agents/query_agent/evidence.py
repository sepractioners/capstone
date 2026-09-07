"""Flatten tenant-authorized contract snapshots into citation-ready evidence.

Shared by the query agent's reasoning loop and the read-only ``search_clauses``
MCP tool so both rank the same record shape.
"""
from __future__ import annotations

import json
from typing import Any

EvidenceRecord = dict[str, str]


def flatten_contract_evidence(contract: dict[str, Any]) -> list[EvidenceRecord]:
    """One contract snapshot -> a list of {contract_id, label, evidence} records."""
    contract_id = str(contract.get("id", ""))
    records: list[EvidenceRecord] = []
    for party in contract.get("parties", []):
        records.append({"contract_id": contract_id, "label": "party", "evidence": json.dumps(party, default=str)})
    for clause in contract.get("clauses", []):
        records.append(
            {
                "contract_id": contract_id,
                "label": f"clause:{clause.get('heading', 'unknown')}",
                "evidence": clause.get("text", ""),
            }
        )
    for obligation in contract.get("obligations", []):
        trigger = obligation.get("trigger") or obligation.get("trigger_event") or ""
        consequence = obligation.get("consequence_of_failure") or ""
        label = "obligation"
        if trigger:
            label += f" trigger:{str(trigger)[:60]}"
        if consequence:
            label += f" consequence:{str(consequence)[:60]}"
        records.append(
            {"contract_id": contract_id, "label": label, "evidence": json.dumps(obligation, default=str)}
        )
    key_dates = contract.get("key_dates") or {}
    for deadline in ("renewal_deadline", "termination_notice_deadline"):
        if key_dates.get(deadline):
            records.append(
                {"contract_id": contract_id, "label": f"key_dates:{deadline}", "evidence": str(key_dates[deadline])}
            )
    for field in (
        "key_dates",
        "commercial_terms",
        "renewal_terms",
        "termination_terms",
        "risk_profile",
        "lifecycle_status",
        "title",
        "contract_type",
    ):
        if contract.get(field):
            records.append(
                {"contract_id": contract_id, "label": field, "evidence": json.dumps(contract[field], default=str)}
            )
    return records


def _terms(text: str) -> set[str]:
    return {word.lower().strip(".,:;()\"'") for word in text.split() if len(word) > 2}


def keyword_rank(query: str, records: list[EvidenceRecord], limit: int) -> list[EvidenceRecord]:
    """Deterministic token-overlap ranking - the fallback when embeddings are down."""
    query_terms = _terms(query)
    if not query_terms:
        return records[:limit]
    scored = [
        (sum(term in _terms(f"{record['label']} {record['evidence']}") for term in query_terms), index, record)
        for index, record in enumerate(records)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    ranked = [record for score, _, record in scored if score > 0]
    return (ranked or records)[:limit]
