"""ContractMapper: translates between the Contract aggregate and the
JSON-serializable dict stored in SQLite.

Kept separate from SqliteContractRepository (single responsibility): the
repository worries about SQL and transactions, this class worries about
shape translation. A different storage format could reuse this mapper
unchanged, or the mapper could be swapped without touching the
repository.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from ...domain.aggregates import Contract
from ...domain.entities import (
    Amendment,
    Approval,
    ApprovalDecision,
    Clause,
    ClauseStatus,
    ClauseType,
    ContractParty,
    ContractReview,
    ContractVersion,
    Notice,
    NoticeType,
    Obligation,
    ObligationStatus,
    PartyRole,
    PartyType,
    PolicyException,
    ReviewDecision,
    SignaturePackage,
    SignatureStatus,
    Signer,
    VersionStatus,
)
from ...domain.value_objects import (
    AccessPolicy,
    Actor,
    Address,
    ApprovalThreshold,
    AuditMetadata,
    BusinessCalendar,
    ClauseReference,
    CommercialTerms,
    ContactDetails,
    ContractId,
    ContractNumber,
    ContractType,
    DeliveryMethod,
    DocumentReference,
    DueDate,
    Jurisdiction,
    KeyDates,
    LegalName,
    LifecycleStatus,
    Money,
    NoticePeriod,
    ObligationId,
    OrganizationalRole,
    PartyId,
    RecurrenceFrequency,
    RecurrenceRule,
    RenewalTerms,
    RiskFactor,
    RiskLevel,
    RiskRating,
    SignatureRequirement,
    TerminationTerms,
    VersionNumber,
)


def _d(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _parse_d(value: Optional[str]) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def _dt(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


class ContractMapper:
    def to_dict(self, contract: Contract) -> dict[str, Any]:
        return {
            "id": str(contract.id),
            "contract_number": str(contract.contract_number),
            "contract_type": str(contract.contract_type),
            "title": contract.title,
            "lifecycle_status": contract.lifecycle_status.value,
            "aggregate_version": contract.aggregate_version,
            "parties": [self._party_to_dict(p) for p in contract.parties],
            "versions": [self._version_to_dict(v) for v in contract.versions],
            "clauses": [self._clause_to_dict(c) for c in contract.clauses],
            "reviews": [self._review_to_dict(r) for r in contract.reviews],
            "approvals": [self._approval_to_dict(a) for a in contract.approvals],
            "signature_packages": [self._package_to_dict(p) for p in contract.signature_packages],
            "obligations": [self._obligation_to_dict(o) for o in contract.obligations],
            "amendments": [self._amendment_to_dict(a) for a in contract.amendments],
            "exceptions": [self._exception_to_dict(e) for e in contract.exceptions],
            "key_dates": self._key_dates_to_dict(contract.key_dates),
            "commercial_terms": self._commercial_terms_to_dict(contract.commercial_terms),
            "renewal_terms": self._renewal_terms_to_dict(contract.renewal_terms),
            "termination_terms": self._termination_terms_to_dict(contract.termination_terms),
            "risk_profile": self._risk_rating_to_dict(contract.risk_profile),
            "access_policy": {
                "allowed_roles": list(contract.access_policy.allowed_roles),
                "confidentiality_level": contract.access_policy.confidentiality_level,
            },
            "audit_metadata": {
                "created_by": contract.audit_metadata.created_by,
                "created_at": _dt(contract.audit_metadata.created_at),
                "updated_by": contract.audit_metadata.updated_by,
                "updated_at": _dt(contract.audit_metadata.updated_at),
            },
        }

    def from_dict(self, data: dict[str, Any]) -> Contract:
        audit = data["audit_metadata"]
        contract = Contract(
            contract_id=ContractId(data["id"]),
            contract_number=ContractNumber(data["contract_number"]),
            contract_type=ContractType.from_stored(data["contract_type"]),
            title=data["title"],
            audit_metadata=AuditMetadata(
                created_by=audit["created_by"],
                created_at=_parse_dt(audit["created_at"]),
                updated_by=audit.get("updated_by"),
                updated_at=_parse_dt(audit.get("updated_at")),
            ),
            key_dates=self._key_dates_from_dict(data["key_dates"]),
            commercial_terms=self._commercial_terms_from_dict(data["commercial_terms"]),
            renewal_terms=self._renewal_terms_from_dict(data["renewal_terms"]),
            termination_terms=self._termination_terms_from_dict(data["termination_terms"]),
            risk_profile=self._risk_rating_from_dict(data.get("risk_profile")),
            access_policy=AccessPolicy(
                allowed_roles=tuple(data["access_policy"]["allowed_roles"]),
                confidentiality_level=data["access_policy"]["confidentiality_level"],
            ),
            lifecycle_status=LifecycleStatus(data["lifecycle_status"]),
        )
        contract.aggregate_version = data["aggregate_version"]
        contract.parties = [self._party_from_dict(p) for p in data["parties"]]
        contract.versions = [self._version_from_dict(v) for v in data["versions"]]
        contract.clauses = [self._clause_from_dict(c) for c in data["clauses"]]
        contract.reviews = [self._review_from_dict(r) for r in data["reviews"]]
        contract.approvals = [self._approval_from_dict(a) for a in data["approvals"]]
        contract.signature_packages = [
            self._package_from_dict(p) for p in data["signature_packages"]
        ]
        contract.obligations = [self._obligation_from_dict(o) for o in data["obligations"]]
        contract.amendments = [self._amendment_from_dict(a) for a in data["amendments"]]
        contract.exceptions = [self._exception_from_dict(e) for e in data["exceptions"]]
        return contract

    # -- parties --------------------------------------------------------

    def _party_to_dict(self, p: ContractParty) -> dict[str, Any]:
        return {
            "party_id": str(p.party_id),
            "legal_name": p.legal_name.value,
            "party_type": p.party_type.value,
            "jurisdiction": {
                "country_code": p.jurisdiction.country_code,
                "subdivision": p.jurisdiction.subdivision,
            },
            "roles": [r.value for r in p.roles],
            "registration_id": p.registration_id,
            "address": (
                {
                    "line1": p.address.line1,
                    "line2": p.address.line2,
                    "city": p.address.city,
                    "state_or_province": p.address.state_or_province,
                    "postal_code": p.address.postal_code,
                    "country_code": p.address.country_code,
                }
                if p.address
                else None
            ),
            "contact": (
                {"email": p.contact.email, "phone": p.contact.phone} if p.contact else None
            ),
        }

    def _party_from_dict(self, d: dict[str, Any]) -> ContractParty:
        address = d.get("address")
        contact = d.get("contact")
        return ContractParty(
            party_id=PartyId(d["party_id"]),
            legal_name=LegalName(d["legal_name"]),
            party_type=PartyType(d["party_type"]),
            jurisdiction=Jurisdiction(**d["jurisdiction"]),
            roles=tuple(PartyRole(r) for r in d["roles"]),
            registration_id=d.get("registration_id"),
            address=Address(**address) if address else None,
            contact=ContactDetails(**contact) if contact else None,
        )

    # -- versions and clauses --------------------------------------------

    def _document_to_dict(self, doc: DocumentReference) -> dict[str, Any]:
        return {"uri": doc.uri, "media_type": doc.media_type, "content_hash": doc.content_hash}

    def _document_from_dict(self, d: dict[str, Any]) -> DocumentReference:
        return DocumentReference(**d)

    def _version_to_dict(self, v: ContractVersion) -> dict[str, Any]:
        return {
            "version_number": v.version_number.value,
            "document": self._document_to_dict(v.document),
            "author_id": v.author_id,
            "created_at": _dt(v.created_at),
            "change_summary": v.change_summary,
            "superseded_version": v.superseded_version.value if v.superseded_version else None,
            "status": v.status.value,
        }

    def _version_from_dict(self, d: dict[str, Any]) -> ContractVersion:
        return ContractVersion(
            version_number=VersionNumber(d["version_number"]),
            document=self._document_from_dict(d["document"]),
            author_id=d["author_id"],
            created_at=_parse_dt(d["created_at"]),
            change_summary=d.get("change_summary"),
            superseded_version=(
                VersionNumber(d["superseded_version"]) if d.get("superseded_version") else None
            ),
            status=VersionStatus(d["status"]),
        )

    def _clause_to_dict(self, c: Clause) -> dict[str, Any]:
        return {
            "clause_id": c.clause_id,
            "heading": c.heading,
            "text_reference": self._document_to_dict(c.text_reference),
            "clause_type": c.clause_type.value,
            "location": c.location,
            "version_number": c.version_number.value,
            "text": c.text,
            "status": c.status.value,
        }

    def _clause_from_dict(self, d: dict[str, Any]) -> Clause:
        return Clause(
            clause_id=d["clause_id"],
            heading=d["heading"],
            text_reference=self._document_from_dict(d["text_reference"]),
            clause_type=ClauseType(d["clause_type"]),
            location=d["location"],
            version_number=VersionNumber(d["version_number"]),
            text=d.get("text"),
            status=ClauseStatus(d["status"]),
        )

    # -- reviews and approvals -------------------------------------------

    def _review_to_dict(self, r: ContractReview) -> dict[str, Any]:
        return {
            "reviewer_id": r.reviewer_id,
            "review_type": r.review_type,
            "version_reviewed": r.version_reviewed.value,
            "decision": r.decision.value,
            "comments": r.comments,
            "conditions": list(r.conditions),
            "decided_at": _dt(r.decided_at),
        }

    def _review_from_dict(self, d: dict[str, Any]) -> ContractReview:
        return ContractReview(
            reviewer_id=d["reviewer_id"],
            review_type=d["review_type"],
            version_reviewed=VersionNumber(d["version_reviewed"]),
            decision=ReviewDecision(d["decision"]),
            comments=d.get("comments"),
            conditions=tuple(d.get("conditions", [])),
            decided_at=_parse_dt(d.get("decided_at")),
        )

    def _approval_to_dict(self, a: Approval) -> dict[str, Any]:
        return {
            "approver_id": a.approver_id,
            "authority_basis": a.authority_basis,
            "version_approved": a.version_approved.value,
            "scope": a.scope,
            "decision": a.decision.value,
            "conditions": list(a.conditions),
            "decided_at": _dt(a.decided_at),
            "expires_at": _dt(a.expires_at),
        }

    def _approval_from_dict(self, d: dict[str, Any]) -> Approval:
        return Approval(
            approver_id=d["approver_id"],
            authority_basis=d["authority_basis"],
            version_approved=VersionNumber(d["version_approved"]),
            scope=d["scope"],
            decision=ApprovalDecision(d["decision"]),
            conditions=tuple(d.get("conditions", [])),
            decided_at=_parse_dt(d.get("decided_at")),
            expires_at=_parse_dt(d.get("expires_at")),
        )

    # -- signature packages -----------------------------------------------

    def _signer_to_dict(self, s: Signer) -> dict[str, Any]:
        return {
            "party_id": str(s.party_id),
            "signer_role": s.signer_role,
            "order": s.order,
            "signed_at": _dt(s.signed_at),
        }

    def _signer_from_dict(self, d: dict[str, Any]) -> Signer:
        return Signer(
            party_id=PartyId(d["party_id"]),
            signer_role=d["signer_role"],
            order=d["order"],
            signed_at=_parse_dt(d.get("signed_at")),
        )

    def _package_to_dict(self, p: SignaturePackage) -> dict[str, Any]:
        return {
            "package_id": p.package_id,
            "version_number": p.version_number.value,
            "signers": [self._signer_to_dict(s) for s in p.signers],
            "provider_reference": p.provider_reference,
            "deadline": _dt(p.deadline),
            "status": p.status.value,
        }

    def _package_from_dict(self, d: dict[str, Any]) -> SignaturePackage:
        return SignaturePackage(
            package_id=d["package_id"],
            version_number=VersionNumber(d["version_number"]),
            signers=[self._signer_from_dict(s) for s in d["signers"]],
            provider_reference=d.get("provider_reference"),
            deadline=_parse_dt(d.get("deadline")),
            status=SignatureStatus(d["status"]),
        )

    # -- obligations --------------------------------------------------------

    def _clause_reference_to_dict(self, ref: ClauseReference) -> dict[str, Any]:
        return {
            "clause_id": ref.clause_id,
            "document": self._document_to_dict(ref.document),
            "location": ref.location,
        }

    def _clause_reference_from_dict(self, d: dict[str, Any]) -> ClauseReference:
        return ClauseReference(
            clause_id=d["clause_id"],
            document=self._document_from_dict(d["document"]),
            location=d["location"],
        )

    def _recurrence_to_dict(self, rule: RecurrenceRule) -> dict[str, Any]:
        return {
            "frequency": rule.frequency.value,
            "interval": rule.interval,
            "count": rule.count,
            "until": _d(rule.until),
        }

    def _recurrence_from_dict(self, d: dict[str, Any]) -> RecurrenceRule:
        return RecurrenceRule(
            frequency=RecurrenceFrequency(d["frequency"]),
            interval=d.get("interval", 1),
            count=d.get("count"),
            until=_parse_d(d.get("until")),
        )

    def _obligation_to_dict(self, o: Obligation) -> dict[str, Any]:
        return {
            "obligation_id": str(o.obligation_id),
            "description": o.description,
            "responsible_party_id": str(o.responsible_party_id),
            "owner_actor_id": o.owner_actor_id,
            "due_date_rule": {
                "value": _d(o.due_date_rule.value),
                "grace_period_days": o.due_date_rule.grace_period_days,
            },
            "source_clause": (
                self._clause_reference_to_dict(o.source_clause) if o.source_clause else None
            ),
            "recurrence": self._recurrence_to_dict(o.recurrence) if o.recurrence else None,
            "evidence_requirements": list(o.evidence_requirements),
            "consequence_of_failure": o.consequence_of_failure,
            "status": o.status.value,
        }

    def _obligation_from_dict(self, d: dict[str, Any]) -> Obligation:
        due = d["due_date_rule"]
        source_clause = d.get("source_clause")
        recurrence = d.get("recurrence")
        return Obligation(
            obligation_id=ObligationId(d["obligation_id"]),
            description=d["description"],
            responsible_party_id=PartyId(d["responsible_party_id"]),
            owner_actor_id=d["owner_actor_id"],
            due_date_rule=DueDate(value=_parse_d(due["value"]), grace_period_days=due["grace_period_days"]),
            source_clause=self._clause_reference_from_dict(source_clause) if source_clause else None,
            recurrence=self._recurrence_from_dict(recurrence) if recurrence else None,
            evidence_requirements=tuple(d.get("evidence_requirements", [])),
            consequence_of_failure=d.get("consequence_of_failure"),
            status=ObligationStatus(d["status"]),
        )

    # -- amendments and exceptions ------------------------------------------

    def _amendment_to_dict(self, a: Amendment) -> dict[str, Any]:
        return {
            "amendment_id": a.amendment_id,
            "modifies_version": a.modifies_version.value,
            "affected_clause_ids": list(a.affected_clause_ids),
            "effective_date": _d(a.effective_date),
            "resulting_version": a.resulting_version.value if a.resulting_version else None,
            "approved": a.approved,
            "signed": a.signed,
        }

    def _amendment_from_dict(self, d: dict[str, Any]) -> Amendment:
        return Amendment(
            amendment_id=d["amendment_id"],
            modifies_version=VersionNumber(d["modifies_version"]),
            affected_clause_ids=tuple(d["affected_clause_ids"]),
            effective_date=_parse_d(d["effective_date"]),
            resulting_version=(
                VersionNumber(d["resulting_version"]) if d.get("resulting_version") else None
            ),
            approved=d.get("approved", False),
            signed=d.get("signed", False),
        )

    def _exception_to_dict(self, e: PolicyException) -> dict[str, Any]:
        return {
            "exception_id": e.exception_id,
            "owner_actor_id": e.owner_actor_id,
            "rationale": e.rationale,
            "scope": e.scope,
            "approver_actor_id": e.approver_actor_id,
            "expires_at": _d(e.expires_at),
        }

    def _exception_from_dict(self, d: dict[str, Any]) -> PolicyException:
        return PolicyException(
            exception_id=d["exception_id"],
            owner_actor_id=d["owner_actor_id"],
            rationale=d["rationale"],
            scope=d["scope"],
            approver_actor_id=d["approver_actor_id"],
            expires_at=_parse_d(d.get("expires_at")),
        )

    # -- contract-level value objects ---------------------------------------

    def _key_dates_to_dict(self, k: KeyDates) -> dict[str, Any]:
        return {
            "effective_date": _d(k.effective_date),
            "execution_date": _d(k.execution_date),
            "expiration_date": _d(k.expiration_date),
            "renewal_deadline": _d(k.renewal_deadline),
            "termination_notice_deadline": _d(k.termination_notice_deadline),
        }

    def _key_dates_from_dict(self, d: dict[str, Any]) -> KeyDates:
        return KeyDates(**{k: _parse_d(v) for k, v in d.items()})

    def _money_to_dict(self, m: Optional[Money]) -> Optional[dict[str, Any]]:
        return {"amount": str(m.amount), "currency": m.currency} if m else None

    def _money_from_dict(self, d: Optional[dict[str, Any]]) -> Optional[Money]:
        return Money(amount=Decimal(d["amount"]), currency=d["currency"]) if d else None

    def _commercial_terms_to_dict(self, c: CommercialTerms) -> dict[str, Any]:
        return {
            "total_value": self._money_to_dict(c.total_value),
            "payment_terms": c.payment_terms,
            "pricing_model": c.pricing_model,
        }

    def _commercial_terms_from_dict(self, d: dict[str, Any]) -> CommercialTerms:
        return CommercialTerms(
            total_value=self._money_from_dict(d.get("total_value")),
            payment_terms=d.get("payment_terms"),
            pricing_model=d.get("pricing_model"),
        )

    def _notice_period_to_dict(self, n: Optional[NoticePeriod]) -> Optional[int]:
        return n.days if n else None

    def _notice_period_from_dict(self, days: Optional[int]) -> Optional[NoticePeriod]:
        return NoticePeriod(days) if days is not None else None

    def _renewal_terms_to_dict(self, r: RenewalTerms) -> dict[str, Any]:
        return {
            "auto_renew": r.auto_renew,
            "renewal_notice_days": self._notice_period_to_dict(r.renewal_notice),
            "renewal_term_length_months": r.renewal_term_length_months,
        }

    def _renewal_terms_from_dict(self, d: dict[str, Any]) -> RenewalTerms:
        return RenewalTerms(
            auto_renew=d.get("auto_renew", False),
            renewal_notice=self._notice_period_from_dict(d.get("renewal_notice_days")),
            renewal_term_length_months=d.get("renewal_term_length_months"),
        )

    def _termination_terms_to_dict(self, t: TerminationTerms) -> dict[str, Any]:
        return {
            "notice_period_days": self._notice_period_to_dict(t.notice_period),
            "cure_period_days": t.cure_period_days,
            "termination_for_convenience": t.termination_for_convenience,
        }

    def _termination_terms_from_dict(self, d: dict[str, Any]) -> TerminationTerms:
        return TerminationTerms(
            notice_period=self._notice_period_from_dict(d.get("notice_period_days")),
            cure_period_days=d.get("cure_period_days", 0),
            termination_for_convenience=d.get("termination_for_convenience", False),
        )

    def _risk_rating_to_dict(self, r: Optional[RiskRating]) -> Optional[dict[str, Any]]:
        if r is None:
            return None
        return {
            "level": r.level.value,
            "factors": [
                {"name": f.name, "weight": str(f.weight), "score": str(f.score)} for f in r.factors
            ],
        }

    def _risk_rating_from_dict(self, d: Optional[dict[str, Any]]) -> Optional[RiskRating]:
        if d is None:
            return None
        return RiskRating(
            level=RiskLevel(d["level"]),
            factors=tuple(
                RiskFactor(name=f["name"], weight=Decimal(f["weight"]), score=Decimal(f["score"]))
                for f in d.get("factors", [])
            ),
        )
