"""Reconciles N per-page PageExtraction results into one ContractCandidate.

Two distinct problems, per the design discussion:
- Singleton fields (title, contract_type) that might appear, possibly
  inconsistently, on multiple pages: first-non-null wins, but a genuine
  disagreement is recorded as a FieldConflict rather than silently
  dropped.
- List fields (clauses especially) that are often *duplicated* across
  pages rather than split across them (this dataset's generator repeats
  the whole clause block per page) - deduped by near-exact normalized
  text match, not semantic similarity.
"""
from __future__ import annotations

from typing import Callable, Optional, TypeVar

from .schema import (
    ContractCandidate,
    ExtractedClause,
    ExtractedCommercialTerms,
    ExtractedKeyDates,
    ExtractedObligation,
    ExtractedParty,
    ExtractedSigner,
    FieldConflict,
    PageExtraction,
)

T = TypeVar("T")


def merge_page_extractions(
    pages: list[PageExtraction],
    source_uri: str,
    source_document_hash: str,
    source_media_type: str,
    source_content_base64: str,
    source_original_filename: Optional[str] = None,
) -> ContractCandidate:
    """Combine page-level extractions into one ingest-ready candidate.

    Singleton conflicts are retained in ``field_conflicts``; repeated list
    entries are deduplicated while preserving their first-seen order.
    """
    title, title_conflict = _first_non_null_with_conflict(p.title for p in pages)
    contract_type, type_conflict = _first_non_null_with_conflict(p.contract_type for p in pages)

    conflicts: list[FieldConflict] = []
    if title_conflict:
        conflicts.append(FieldConflict(field="title", candidate_values=title_conflict))
    if type_conflict:
        conflicts.append(FieldConflict(field="contract_type", candidate_values=type_conflict))

    parties = _merge_parties(p for page in pages for p in page.parties)
    clauses = _dedupe_clauses(c for page in pages for c in page.clauses)
    obligations = _dedupe_by_key(
        (o for page in pages for o in page.obligations),
        key=lambda o: (o.description.strip().lower(), o.responsible_party_legal_name.strip().lower()),
    )
    signers = _dedupe_by_key(
        (s for page in pages for s in page.signers),
        key=lambda s: (s.party_legal_name.strip().lower(), s.signer_role.strip().lower()),
    )
    key_dates = _merge_key_dates(p.key_dates for p in pages)
    commercial_terms = _merge_commercial_terms(p.commercial_terms for p in pages)

    return ContractCandidate(
        source_document_hash=source_document_hash,
        source_uri=source_uri,
        source_media_type=source_media_type,
        source_content_base64=source_content_base64,
        source_original_filename=source_original_filename,
        title=title or "Untitled Contract",
        contract_type=contract_type or "unclassified",
        parties=parties,
        clauses=clauses,
        obligations=obligations,
        signers=signers,
        key_dates=key_dates,
        commercial_terms=commercial_terms,
        field_conflicts=conflicts,
    )


def _first_non_null_with_conflict(values) -> tuple[Optional[str], list[str]]:
    """Choose the first distinct non-empty value and report disagreements."""
    seen: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.append(v)
    if not seen:
        return None, []
    if len(seen) == 1:
        return seen[0], []
    return seen[0], seen


def _normalize_text(text: str) -> str:
    """Normalize whitespace and case for near-exact text comparison."""
    return " ".join(text.split()).strip().lower()


def _dedupe_clauses(clauses) -> list[ExtractedClause]:
    """Deduplicate clauses by normalized clause text."""
    seen: dict[str, ExtractedClause] = {}
    for clause in clauses:
        key = _normalize_text(clause.text)
        if key not in seen:
            seen[key] = clause
    return list(seen.values())


def _dedupe_by_key(items, key: Callable[[T], object]) -> list[T]:
    """Deduplicate an iterable by a caller-supplied key."""
    seen: dict[object, T] = {}
    for item in items:
        k = key(item)
        if k not in seen:
            seen[k] = item
    return list(seen.values())


def _merge_parties(parties) -> list[ExtractedParty]:
    """Merge repeated parties and combine their observed metadata."""
    merged: dict[str, ExtractedParty] = {}
    for party in parties:
        key = party.legal_name.strip().lower()
        if key not in merged:
            merged[key] = party
            continue
        existing = merged[key]
        combined_roles = list(dict.fromkeys([*existing.roles, *party.roles]))
        merged[key] = existing.model_copy(
            update={
                "roles": combined_roles,
                "registration_id": existing.registration_id or party.registration_id,
                "subdivision": existing.subdivision or party.subdivision,
            }
        )
    return list(merged.values())


def _merge_key_dates(key_dates_list) -> ExtractedKeyDates:
    """Fill each key date with the first value observed across pages."""
    effective, execution, expiration = None, None, None
    for kd in key_dates_list:
        effective = effective or kd.effective_date
        execution = execution or kd.execution_date
        expiration = expiration or kd.expiration_date
    return ExtractedKeyDates(effective_date=effective, execution_date=execution, expiration_date=expiration)


def _merge_commercial_terms(terms_list) -> ExtractedCommercialTerms:
    """Fill each commercial term with the first value observed across pages."""
    amount, currency, payment_terms = None, None, None
    for t in terms_list:
        amount = amount if amount is not None else t.total_value_amount
        currency = currency or t.total_value_currency
        payment_terms = payment_terms or t.payment_terms
    return ExtractedCommercialTerms(
        total_value_amount=amount, total_value_currency=currency, payment_terms=payment_terms
    )
