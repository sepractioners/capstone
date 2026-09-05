"""Wires the concrete contract_lifecycle infrastructure and application
services this server drives. Kept in one place so ingest_contract_handler
and server.py both construct the exact same instances (sharing one
repository matters for optimistic concurrency and idempotency caches).
"""
from __future__ import annotations

from dataclasses import dataclass

from contract_lifecycle.application.services import (
    ContractApprovalService,
    ContractExecutionService,
    ContractIntakeService,
    ContractReviewService,
    ContractSearchService,
    ObligationManagementService,
)
from contract_lifecycle.domain.repositories import ContractRepository, DocumentBlobStore, DomainEventPublisher
from contract_lifecycle.domain.services import (
    ObligationScheduler,
    RoleBasedAuthorityChecker,
    SequentialContractNumberGenerator,
)
from contract_lifecycle.infrastructure.sqlite import (
    SqliteConnectionFactory,
    SqliteContractRepository,
    SqliteDocumentBlobStore,
    SqliteDomainEventPublisher,
)

from .system_actor import AUTOMATED_IMPORT_ROLE

# The automated-import actor is granted authority to approve, sign, amend,
# and terminate anything it creates - a deliberate policy for automated
# ingestion, scoped to this one system identity.
_IMPORT_AUTHORITY_ROLES = frozenset({AUTOMATED_IMPORT_ROLE.name})


@dataclass
class Dependencies:
    repository: ContractRepository
    publisher: DomainEventPublisher
    blob_store: DocumentBlobStore
    intake: ContractIntakeService
    review: ContractReviewService
    approval: ContractApprovalService
    execution: ContractExecutionService
    obligations: ObligationManagementService
    search: ContractSearchService


def build_dependencies(database_path: str, authority_roles: frozenset[str] | None = None) -> Dependencies:
    connection_factory = SqliteConnectionFactory(database_path)
    repository = SqliteContractRepository(connection_factory)
    publisher = SqliteDomainEventPublisher(connection_factory)
    blob_store = SqliteDocumentBlobStore(connection_factory)
    roles = authority_roles or _IMPORT_AUTHORITY_ROLES
    authority_checker = RoleBasedAuthorityChecker(
        approver_roles=roles,
        signer_roles=roles,
        amender_roles=roles,
        terminator_roles=roles,
    )
    number_generator = SequentialContractNumberGenerator(prefix="AUTOGEN")

    return Dependencies(
        repository=repository,
        publisher=publisher,
        blob_store=blob_store,
        intake=ContractIntakeService(repository, publisher, number_generator),
        review=ContractReviewService(repository, publisher),
        approval=ContractApprovalService(repository, publisher, authority_checker),
        execution=ContractExecutionService(repository, publisher, authority_checker),
        obligations=ObligationManagementService(repository, publisher, ObligationScheduler()),
        search=ContractSearchService(repository),
    )
