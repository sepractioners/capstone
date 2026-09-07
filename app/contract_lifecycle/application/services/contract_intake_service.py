"""ContractIntakeService: contract intake with parties, type, and drafts.

Depends on the ContractNumberGenerator abstraction rather than a concrete
numbering scheme (dependency inversion) - an organization can inject its
own generator without this service changing.
"""
from __future__ import annotations

from ...domain.aggregates import Contract
from ...domain.services import ContractNumberGenerator
from ...domain.value_objects import ContractNumber
from ..commands import (
    AddContractVersionCommand,
    CreateContractCommand,
    RecordContractTermsCommand,
)
from .application_service import ApplicationService


class ContractIntakeService(ApplicationService):
    def __init__(self, repository, publisher, number_generator: ContractNumberGenerator, seen_commands=None) -> None:
        super().__init__(repository, publisher, seen_commands)
        self._number_generator = number_generator

    def handle_create(self, command: CreateContractCommand) -> Contract:
        contract_number = (
            ContractNumber(command.contract_number)
            if command.contract_number
            else self._number_generator.generate(command.contract_type)
        )
        if self._already_handled(command):
            existing = self._repository.find_by_number(contract_number)
            if existing is not None:
                return existing

        contract = Contract.create_contract(
            contract_number=contract_number,
            contract_type=command.contract_type,
            title=command.title,
            actor=command.actor,
            correlation_id=command.correlation_id,
            parties=list(command.parties),
        )
        self._finish(contract, command)
        return contract

    def handle_record_terms(self, command: RecordContractTermsCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.record_extracted_terms(
            key_dates=command.key_dates,
            renewal_terms=command.renewal_terms,
            termination_terms=command.termination_terms,
        )
        self._finish(contract, command)
        return contract

    def handle_add_version(self, command: AddContractVersionCommand) -> Contract:
        contract = self._repository.get(command.contract_id)
        if self._already_handled(command):
            return contract

        contract.add_version(
            document=command.document,
            author_id=command.author_id,
            actor=command.actor,
            correlation_id=command.correlation_id,
            change_summary=command.change_summary,
        )
        self._finish(contract, command)
        return contract
