"""Shared CLM domain dependency construction for MCP server processes."""
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
from contract_lifecycle.domain.services import ObligationScheduler, RoleBasedAuthorityChecker, SequentialContractNumberGenerator
from contract_lifecycle.infrastructure.sqlite import SqliteConnectionFactory, SqliteContractRepository, SqliteDocumentBlobStore, SqliteDomainEventPublisher


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


def build_dependencies(database_path: str, authority_roles: frozenset[str] = frozenset({"automated-import"})) -> Dependencies:
    connection_factory = SqliteConnectionFactory(database_path)
    repository = SqliteContractRepository(connection_factory)
    publisher = SqliteDomainEventPublisher(connection_factory)
    blob_store = SqliteDocumentBlobStore(connection_factory)
    authority_checker = RoleBasedAuthorityChecker(
        approver_roles=authority_roles,
        signer_roles=authority_roles,
        amender_roles=authority_roles,
        terminator_roles=authority_roles,
    )
    return Dependencies(
        repository=repository,
        publisher=publisher,
        blob_store=blob_store,
        intake=ContractIntakeService(repository, publisher, SequentialContractNumberGenerator(prefix="AUTOGEN")),
        review=ContractReviewService(repository, publisher),
        approval=ContractApprovalService(repository, publisher, authority_checker),
        execution=ContractExecutionService(repository, publisher, authority_checker),
        obligations=ObligationManagementService(repository, publisher, ObligationScheduler()),
        search=ContractSearchService(repository),
    )