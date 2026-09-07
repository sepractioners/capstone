"""Maps an already-structured JSON or CSV record straight onto
ContractCandidate - no LLM involved. JSON records may carry nested lists
(parties, clauses, ...) matching our field names directly; flat CSV rows
use a `party_1_name` / `party_1_role` / `party_2_name` / ... convention
since CSV has no native way to express a list-of-parties per row.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

from .schema import (
    ContractCandidate,
    ExtractedClause,
    ExtractedCommercialTerms,
    ExtractedKeyDates,
    ExtractedObligation,
    ExtractedParty,
    ExtractedSigner,
)

M = TypeVar("M", bound=BaseModel)


def from_structured_record(
    record: dict[str, Any],
    source_uri: str,
    content_hash: str,
    source_media_type: str,
    source_content_base64: str,
    source_original_filename: Optional[str] = None,
    extraction_trace: list[dict[str, Any]] | None = None,
) -> ContractCandidate:
    """Map one JSON or CSV record to the agent's candidate schema.

    Nested JSON fields are parsed directly; flat CSV party columns are
    handled by the ``party_N_*`` convention in :func:`_extract_parties`.
    """
    return ContractCandidate(
        source_document_hash=content_hash,
        source_uri=source_uri,
        source_media_type=source_media_type,
        source_content_base64=source_content_base64,
        source_original_filename=source_original_filename,
        title=str(record.get("title") or "Untitled Contract"),
        contract_type=str(record.get("contract_type") or "unclassified"),
        parties=_extract_parties(record),
        clauses=_extract_list(record, "clauses", ExtractedClause),
        obligations=_extract_list(record, "obligations", ExtractedObligation),
        signers=_extract_list(record, "signers", ExtractedSigner),
        key_dates=ExtractedKeyDates(
            effective_date=_parse_date(record.get("effective_date")),
            execution_date=_parse_date(record.get("execution_date")),
            expiration_date=_parse_date(record.get("expiration_date")),
        ),
        commercial_terms=ExtractedCommercialTerms(
            total_value_amount=_parse_decimal(record.get("total_value_amount")),
            total_value_currency=(record.get("total_value_currency") or None),
            payment_terms=(record.get("payment_terms") or None),
        ),
        extraction_trace=extraction_trace or [],
    )


def _extract_parties(record: dict[str, Any]) -> list[ExtractedParty]:
    """Read nested parties or numbered party columns from a record."""
    raw_parties = record.get("parties")
    if isinstance(raw_parties, list):
        return [p if isinstance(p, ExtractedParty) else ExtractedParty(**p) for p in raw_parties]

    parties: list[ExtractedParty] = []
    i = 1
    while f"party_{i}_name" in record:
        name = record.get(f"party_{i}_name")
        if name:
            roles_raw = record.get(f"party_{i}_role") or ""
            roles = [r.strip() for r in roles_raw.split(";") if r.strip()]
            parties.append(
                ExtractedParty(
                    legal_name=str(name),
                    roles=roles or ["other"],
                    country_code=record.get(f"party_{i}_country") or "US",
                )
            )
        i += 1
    return parties


def _extract_list(record: dict[str, Any], key: str, model: Type[M]) -> list[M]:
    """Parse a list-valued record field into instances of ``model``."""
    value = record.get(key)
    if not isinstance(value, list):
        return []
    return [v if isinstance(v, model) else model(**v) for v in value]


def _parse_date(value: Any) -> Optional[date]:
    """Parse an ISO-like date value, returning ``None`` when invalid."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _parse_decimal(value: Any) -> Optional[Decimal]:
    """Parse a decimal value, returning ``None`` when invalid."""
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
