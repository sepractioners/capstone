"""The actual orchestration behind the `ingest_contract` MCP tool.

Fast-forwards a validated ContractCandidate through the real
contract_lifecycle application services (create -> draft -> submit ->
review -> approve -> [sign -> execute -> activate]), stopping at the
first stage the extracted data can't legitimately support rather than
fabricating missing facts. The hardcoded SYSTEM_ACTOR and a derived
timestamp cover *procedural* facts (who/when the import ran); this
handler never invents *substantive* legal facts such as a signature that
wasn't actually found in the source document.

Idempotency is keyed by `source_document_hash`, encoded directly into a
deterministic ContractNumber - re-ingesting the same document is a no-op
that returns the existing contract, reusing ContractReader.find_by_number
rather than adding a new repository method.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime
from typing import Optional

from contract_lifecycle.application.commands import (
    ActivateContractCommand,
    AddContractVersionCommand,
    ApproveContractCommand,
    CreateContractCommand,
    MarkExecutedCommand,
    RecordContractTermsCommand,
    RecordReviewCommand,
    RecordSignatureCommand,
    RegisterObligationCommand,
    RequestSignatureCommand,
    SubmitForReviewCommand,
)
from contract_lifecycle.domain.aggregates import Contract
from contract_lifecycle.domain.entities import (
    Clause,
    ClauseType,
    ContractParty,
    Obligation,
    PartyRole,
    PartyType,
    ReviewDecision,
    Signer,
)
from contract_lifecycle.domain.exceptions import InvalidValueError, InvariantViolation
from contract_lifecycle.domain.value_objects import (
    ContractNumber,
    ContractType,
    DocumentReference,
    DueDate,
    Jurisdiction,
    KeyDates,
    LegalName,
    NoticePeriod,
    ObligationId,
    PartyId,
    RecurrenceFrequency,
    RecurrenceRule,
    RenewalTerms,
    TerminationTerms,
)

from .dependencies import Dependencies
from .ingest_payload import ContractCandidate, ExtractedParty, IngestResult, SkippedStage
from .system_actor import SYSTEM_ACTOR

_COUNTRY_CODE_RE = re.compile(r"^[A-Za-z]{2}$")
_ROLE_VALUES = {r.value for r in PartyRole}
_PARTY_TYPE_VALUES = {t.value for t in PartyType}
_CLAUSE_TYPE_VALUES = {t.value for t in ClauseType}
_RECURRENCE_VALUES = {f.value for f in RecurrenceFrequency}


def ingest_contract(candidate: ContractCandidate, deps: Dependencies) -> IngestResult:
    contract_number = _contract_number_for(candidate.source_document_hash)

    existing = deps.repository.find_by_number(contract_number)
    if existing is not None:
        return IngestResult(
            contract_id=str(existing.id),
            contract_number=str(existing.contract_number),
            lifecycle_status=existing.lifecycle_status.value,
            already_ingested=True,
        )

    # Persist the original source bytes before anything else references
    # them by hash - a UI can later fetch this to verify extraction
    # quality against what was actually in the source document/record.
    deps.blob_store.put(
        content_hash=candidate.source_document_hash,
        media_type=candidate.source_media_type,
        data=base64.b64decode(candidate.source_content_base64),
        original_filename=candidate.source_original_filename,
    )

    correlation_id = f"ingest-{candidate.source_document_hash[:12]}"
    contract_type = _resolve_contract_type(candidate.contract_type)
    parties, skipped = _build_parties(candidate.parties)

    contract = deps.intake.handle_create(
        CreateContractCommand(
            idempotency_key=f"create-{contract_number}",
            actor=SYSTEM_ACTOR,
            correlation_id=correlation_id,
            contract_type=contract_type,
            title=candidate.title,
            parties=parties,
            contract_number=str(contract_number),
        )
    )

    document = DocumentReference(
        uri=candidate.source_uri,
        media_type=candidate.source_media_type,
        content_hash=candidate.source_document_hash,
    )
    contract = deps.intake.handle_add_version(
        AddContractVersionCommand(
            idempotency_key=f"version-{contract_number}",
            actor=SYSTEM_ACTOR,
            correlation_id=correlation_id,
            contract_id=contract.id,
            document=document,
            author_id=SYSTEM_ACTOR.actor_id,
            change_summary="Initial import from source document",
        )
    )

    terms_command = _terms_command(candidate, contract.id, contract_number, correlation_id)
    if terms_command is not None:
        contract = deps.intake.handle_record_terms(terms_command)

    party_index = _party_index(contract.parties)

    for i, extracted_clause in enumerate(candidate.clauses, start=1):
        clause = Clause(
            clause_id=f"{contract_number}-clause-{i}",
            heading=extracted_clause.heading,
            text_reference=document,
            clause_type=_resolve_clause_type(extracted_clause.clause_type),
            location=extracted_clause.page_location,
            version_number=contract.current_version.version_number,
            text=extracted_clause.text,
        )
        contract.add_clause(clause)
    if candidate.clauses:
        deps.repository.save(contract)

    for extracted_obligation in candidate.obligations:
        responsible = party_index.get(extracted_obligation.responsible_party_legal_name.strip().lower())
        if responsible is None or extracted_obligation.due_date is None:
            skipped.append(
                SkippedStage(
                    stage="obligation",
                    reason=f"could not resolve party or due date for '{extracted_obligation.description[:60]}'",
                )
            )
            continue
        obligation = Obligation(
            obligation_id=ObligationId.new(),
            description=extracted_obligation.description,
            responsible_party_id=responsible.party_id,
            owner_actor_id=SYSTEM_ACTOR.actor_id,
            due_date_rule=DueDate(
                value=extracted_obligation.due_date,
                grace_period_days=max(0, extracted_obligation.grace_period_days),
            ),
            recurrence=_resolve_recurrence(
                extracted_obligation.recurrence_frequency, extracted_obligation.recurrence_interval
            ),
            evidence_requirements=tuple(extracted_obligation.evidence_requirements),
            consequence_of_failure=extracted_obligation.consequence_of_failure or None,
        )
        contract, _occurrences = deps.obligations.handle_register(
            RegisterObligationCommand(
                idempotency_key=f"obligation-{contract_number}-{obligation.obligation_id}",
                actor=SYSTEM_ACTOR,
                correlation_id=correlation_id,
                contract_id=contract.id,
                obligation=obligation,
            )
        )

    contract = deps.review.handle_submit_for_review(
        SubmitForReviewCommand(
            idempotency_key=f"submit-{contract_number}",
            actor=SYSTEM_ACTOR,
            correlation_id=correlation_id,
            contract_id=contract.id,
        )
    )
    contract = deps.review.handle_record_review(
        RecordReviewCommand(
            idempotency_key=f"review-{contract_number}",
            actor=SYSTEM_ACTOR,
            correlation_id=correlation_id,
            contract_id=contract.id,
            reviewer_id=SYSTEM_ACTOR.actor_id,
            review_type="automated-import",
            decision=ReviewDecision.APPROVED,
        )
    )

    if len(contract.parties) < 2:
        skipped.append(SkippedStage(stage="approve", reason="fewer than two parties were extracted"))
        return _finalize(contract, skipped, candidate)

    try:
        contract = deps.approval.handle_approve(
            ApproveContractCommand(
                idempotency_key=f"approve-{contract_number}",
                actor=SYSTEM_ACTOR,
                correlation_id=correlation_id,
                contract_id=contract.id,
                approver_id=SYSTEM_ACTOR.actor_id,
                authority_basis="automated-import",
                scope="full",
            )
        )
    except InvariantViolation as e:
        skipped.append(SkippedStage(stage="approve", reason=str(e)))
        return _finalize(contract, skipped, candidate)

    if not candidate.signers:
        skipped.append(SkippedStage(stage="sign", reason="no signers extracted from document"))
        return _finalize(contract, skipped, candidate)

    signer_entities = []
    for s in candidate.signers:
        party = party_index.get(s.party_legal_name.strip().lower())
        if party is not None:
            signer_entities.append(Signer(party_id=party.party_id, signer_role=s.signer_role, order=s.order))

    if not signer_entities:
        skipped.append(SkippedStage(stage="sign", reason="none of the extracted signers matched a known party"))
        return _finalize(contract, skipped, candidate)

    package_id = f"pkg-{contract_number}"
    contract = deps.execution.handle_request_signature(
        RequestSignatureCommand(
            idempotency_key=f"sig-request-{contract_number}",
            actor=SYSTEM_ACTOR,
            correlation_id=correlation_id,
            contract_id=contract.id,
            package_id=package_id,
            signers=signer_entities,
        )
    )

    for s in candidate.signers:
        party = party_index.get(s.party_legal_name.strip().lower())
        signed_at = s.signed_at or candidate.key_dates.execution_date
        if party is None or signed_at is None:
            continue
        contract = deps.execution.handle_record_signature(
            RecordSignatureCommand(
                idempotency_key=f"sig-record-{contract_number}-{party.party_id}",
                actor=SYSTEM_ACTOR,
                correlation_id=correlation_id,
                contract_id=contract.id,
                package_id=package_id,
                party_id=party.party_id,
                signed_at=datetime.combine(signed_at, datetime.min.time()),
            )
        )

    current_package = next(p for p in contract.signature_packages if p.package_id == package_id)
    if not current_package.all_signed():
        skipped.append(SkippedStage(stage="execute", reason="not every signer had an extractable signature date"))
        return _finalize(contract, skipped, candidate)

    contract = deps.execution.handle_mark_executed(
        MarkExecutedCommand(
            idempotency_key=f"execute-{contract_number}",
            actor=SYSTEM_ACTOR,
            correlation_id=correlation_id,
            contract_id=contract.id,
            package_id=package_id,
        )
    )

    if candidate.key_dates.effective_date is None:
        skipped.append(SkippedStage(stage="activate", reason="no effective date extracted"))
        return _finalize(contract, skipped, candidate)

    try:
        contract = deps.execution.handle_activate(
            ActivateContractCommand(
                idempotency_key=f"activate-{contract_number}",
                actor=SYSTEM_ACTOR,
                correlation_id=correlation_id,
                contract_id=contract.id,
                effective_date=candidate.key_dates.effective_date,
            )
        )
    except InvariantViolation as e:
        skipped.append(SkippedStage(stage="activate", reason=str(e)))

    return _finalize(contract, skipped, candidate)


def _finalize(contract: Contract, skipped: list[SkippedStage], candidate: ContractCandidate) -> IngestResult:
    return IngestResult(
        contract_id=str(contract.id),
        contract_number=str(contract.contract_number),
        lifecycle_status=contract.lifecycle_status.value,
        already_ingested=False,
        skipped_stages=skipped,
        field_conflicts=candidate.field_conflicts,
        review_findings=candidate.review_findings,
        review_summary=candidate.review_summary,
        extraction_trace=candidate.extraction_trace,
    )


def _notice_period(days: Optional[int]) -> Optional[NoticePeriod]:
    return NoticePeriod(days) if days is not None and days > 0 else None


def _terms_command(
    candidate: ContractCandidate,
    contract_id,
    contract_number: ContractNumber,
    correlation_id: str,
) -> Optional[RecordContractTermsCommand]:
    """Build the terms command from the extracted candidate, or None when the
    source document stated no renewal / termination / deadline facts."""
    kd = candidate.key_dates
    key_dates = None
    if kd.expiration_date or kd.renewal_deadline or kd.termination_notice_deadline:
        key_dates = KeyDates(
            expiration_date=kd.expiration_date,
            renewal_deadline=kd.renewal_deadline,
            termination_notice_deadline=kd.termination_notice_deadline,
        )

    rt = candidate.renewal_terms
    renewal_terms = None
    if rt.auto_renew or rt.renewal_notice_days or rt.renewal_term_length_months:
        renewal_terms = RenewalTerms(
            auto_renew=rt.auto_renew,
            renewal_notice=_notice_period(rt.renewal_notice_days),
            renewal_term_length_months=rt.renewal_term_length_months,
        )

    tt = candidate.termination_terms
    termination_terms = None
    if tt.notice_period_days or tt.cure_period_days or tt.termination_for_convenience:
        termination_terms = TerminationTerms(
            notice_period=_notice_period(tt.notice_period_days),
            cure_period_days=max(0, tt.cure_period_days),
            termination_for_convenience=tt.termination_for_convenience,
        )

    if key_dates is None and renewal_terms is None and termination_terms is None:
        return None
    return RecordContractTermsCommand(
        idempotency_key=f"terms-{contract_number}",
        actor=SYSTEM_ACTOR,
        correlation_id=correlation_id,
        contract_id=contract_id,
        key_dates=key_dates,
        renewal_terms=renewal_terms,
        termination_terms=termination_terms,
    )


def _contract_number_for(source_document_hash: str) -> ContractNumber:
    return ContractNumber(f"IMPORT-{source_document_hash[:16]}")


def _resolve_contract_type(raw: str) -> ContractType:
    try:
        return ContractType(raw)
    except InvalidValueError:
        ContractType.register(raw)
        return ContractType(raw)


def _resolve_country_code(raw: str) -> str:
    candidate = (raw or "US").strip().upper()
    return candidate if _COUNTRY_CODE_RE.match(candidate) else "US"


def _resolve_party_type(raw: str) -> PartyType:
    normalized = raw.strip().lower()
    return PartyType(normalized) if normalized in _PARTY_TYPE_VALUES else PartyType.ORGANIZATION


def _resolve_roles(raw_roles: list[str]) -> tuple[PartyRole, ...]:
    resolved: list[PartyRole] = []
    for raw in raw_roles:
        normalized = raw.strip().lower().replace(" ", "-")
        if normalized in _ROLE_VALUES and PartyRole(normalized) not in resolved:
            resolved.append(PartyRole(normalized))
    return tuple(resolved) if resolved else (PartyRole.OTHER,)


def _resolve_clause_type(raw: str) -> ClauseType:
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return ClauseType(normalized) if normalized in _CLAUSE_TYPE_VALUES else ClauseType.GENERAL_PROVISION


def _resolve_recurrence(raw: Optional[str], interval: int) -> Optional[RecurrenceRule]:
    if not raw:
        return None
    normalized = raw.strip().lower()
    if normalized not in _RECURRENCE_VALUES:
        return None
    return RecurrenceRule(frequency=RecurrenceFrequency(normalized), interval=max(interval, 1))


def _build_party(p: ExtractedParty) -> ContractParty:
    legal_name = p.legal_name.strip()
    if not legal_name:
        raise InvalidValueError("party has an empty legal_name")
    return ContractParty(
        party_id=PartyId.new(),
        legal_name=LegalName(legal_name),
        party_type=_resolve_party_type(p.party_type),
        jurisdiction=Jurisdiction(country_code=_resolve_country_code(p.country_code), subdivision=p.subdivision),
        roles=_resolve_roles(p.roles),
        registration_id=p.registration_id,
    )


def _build_parties(extracted: list[ExtractedParty]) -> tuple[list[ContractParty], list[SkippedStage]]:
    parties: list[ContractParty] = []
    skipped: list[SkippedStage] = []
    for p in extracted:
        try:
            parties.append(_build_party(p))
        except InvalidValueError as e:
            skipped.append(SkippedStage(stage="party", reason=f"{p.legal_name!r}: {e}"))
    return parties, skipped


def _party_index(parties: list[ContractParty]) -> dict[str, ContractParty]:
    return {p.legal_name.value.strip().lower(): p for p in parties}
