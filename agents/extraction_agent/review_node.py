"""Document-level review: the one reasoning pass over a whole contract.

The per-page extraction is deliberately myopic - it sees one page at a
time.  This node runs after ``merge_page_extractions`` and looks at the
assembled candidate as a whole:

- final ``contract_type`` classification (instead of "first non-null page
  guess wins"),
- an independent full-text read of the high-stakes fields (parties,
  effective/expiration date, total value) that is *voted* against the
  merged values - a disagreement becomes a finding, never a silent
  overwrite,
- deterministic internal-consistency checks (obligations must reference a
  known party, dates must be ordered, required fields for the classified
  type must be present),
- the user directive check (a requested contract type that disagrees with
  the document is a blocker, not a silent change).

Source content stays authoritative: this node flags and classifies, it
never invents parties, dates, or obligations.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Literal

from agent_llm.client import acall
from contract_calc import add_days, days_between
from pydantic import BaseModel, Field

from .schema import ContractCandidate, FieldConflict, PageExtraction, ReviewFinding

logger = logging.getLogger(__name__)

REVIEW_ENABLED = os.environ.get("EXTRACTION_REVIEW_ENABLED", "1") != "0"
REVIEW_TEXT_BUDGET = max(2000, int(os.environ.get("EXTRACTION_REVIEW_TEXT_CHARS", "16000")))

_REVIEW_PROMPT = (
    "You are a senior contracts reviewer. You are given the full text of a contract and a "
    "candidate extraction assembled from a myopic page-by-page pass. Your job is to reason "
    "over the document as a whole and return a structured review.\n"
    "- Classify contract_type with a concise stable label (e.g. affiliate-agreement, "
    "co-branding-agreement, vendor-agreement, amendment) or 'unclassified'.\n"
    "- Independently read the high-stakes fields from the text: party legal names, "
    "effective_date, expiration_date, total_value (amount and currency as written).\n"
    "- Raise a finding for every genuine problem: a missing field the document clearly "
    "supports, an internal contradiction, a party named in an obligation but not in the "
    "party list, or a candidate value that the text does not support. severity is "
    "'info', 'warning', or 'blocker'. Use 'blocker' only for a problem that must be "
    "confirmed by a human before the contract is trusted.\n"
    "- obligation_analysis: for each material commitment or right in the contract, state "
    "the responsible party, the triggering event that starts the clock, the consequence "
    "the text attaches to non-performance (empty if unstated), the basis of any deadline, "
    "and a materiality rating ('high' for money at risk, a termination or indemnity "
    "trigger, or a hard external deadline; 'low' for administrative points) with a one-line "
    "reason. Only describe consequences the text states.\n"
    "- Do not invent facts. If the text does not state something, leave it null and, if it "
    "matters, raise a finding.\n"
    "Return only the schema."
)


class _ObligationInsight(BaseModel):
    description: str = ""
    responsible_party: str = ""
    trigger: str = ""
    consequence: str = ""
    deadline_basis: str = ""
    materiality: Literal["high", "medium", "low"] = "medium"
    materiality_reason: str = ""


class _ReviewResult(BaseModel):
    reasoning: str = ""
    contract_type: str = ""
    parties: list[str] = Field(default_factory=list)
    effective_date: str | None = None
    expiration_date: str | None = None
    total_value: str | None = None
    review_summary: str = ""
    findings: list[ReviewFinding] = Field(default_factory=list)
    obligation_analysis: list[_ObligationInsight] = Field(default_factory=list)


def _candidate_view(candidate: ContractCandidate) -> dict[str, Any]:
    """A compact, JSON-safe snapshot of the merged candidate for the prompt."""
    return {
        "title": candidate.title,
        "contract_type": candidate.contract_type,
        "parties": [{"legal_name": p.legal_name, "roles": p.roles} for p in candidate.parties],
        "clause_headings": [c.heading for c in candidate.clauses],
        "obligations": [
            {
                "description": o.description[:160],
                "responsible_party": o.responsible_party_legal_name,
                "trigger_event": o.trigger_event,
                "consequence_of_failure": o.consequence_of_failure,
            }
            for o in candidate.obligations
        ],
        "key_dates": candidate.key_dates.model_dump(mode="json"),
        "commercial_terms": candidate.commercial_terms.model_dump(mode="json"),
        "renewal_terms": candidate.renewal_terms.model_dump(mode="json"),
        "termination_terms": candidate.termination_terms.model_dump(mode="json"),
        "field_conflicts": [fc.model_dump() for fc in candidate.field_conflicts],
    }


def _date_math_findings(candidate: ContractCandidate) -> list[ReviewFinding]:
    """Checks that need calendar arithmetic (via contract_calc), not just ordering."""
    findings: list[ReviewFinding] = []
    dates = candidate.key_dates
    term_days = days_between(dates.effective_date, dates.expiration_date)

    if term_days is not None and 0 <= term_days < 7:
        findings.append(
            ReviewFinding(
                field="key_dates",
                issue=f"Contract term is only {term_days} day(s) ({dates.effective_date} to {dates.expiration_date}) - likely a date error.",
                severity="warning",
                suggestion="Re-check the effective and expiration dates against the source.",
            )
        )

    # Auto-renewal opt-out deadline = expiration minus the notice window.
    notice = candidate.renewal_terms.renewal_notice_days
    if candidate.renewal_terms.auto_renew and notice and dates.expiration_date:
        computed = add_days(dates.expiration_date, -int(notice))
        stated = dates.renewal_deadline
        if stated and computed and abs((stated - computed).days) > 7:
            findings.append(
                ReviewFinding(
                    field="key_dates",
                    issue=(
                        f"Renewal deadline {stated} does not match expiration {dates.expiration_date} minus the "
                        f"{notice}-day notice window ({computed})."
                    ),
                    severity="warning",
                    suggestion="Confirm which date the renewal clause actually sets.",
                )
            )
        elif not stated and computed:
            findings.append(
                ReviewFinding(
                    field="key_dates",
                    issue=(
                        f"Auto-renewal opt-out notice is due by {computed} "
                        f"(expiration {dates.expiration_date} minus {notice} days)."
                    ),
                    severity="info",
                    suggestion="Record this as key_dates.renewal_deadline.",
                )
            )

    for obligation in candidate.obligations:
        if obligation.due_date and dates.expiration_date and obligation.due_date > dates.expiration_date:
            findings.append(
                ReviewFinding(
                    field="obligations",
                    issue=(
                        f"Obligation '{obligation.description[:80]}' is due {obligation.due_date}, after the "
                        f"contract expires {dates.expiration_date}."
                    ),
                    severity="warning",
                    suggestion="Confirm the due date or a survival clause.",
                )
            )
    return findings


def _deterministic_findings(
    candidate: ContractCandidate, profile: dict[str, Any] | None
) -> list[ReviewFinding]:
    """Structural checks that need no LLM and always run."""
    findings: list[ReviewFinding] = []
    party_names = {p.legal_name.strip().lower() for p in candidate.parties}

    for obligation in candidate.obligations:
        if obligation.responsible_party_legal_name.strip().lower() not in party_names:
            findings.append(
                ReviewFinding(
                    field="obligations",
                    issue=(
                        f"Obligation '{obligation.description[:80]}' names responsible party "
                        f"'{obligation.responsible_party_legal_name}', which is not in the party list."
                    ),
                    severity="warning",
                    suggestion="Confirm the party name or add the missing party.",
                )
            )

    dates = candidate.key_dates
    if dates.effective_date and dates.expiration_date and dates.expiration_date < dates.effective_date:
        findings.append(
            ReviewFinding(
                field="key_dates",
                issue=f"expiration_date {dates.expiration_date} is before effective_date {dates.effective_date}.",
                severity="blocker",
                suggestion="Re-check both dates against the source text.",
            )
        )
    if dates.effective_date and dates.execution_date and dates.effective_date < dates.execution_date:
        findings.append(
            ReviewFinding(
                field="key_dates",
                issue=f"effective_date {dates.effective_date} precedes execution_date {dates.execution_date}.",
                severity="warning",
            )
        )

    if len(candidate.parties) < 2:
        findings.append(
            ReviewFinding(
                field="parties",
                issue=f"Only {len(candidate.parties)} party extracted; a contract normally has at least two.",
                severity="warning",
                suggestion="Re-check the recitals and signature blocks for a second party.",
            )
        )

    for obligation in candidate.obligations:
        has_timing = obligation.due_date is not None or bool(obligation.recurrence_frequency)
        if has_timing and not obligation.trigger_event.strip():
            findings.append(
                ReviewFinding(
                    field="obligations",
                    issue=(
                        f"Obligation '{obligation.description[:80]}' has timing but no recorded "
                        "triggering event."
                    ),
                    severity="info",
                    suggestion="Note what event starts the clock (invoice, notice, anniversary).",
                )
            )

    findings.extend(_date_math_findings(candidate))

    renewal = candidate.renewal_terms
    if renewal.auto_renew and not renewal.renewal_notice_days and not candidate.key_dates.renewal_deadline:
        findings.append(
            ReviewFinding(
                field="renewal_terms",
                issue="Contract auto-renews but no notice window or renewal deadline was extracted.",
                severity="warning",
                suggestion="Check the renewal clause for the opt-out notice period.",
            )
        )

    termination = candidate.termination_terms
    if termination.termination_for_convenience and not termination.notice_period_days:
        findings.append(
            ReviewFinding(
                field="termination_terms",
                issue="Termination for convenience is allowed but no notice period was extracted.",
                severity="warning",
                suggestion="Confirm the notice a party must give to terminate without cause.",
            )
        )

    required = [str(f) for f in (profile or {}).get("required_fields", [])]
    present = {
        "title": bool(candidate.title and candidate.title != "Untitled Contract"),
        "parties": bool(candidate.parties),
        "clauses": bool(candidate.clauses),
        "contract_type": candidate.contract_type not in ("", "unclassified"),
        "key_dates": any(candidate.key_dates.model_dump().values()),
    }
    for field in required:
        if present.get(field) is False:
            findings.append(
                ReviewFinding(
                    field=field,
                    issue=f"Profile '{(profile or {}).get('id', 'unknown')}' expects '{field}' but it is empty.",
                    severity="warning",
                )
            )
    return findings


def _vote_findings(candidate: ContractCandidate, review: _ReviewResult) -> list[ReviewFinding]:
    """Self-consistency: compare the independent full-text read to the merged values."""
    findings: list[ReviewFinding] = []
    merged_parties = {p.legal_name.strip().lower() for p in candidate.parties}
    missing = [name.strip() for name in review.parties if name.strip() and name.strip().lower() not in merged_parties]
    if missing and merged_parties:
        findings.append(
            ReviewFinding(
                field="parties",
                issue="Full-text review found parties the page pass missed: " + ", ".join(sorted(missing)),
                severity="warning",
                suggestion="Add the parties or confirm they are not contract parties.",
            )
        )

    merged_effective = candidate.key_dates.effective_date
    if review.effective_date and merged_effective and str(merged_effective) != review.effective_date[:10]:
        findings.append(
            ReviewFinding(
                field="key_dates",
                issue=f"effective_date disagreement: page pass {merged_effective}, full-text review {review.effective_date}.",
                severity="warning",
            )
        )
    if review.total_value and candidate.commercial_terms.total_value_amount is None:
        findings.append(
            ReviewFinding(
                field="commercial_terms",
                issue=f"Full-text review saw a total value ({review.total_value}) the page pass did not record.",
                severity="warning",
            )
        )
    return findings


def _obligation_analysis_findings(review: _ReviewResult) -> list[ReviewFinding]:
    """Turn the LLM's obligation analysis into findings a human should see."""
    findings: list[ReviewFinding] = []
    for insight in review.obligation_analysis:
        if insight.materiality == "high" and not insight.consequence.strip():
            findings.append(
                ReviewFinding(
                    field="obligations",
                    issue=(
                        f"High-materiality obligation '{insight.description[:80]}' has no recorded "
                        "consequence of failure."
                    ),
                    severity="info",
                    suggestion="Check the clause for a stated penalty, termination right, or indemnity.",
                )
            )
    return findings


async def _run_review(candidate: ContractCandidate, document_text: str, debug: Any = None) -> _ReviewResult | None:
    user = {"candidate": _candidate_view(candidate), "document_text": document_text[:REVIEW_TEXT_BUDGET]}
    parsed, _note = await acall(
        "review", _REVIEW_PROMPT, user, schema=_ReviewResult, recorder=debug, phase="document_review"
    )
    return parsed if isinstance(parsed, _ReviewResult) else None


async def review_candidate(
    candidate: ContractCandidate,
    pages: list[PageExtraction],
    document_text: str,
    profile: dict[str, Any] | None,
    directive: dict[str, Any] | None,
    debug: Any = None,
) -> ContractCandidate:
    """Run the document-level reasoning pass and fold its output into the candidate."""
    findings = _deterministic_findings(candidate, profile)
    review_summary = ""

    if REVIEW_ENABLED and pages:
        review = await _run_review(candidate, document_text, debug)
        if review is not None:
            review_summary = review.review_summary
            findings.extend(review.findings)
            findings.extend(_vote_findings(candidate, review))
            # Adopt a classification only when the page pass produced none.
            if candidate.contract_type in ("", "unclassified") and review.contract_type not in ("", "unclassified"):
                candidate.contract_type = review.contract_type
            elif (
                review.contract_type not in ("", "unclassified")
                and review.contract_type != candidate.contract_type
            ):
                findings.append(
                    ReviewFinding(
                        field="contract_type",
                        issue=(
                            f"Page pass classified '{candidate.contract_type}', document review says "
                            f"'{review.contract_type}'."
                        ),
                        severity="warning",
                        suggestion="Confirm the contract type.",
                    )
                )
            findings.extend(_obligation_analysis_findings(review))
            high = [i for i in review.obligation_analysis if i.materiality == "high"]
            if review.obligation_analysis:
                lines = [
                    f"{i.responsible_party or 'A party'}: {i.description[:100]}"
                    + (f" - trigger: {i.trigger}" if i.trigger else "")
                    + (f" - if missed: {i.consequence}" if i.consequence else "")
                    for i in review.obligation_analysis
                ]
                review_summary = (review_summary + "\n\nWhat matters:\n- " + "\n- ".join(lines)).strip()
            candidate.extraction_trace.append(
                {
                    "stage": "document_review",
                    "status": "completed",
                    "contract_type": candidate.contract_type,
                    "finding_count": len(findings),
                    "reasoning_chars": len(review.reasoning),
                }
            )
            candidate.extraction_trace.append(
                {
                    "stage": "obligation_analysis",
                    "status": "completed",
                    "insight_count": len(review.obligation_analysis),
                    "high_materiality": len(high),
                }
            )
        else:
            candidate.extraction_trace.append({"stage": "document_review", "status": "unavailable"})

    directive = directive or {}
    requested_type = directive.get("requested_contract_type")
    if requested_type and candidate.contract_type not in ("", "unclassified", requested_type):
        candidate.field_conflicts.append(
            FieldConflict(field="contract_type_instruction", candidate_values=[candidate.contract_type, requested_type])
        )
        findings.append(
            ReviewFinding(
                field="contract_type_instruction",
                issue=(
                    f"User asked to extract this as '{requested_type}' but the document reads as "
                    f"'{candidate.contract_type}'."
                ),
                severity="blocker",
                suggestion="A human must confirm the contract type before this is saved.",
            )
        )

    candidate.review_findings = findings
    candidate.review_summary = review_summary
    return candidate


def has_blocker(candidate: ContractCandidate) -> bool:
    """True when a finding requires human confirmation before persistence."""
    return any(finding.severity == "blocker" for finding in candidate.review_findings)
