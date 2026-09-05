"""The Contract aggregate root.

`Contract` is the primary aggregate root for the Contract Authoring /
Governance / Signature / Obligation-definition slice of the domain. It
controls every state transition that affects the contract's lifecycle and
is the only object permitted to mutate the entities it owns.

Commands map directly to the ones named in the DDD document's
"Contract Aggregate" section: CreateContract, SubmitForReview,
ApproveContract, RejectContract, RequestSignature, MarkExecuted,
ActivateContract, CreateAmendment, StartTermination, TerminateContract,
ArchiveContract. A handful of supporting methods (adding a party, a draft
version, a review, an obligation) exist because those commands cannot be
satisfied without them.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional, Type, TypeVar

from ..entities import (
    Amendment,
    Approval,
    ApprovalDecision,
    Clause,
    ContractParty,
    ContractReview,
    ContractVersion,
    Obligation,
    PolicyException,
    ReviewDecision,
    SignaturePackage,
    SignatureStatus,
    VersionStatus,
)
from ..events import (
    AmendmentExecuted,
    ContractActivated,
    ContractApproved,
    ContractArchived,
    ContractCreated,
    ContractExecuted,
    ContractExpired,
    ContractRejected,
    ContractReviewCompleted,
    ContractSubmittedForReview,
    ContractTerminated,
    ContractVersionCreated,
    DomainEvent,
    ObligationCreated,
    RenewalInitiated,
    SignatureFailed,
    SignatureRequested,
    TerminationInitiated,
)
from ..exceptions import InvalidStateTransition, InvariantViolation
from ..value_objects import (
    ALLOWED_TRANSITIONS,
    AccessPolicy,
    Actor,
    AuditMetadata,
    CommercialTerms,
    ContractId,
    ContractNumber,
    ContractType,
    KeyDates,
    LifecycleStatus,
    RenewalTerms,
    RiskRating,
    TerminationTerms,
    VersionNumber,
)

TEvent = TypeVar("TEvent", bound=DomainEvent)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Contract:
    """Aggregate root. Contains only the data needed to enforce its
    invariants; document binaries, search indexes, and reporting
    projections live outside the aggregate."""

    def __init__(
        self,
        contract_id: ContractId,
        contract_number: ContractNumber,
        contract_type: ContractType,
        title: str,
        audit_metadata: AuditMetadata,
        parties: Optional[list[ContractParty]] = None,
        key_dates: Optional[KeyDates] = None,
        commercial_terms: Optional[CommercialTerms] = None,
        renewal_terms: Optional[RenewalTerms] = None,
        termination_terms: Optional[TerminationTerms] = None,
        risk_profile: Optional[RiskRating] = None,
        access_policy: Optional[AccessPolicy] = None,
        lifecycle_status: LifecycleStatus = LifecycleStatus.INTAKE,
    ) -> None:
        self.id = contract_id
        self.contract_number = contract_number
        self.contract_type = contract_type
        self.title = title
        self.lifecycle_status = lifecycle_status
        self.parties: list[ContractParty] = list(parties or [])
        self.versions: list[ContractVersion] = []
        self.clauses: list[Clause] = []
        self.reviews: list[ContractReview] = []
        self.approvals: list[Approval] = []
        self.signature_packages: list[SignaturePackage] = []
        self.obligations: list[Obligation] = []
        self.amendments: list[Amendment] = []
        self.exceptions: list[PolicyException] = []
        self.key_dates = key_dates or KeyDates()
        self.commercial_terms = commercial_terms or CommercialTerms()
        self.renewal_terms = renewal_terms or RenewalTerms()
        self.termination_terms = termination_terms or TerminationTerms()
        self.risk_profile = risk_profile
        self.access_policy = access_policy or AccessPolicy()
        self.audit_metadata = audit_metadata

        self.aggregate_version = 0
        # Opaque persistence row-version, set by a repository on load and
        # used for optimistic concurrency checks on save. Distinct from
        # aggregate_version (a count of domain events), since not every
        # mutation raises an event.
        self.version_at_load = 0
        self._pending_events: list[DomainEvent] = []

    # -- construction ------------------------------------------------

    @classmethod
    def create_contract(
        cls,
        contract_number: ContractNumber,
        contract_type: ContractType,
        title: str,
        actor: Actor,
        correlation_id: str,
        parties: Optional[list[ContractParty]] = None,
        contract_id: Optional[ContractId] = None,
        now: Optional[datetime] = None,
    ) -> "Contract":
        moment = now or _utcnow()
        contract = cls(
            contract_id=contract_id or ContractId.new(),
            contract_number=contract_number,
            contract_type=contract_type,
            title=title,
            audit_metadata=AuditMetadata(created_by=actor.actor_id, created_at=moment),
            parties=parties,
        )
        contract._record_event(
            ContractCreated,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            contract_number=str(contract_number),
            contract_type=str(contract_type),
            title=title,
        )
        return contract

    # -- event bookkeeping --------------------------------------------

    def _record_event(
        self,
        event_cls: Type[TEvent],
        *,
        actor: Actor,
        correlation_id: str,
        now: Optional[datetime] = None,
        version_reference: Optional[int] = None,
        **fields,
    ) -> TEvent:
        self.aggregate_version += 1
        event = event_cls(
            event_id=uuid.uuid4().hex,
            aggregate_id=str(self.id),
            aggregate_version=self.aggregate_version,
            occurred_at=now or _utcnow(),
            actor_id=actor.actor_id,
            correlation_id=correlation_id,
            version_reference=version_reference,
            **fields,
        )
        self._pending_events.append(event)
        self.audit_metadata = self.audit_metadata.touched_by(actor.actor_id, event.occurred_at)
        return event

    def pull_events(self) -> list[DomainEvent]:
        """Drain and return events raised since the last pull."""
        events, self._pending_events = self._pending_events, []
        return events

    # -- lifecycle transition guard ------------------------------------

    def _transition(self, new_status: LifecycleStatus) -> None:
        allowed = ALLOWED_TRANSITIONS.get(self.lifecycle_status, frozenset())
        if new_status not in allowed:
            raise InvalidStateTransition(self.lifecycle_status.value, new_status.value)
        self.lifecycle_status = new_status

    @property
    def current_version(self) -> Optional[ContractVersion]:
        return self.versions[-1] if self.versions else None

    # -- parties ---------------------------------------------------------

    def add_party(self, party: ContractParty) -> None:
        if self.lifecycle_status not in (LifecycleStatus.INTAKE, LifecycleStatus.DRAFTING):
            raise InvariantViolation("Parties can only be added during intake or drafting")
        self.parties.append(party)

    # -- drafting / versioning -------------------------------------------

    def add_version(
        self,
        document,
        author_id: str,
        actor: Actor,
        correlation_id: str,
        change_summary: Optional[str] = None,
        now: Optional[datetime] = None,
    ) -> ContractVersion:
        moment = now or _utcnow()
        if self.lifecycle_status == LifecycleStatus.INTAKE:
            self._transition(LifecycleStatus.DRAFTING)
        elif self.lifecycle_status not in (
            LifecycleStatus.DRAFTING,
            LifecycleStatus.REJECTED,
        ):
            raise InvariantViolation(
                f"Cannot create a new version while contract is {self.lifecycle_status.value}"
            )

        previous = self.current_version
        next_number = previous.version_number.next() if previous else VersionNumber(1)
        if previous is not None:
            previous.supersede()

        version = ContractVersion(
            version_number=next_number,
            document=document,
            author_id=author_id,
            created_at=moment,
            change_summary=change_summary,
            superseded_version=previous.version_number if previous else None,
        )
        self.versions.append(version)

        self._record_event(
            ContractVersionCreated,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=next_number.value,
            change_summary=change_summary,
        )
        return version

    def add_clause(self, clause: Clause) -> None:
        if self.current_version is None:
            raise InvariantViolation("Cannot add a clause without a drafted version")
        if clause.version_number != self.current_version.version_number:
            raise InvariantViolation("A clause must belong to the current version")
        self.clauses.append(clause)

    def submit_for_review(self, actor: Actor, correlation_id: str, now: Optional[datetime] = None) -> None:
        if self.current_version is None:
            raise InvariantViolation("Cannot submit for review without a drafted version")
        moment = now or _utcnow()
        self._transition(LifecycleStatus.IN_REVIEW)
        self.current_version.status = VersionStatus.IN_REVIEW
        self._record_event(
            ContractSubmittedForReview,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=self.current_version.version_number.value,
        )

    def add_review(
        self,
        reviewer_id: str,
        review_type: str,
        decision: ReviewDecision,
        actor: Actor,
        correlation_id: str,
        comments: Optional[str] = None,
        conditions: tuple[str, ...] = (),
        now: Optional[datetime] = None,
    ) -> ContractReview:
        if self.lifecycle_status != LifecycleStatus.IN_REVIEW or self.current_version is None:
            raise InvariantViolation("Reviews can only be recorded while a version is in review")
        moment = now or _utcnow()
        review = ContractReview(
            reviewer_id=reviewer_id,
            review_type=review_type,
            version_reviewed=self.current_version.version_number,
            decision=decision,
            comments=comments,
            conditions=conditions,
            decided_at=moment,
        )
        self.reviews.append(review)
        self._record_event(
            ContractReviewCompleted,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=self.current_version.version_number.value,
            reviewer_id=reviewer_id,
            decision=decision.value,
        )
        return review

    # -- governance: approval ---------------------------------------------

    def approve_contract(
        self,
        approver_id: str,
        authority_basis: str,
        scope: str,
        actor: Actor,
        correlation_id: str,
        conditions: tuple[str, ...] = (),
        expires_at: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> Approval:
        if self.current_version is None:
            raise InvariantViolation("Cannot approve a contract with no version")

        # Invariant: at least two legally identified parties before approval.
        if len(self.parties) < 2:
            raise InvariantViolation(
                "A contract must have at least two parties before approval"
            )
        # Invariant: no outstanding or rejected reviews for the current version.
        current_reviews = [
            r for r in self.reviews if r.version_reviewed == self.current_version.version_number
        ]
        if any(r.decision == ReviewDecision.PENDING for r in current_reviews):
            raise InvariantViolation("All required reviews must be completed before approval")
        if any(r.decision == ReviewDecision.REJECTED for r in current_reviews):
            raise InvariantViolation("Cannot approve a version with a rejected review")

        moment = now or _utcnow()
        self._transition(LifecycleStatus.APPROVED)
        self.current_version.status = VersionStatus.APPROVED

        approval = Approval(
            approver_id=approver_id,
            authority_basis=authority_basis,
            version_approved=self.current_version.version_number,
            scope=scope,
            decision=ApprovalDecision.APPROVED,
            conditions=conditions,
            decided_at=moment,
            expires_at=expires_at,
        )
        self.approvals.append(approval)

        self._record_event(
            ContractApproved,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=self.current_version.version_number.value,
            approver_id=approver_id,
        )
        return approval

    def reject_contract(
        self,
        reason: str,
        actor: Actor,
        correlation_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        moment = now or _utcnow()
        self._transition(LifecycleStatus.REJECTED)
        self._record_event(
            ContractRejected,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=self.current_version.version_number.value if self.current_version else None,
            reason=reason,
        )

    def resume_drafting(self, actor: Actor, correlation_id: str, now: Optional[datetime] = None) -> None:
        """Return a rejected contract to drafting so a new version can be authored."""
        self._transition(LifecycleStatus.DRAFTING)

    # -- signature and execution -------------------------------------------

    def request_signature(
        self,
        package_id: str,
        signers,
        actor: Actor,
        correlation_id: str,
        provider_reference: Optional[str] = None,
        deadline: Optional[datetime] = None,
        now: Optional[datetime] = None,
    ) -> SignaturePackage:
        if self.current_version is None:
            raise InvariantViolation("Cannot request signature without an approved version")

        moment = now or _utcnow()
        valid_approval = any(
            a.is_valid_for(self.current_version.version_number, moment) for a in self.approvals
        )
        if not valid_approval:
            raise InvariantViolation(
                "No valid, unexpired approval exists for the current contract version"
            )

        self._transition(LifecycleStatus.PENDING_SIGNATURE)
        package = SignaturePackage(
            package_id=package_id,
            version_number=self.current_version.version_number,
            signers=list(signers),
            provider_reference=provider_reference,
            deadline=deadline,
            status=SignatureStatus.SENT,
        )
        self.signature_packages.append(package)

        self._record_event(
            SignatureRequested,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=self.current_version.version_number.value,
            package_id=package_id,
        )
        return package

    def _find_signature_package(self, package_id: str) -> SignaturePackage:
        for package in self.signature_packages:
            if package.package_id == package_id:
                return package
        raise InvariantViolation(f"Unknown signature package: {package_id}")

    def record_signer_signed(
        self,
        package_id: str,
        party_id,
        signed_at: datetime,
    ) -> SignaturePackage:
        package = self._find_signature_package(package_id)
        for signer in package.signers:
            if signer.party_id == party_id:
                signer.signed_at = signed_at
                break
        else:
            raise InvariantViolation(f"{party_id} is not a signer on package {package_id}")
        if package.all_signed():
            package.status = SignatureStatus.COMPLETED
        else:
            package.status = SignatureStatus.PARTIALLY_SIGNED
        return package

    def record_signature_failure(
        self,
        package_id: str,
        reason: str,
        actor: Actor,
        correlation_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        moment = now or _utcnow()
        package = self._find_signature_package(package_id)
        package.status = SignatureStatus.FAILED
        self._transition(LifecycleStatus.SIGNATURE_FAILED)
        self._record_event(
            SignatureFailed,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=package.version_number.value,
            package_id=package_id,
            reason=reason,
        )

    def retry_signature(self, actor: Actor, correlation_id: str, now: Optional[datetime] = None) -> None:
        self._transition(LifecycleStatus.PENDING_SIGNATURE)

    def mark_executed(self, package_id: str, actor: Actor, correlation_id: str, now: Optional[datetime] = None) -> None:
        if self.current_version is None:
            raise InvariantViolation("Cannot execute a contract with no version")
        package = self._find_signature_package(package_id)
        if not package.all_signed():
            raise InvariantViolation("Cannot mark executed: not all signers have signed")

        moment = now or _utcnow()
        self._transition(LifecycleStatus.EXECUTED)
        self.current_version.mark_executed()
        for clause in self.clauses:
            if clause.version_number == self.current_version.version_number:
                clause.lock()
        self.key_dates = KeyDates(
            effective_date=self.key_dates.effective_date,
            execution_date=moment.date(),
            expiration_date=self.key_dates.expiration_date,
            renewal_deadline=self.key_dates.renewal_deadline,
            termination_notice_deadline=self.key_dates.termination_notice_deadline,
        )
        self._record_event(
            ContractExecuted,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=self.current_version.version_number.value,
        )

    def activate_contract(
        self,
        effective_date: date,
        actor: Actor,
        correlation_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        moment = now or _utcnow()
        if effective_date > moment.date():
            raise InvariantViolation("A contract cannot become active before its effective date")
        self._transition(LifecycleStatus.ACTIVE)
        self.key_dates = KeyDates(
            effective_date=effective_date,
            execution_date=self.key_dates.execution_date,
            expiration_date=self.key_dates.expiration_date,
            renewal_deadline=self.key_dates.renewal_deadline,
            termination_notice_deadline=self.key_dates.termination_notice_deadline,
        )
        self._record_event(
            ContractActivated,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            effective_date=effective_date,
        )

    # -- obligations (definitions only; scheduling lives in Obligation Management) --

    def register_obligation(
        self,
        obligation: Obligation,
        actor: Actor,
        correlation_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        self.obligations.append(obligation)
        self._record_event(
            ObligationCreated,
            actor=actor,
            correlation_id=correlation_id,
            now=now,
            obligation_id=str(obligation.obligation_id),
        )

    # -- amendments -----------------------------------------------------------

    def create_amendment(
        self,
        amendment_id: str,
        affected_clause_ids: tuple[str, ...],
        effective_date: date,
        actor: Actor,
        correlation_id: str,
        post_termination_permitted: bool = False,
    ) -> Amendment:
        if self.lifecycle_status not in (LifecycleStatus.ACTIVE,):
            if not (
                self.lifecycle_status in (LifecycleStatus.TERMINATED, LifecycleStatus.EXPIRED)
                and post_termination_permitted
            ):
                raise InvariantViolation(
                    "A terminated or expired contract cannot receive ordinary amendments"
                )
        if self.current_version is None:
            raise InvariantViolation("Cannot amend a contract with no executed version")

        amendment = Amendment(
            amendment_id=amendment_id,
            modifies_version=self.current_version.version_number,
            affected_clause_ids=affected_clause_ids,
            effective_date=effective_date,
        )
        self.amendments.append(amendment)
        return amendment

    def execute_amendment(
        self,
        amendment_id: str,
        document,
        author_id: str,
        actor: Actor,
        correlation_id: str,
        now: Optional[datetime] = None,
    ) -> Amendment:
        amendment = next((a for a in self.amendments if a.amendment_id == amendment_id), None)
        if amendment is None:
            raise InvariantViolation(f"Unknown amendment: {amendment_id}")
        if not (amendment.approved and amendment.signed):
            raise InvariantViolation("Amendment must be approved and signed before execution")

        moment = now or _utcnow()
        new_version = self.add_version(
            document=document,
            author_id=author_id,
            actor=actor,
            correlation_id=correlation_id,
            change_summary=f"Amendment {amendment_id}",
            now=moment,
        )
        new_version.status = VersionStatus.EXECUTED
        amendment.resulting_version = new_version.version_number

        self._record_event(
            AmendmentExecuted,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            version_reference=new_version.version_number.value,
            amendment_id=amendment_id,
            resulting_version=new_version.version_number.value,
        )
        return amendment

    # -- renewal ----------------------------------------------------------

    def initiate_renewal(self, actor: Actor, correlation_id: str, now: Optional[datetime] = None) -> None:
        moment = now or _utcnow()
        self._transition(LifecycleStatus.RENEWED)
        self._record_event(RenewalInitiated, actor=actor, correlation_id=correlation_id, now=moment)

    def complete_renewal(self, actor: Actor, correlation_id: str, now: Optional[datetime] = None) -> None:
        self._transition(LifecycleStatus.ACTIVE)

    # -- termination and expiry --------------------------------------------

    def start_termination(
        self,
        reason: str,
        requested_effective_date: date,
        actor: Actor,
        correlation_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        moment = now or _utcnow()
        notice = self.termination_terms.notice_period
        if notice is not None:
            earliest_allowed = moment.date()
            from datetime import timedelta

            earliest_allowed = moment.date() + timedelta(days=notice.days)
            if requested_effective_date < earliest_allowed:
                raise InvariantViolation(
                    f"Termination effective date must respect the {notice.days}-day notice period"
                )
        self._transition(LifecycleStatus.TERMINATING)
        self.key_dates = KeyDates(
            effective_date=self.key_dates.effective_date,
            execution_date=self.key_dates.execution_date,
            expiration_date=self.key_dates.expiration_date,
            renewal_deadline=self.key_dates.renewal_deadline,
            termination_notice_deadline=requested_effective_date,
        )
        self._record_event(
            TerminationInitiated,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            reason=reason,
        )

    def terminate_contract(
        self,
        effective_date: date,
        actor: Actor,
        correlation_id: str,
        now: Optional[datetime] = None,
    ) -> None:
        moment = now or _utcnow()
        self._transition(LifecycleStatus.TERMINATED)
        self._record_event(
            ContractTerminated,
            actor=actor,
            correlation_id=correlation_id,
            now=moment,
            effective_date=effective_date,
        )

    def expire_contract(self, actor: Actor, correlation_id: str, now: Optional[datetime] = None) -> None:
        moment = now or _utcnow()
        self._transition(LifecycleStatus.EXPIRED)
        self._record_event(ContractExpired, actor=actor, correlation_id=correlation_id, now=moment)

    def archive_contract(self, actor: Actor, correlation_id: str, now: Optional[datetime] = None) -> None:
        moment = now or _utcnow()
        self._transition(LifecycleStatus.ARCHIVED)
        self._record_event(ContractArchived, actor=actor, correlation_id=correlation_id, now=moment)
