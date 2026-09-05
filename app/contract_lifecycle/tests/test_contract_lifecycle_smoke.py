"""End-to-end smoke test for the Contract Lifecycle scaffold.

Exercises intake -> drafting -> review -> approval -> signature ->
execution -> activation -> obligation registration -> termination ->
archival against the real SQLite adapter, and checks optimistic
concurrency on the repository.
"""
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from contract_lifecycle.application.commands import (
    ActivateContractCommand,
    AddContractVersionCommand,
    ApproveContractCommand,
    ArchiveContractCommand,
    CreateContractCommand,
    MarkExecutedCommand,
    RecordReviewCommand,
    RecordSignatureCommand,
    RegisterObligationCommand,
    RequestSignatureCommand,
    StartTerminationCommand,
    SubmitForReviewCommand,
    TerminateContractCommand,
)
from contract_lifecycle.application.services import (
    ContractApprovalService,
    ContractExecutionService,
    ContractIntakeService,
    ContractReviewService,
    ContractSearchService,
    ObligationManagementService,
    TerminationService,
)
from contract_lifecycle.domain.entities import (
    ContractParty,
    ObligationStatus,
    PartyRole,
    PartyType,
    ReviewDecision,
    Signer,
)
from contract_lifecycle.domain.entities import Obligation
from contract_lifecycle.domain.exceptions import ConcurrencyConflict
from contract_lifecycle.domain.services import RoleBasedAuthorityChecker, SequentialContractNumberGenerator, ObligationScheduler
from contract_lifecycle.domain.value_objects import (
    Actor,
    ContractType,
    DocumentReference,
    DueDate,
    Jurisdiction,
    LegalName,
    LifecycleStatus,
    ObligationId,
    OrganizationalRole,
    PartyId,
)
from contract_lifecycle.infrastructure.sqlite import (
    SqliteConnectionFactory,
    SqliteContractRepository,
    SqliteDomainEventPublisher,
)


def _actor(role: str) -> Actor:
    return Actor(actor_id=f"user-{role}", display_name=role, role=OrganizationalRole(role))


def _document(name: str) -> DocumentReference:
    return DocumentReference(uri=f"s3://contracts/{name}.pdf", media_type="application/pdf", content_hash=f"hash-{name}")


class ContractLifecycleSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        self.connection_factory = SqliteConnectionFactory(self.db_path)
        self.repository = SqliteContractRepository(self.connection_factory)
        self.publisher = SqliteDomainEventPublisher(self.connection_factory)
        self.published_events = []
        for event_type in [
            "ContractCreated",
            "ContractApproved",
            "ContractExecuted",
            "ContractActivated",
            "ContractTerminated",
            "ContractArchived",
        ]:
            pass  # subscribed generically below via a catch-all wrapper
        self._subscribe_catch_all()

    def _subscribe_catch_all(self) -> None:
        from contract_lifecycle.domain import events as domain_events

        for name in domain_events.__all__:
            obj = getattr(domain_events, name)
            if isinstance(obj, type):
                self.publisher.subscribe(obj, lambda e: self.published_events.append(e))

    def tearDown(self) -> None:
        os.remove(self.db_path)

    def test_full_lifecycle(self) -> None:
        number_generator = SequentialContractNumberGenerator()
        authority_checker = RoleBasedAuthorityChecker()

        intake = ContractIntakeService(self.repository, self.publisher, number_generator)
        review = ContractReviewService(self.repository, self.publisher)
        approval = ContractApprovalService(self.repository, self.publisher, authority_checker)
        execution = ContractExecutionService(self.repository, self.publisher, authority_checker)
        obligations = ObligationManagementService(self.repository, self.publisher, ObligationScheduler())
        termination = TerminationService(self.repository, self.publisher, authority_checker)
        search = ContractSearchService(self.repository)

        legal_actor = _actor("legal-approver")
        signer_actor = _actor("authorized-signer")
        owner_actor = _actor("contract-owner")

        customer = ContractParty(
            party_id=PartyId.new(),
            legal_name=LegalName("Acme Corp"),
            party_type=PartyType.ORGANIZATION,
            jurisdiction=Jurisdiction("US"),
            roles=(PartyRole.CUSTOMER,),
        )
        supplier = ContractParty(
            party_id=PartyId.new(),
            legal_name=LegalName("Widgets Inc"),
            party_type=PartyType.ORGANIZATION,
            jurisdiction=Jurisdiction("US"),
            roles=(PartyRole.SUPPLIER,),
        )

        contract = intake.handle_create(
            CreateContractCommand(
                idempotency_key="create-1",
                actor=legal_actor,
                correlation_id="corr-1",
                contract_type=ContractType("nda"),
                title="Acme/Widgets NDA",
                parties=[customer, supplier],
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.INTAKE)

        contract = intake.handle_add_version(
            AddContractVersionCommand(
                idempotency_key="version-1",
                actor=legal_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                document=_document("v1"),
                author_id=legal_actor.actor_id,
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.DRAFTING)

        contract = review.handle_submit_for_review(
            SubmitForReviewCommand(
                idempotency_key="submit-1", actor=legal_actor, correlation_id="corr-1", contract_id=contract.id
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.IN_REVIEW)

        contract = review.handle_record_review(
            RecordReviewCommand(
                idempotency_key="review-1",
                actor=legal_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                reviewer_id=legal_actor.actor_id,
                review_type="legal",
                decision=ReviewDecision.APPROVED,
            )
        )

        contract = approval.handle_approve(
            ApproveContractCommand(
                idempotency_key="approve-1",
                actor=legal_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                approver_id=legal_actor.actor_id,
                authority_basis="legal-approver",
                scope="full",
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.APPROVED)

        signers = [
            Signer(party_id=customer.party_id, signer_role="customer", order=1),
            Signer(party_id=supplier.party_id, signer_role="supplier", order=2),
        ]
        contract = execution.handle_request_signature(
            RequestSignatureCommand(
                idempotency_key="sig-req-1",
                actor=legal_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                package_id="pkg-1",
                signers=signers,
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.PENDING_SIGNATURE)

        now = datetime.now(timezone.utc)
        for i, party in enumerate((customer, supplier)):
            contract = execution.handle_record_signature(
                RecordSignatureCommand(
                    idempotency_key=f"sig-rec-{i}",
                    actor=signer_actor,
                    correlation_id="corr-1",
                    contract_id=contract.id,
                    package_id="pkg-1",
                    party_id=party.party_id,
                    signed_at=now,
                )
            )

        contract = execution.handle_mark_executed(
            MarkExecutedCommand(
                idempotency_key="exec-1",
                actor=legal_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                package_id="pkg-1",
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.EXECUTED)

        today = date.today()
        contract = execution.handle_activate(
            ActivateContractCommand(
                idempotency_key="activate-1",
                actor=legal_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                effective_date=today,
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.ACTIVE)

        obligation = Obligation(
            obligation_id=ObligationId.new(),
            description="Deliver quarterly compliance report",
            responsible_party_id=supplier.party_id,
            owner_actor_id=legal_actor.actor_id,
            due_date_rule=DueDate(value=today + timedelta(days=30)),
        )
        contract, occurrences = obligations.handle_register(
            RegisterObligationCommand(
                idempotency_key="obligation-1",
                actor=legal_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                obligation=obligation,
            )
        )
        self.assertEqual(len(contract.obligations), 1)
        self.assertEqual(contract.obligations[0].status, ObligationStatus.ACTIVE)
        self.assertEqual(len(occurrences), 1)

        contract = termination.handle_start_termination(
            StartTerminationCommand(
                idempotency_key="term-start-1",
                actor=owner_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                reason="Mutual agreement",
                requested_effective_date=today,
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.TERMINATING)

        contract = termination.handle_terminate(
            TerminateContractCommand(
                idempotency_key="term-1",
                actor=owner_actor,
                correlation_id="corr-1",
                contract_id=contract.id,
                effective_date=today,
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.TERMINATED)

        contract = termination.handle_archive(
            ArchiveContractCommand(
                idempotency_key="archive-1", actor=owner_actor, correlation_id="corr-1", contract_id=contract.id
            )
        )
        self.assertEqual(contract.lifecycle_status, LifecycleStatus.ARCHIVED)

        reloaded = search.get(contract.id)
        self.assertEqual(reloaded.lifecycle_status, LifecycleStatus.ARCHIVED)
        self.assertEqual(len(reloaded.parties), 2)
        self.assertEqual(len(reloaded.versions), 1)
        self.assertEqual(reloaded.versions[0].document.uri, "s3://contracts/v1.pdf")

        archived = search.list_by_status(LifecycleStatus.ARCHIVED)
        self.assertEqual([str(c.id) for c in archived], [str(contract.id)])

        event_types = {type(e).__name__ for e in self.published_events}
        self.assertIn("ContractCreated", event_types)
        self.assertIn("ContractApproved", event_types)
        self.assertIn("ContractExecuted", event_types)
        self.assertIn("ContractActivated", event_types)
        self.assertIn("ContractTerminated", event_types)
        self.assertIn("ContractArchived", event_types)

    def test_optimistic_concurrency_conflict(self) -> None:
        number_generator = SequentialContractNumberGenerator()
        intake = ContractIntakeService(self.repository, self.publisher, number_generator)
        legal_actor = _actor("legal-approver")

        contract = intake.handle_create(
            CreateContractCommand(
                idempotency_key="create-conc",
                actor=legal_actor,
                correlation_id="corr-2",
                contract_type=ContractType("nda"),
                title="Concurrency Test",
            )
        )

        first_copy = self.repository.get(contract.id)
        second_copy = self.repository.get(contract.id)

        first_copy.add_party(
            ContractParty(
                party_id=PartyId.new(),
                legal_name=LegalName("Party A"),
                party_type=PartyType.ORGANIZATION,
                jurisdiction=Jurisdiction("US"),
                roles=(PartyRole.CUSTOMER,),
            )
        )
        self.repository.save(first_copy)

        second_copy.add_party(
            ContractParty(
                party_id=PartyId.new(),
                legal_name=LegalName("Party B"),
                party_type=PartyType.ORGANIZATION,
                jurisdiction=Jurisdiction("US"),
                roles=(PartyRole.SUPPLIER,),
            )
        )
        with self.assertRaises(ConcurrencyConflict):
            self.repository.save(second_copy)


if __name__ == "__main__":
    unittest.main()
