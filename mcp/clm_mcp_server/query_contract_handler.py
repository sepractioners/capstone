"""Tenant-scoped orchestration for the contract analysis MCP tool."""
from __future__ import annotations

import sqlite3

from contract_lifecycle.domain.exceptions import NotFoundError
from contract_lifecycle.domain.value_objects import ContractId
from contract_lifecycle.infrastructure.sqlite.contract_mapper import ContractMapper
from query_agent.agent import QueryAnswer, answer

from .dependencies import Dependencies
from .query_payload import ContractQueryRequest

_mapper = ContractMapper()


async def analyze_contracts(
    request: ContractQueryRequest, dependencies: Dependencies, database_path: str
) -> QueryAnswer:
    """Load only organization-owned contracts before asking the query agent."""
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT contract_id FROM contract_tenants WHERE organization_id = ?"
            + (" AND contract_id = ?" if request.contract_id else ""),
            (request.organization_id, request.contract_id)
            if request.contract_id
            else (request.organization_id,),
        ).fetchall()
    finally:
        connection.close()
    contract_ids = [row[0] for row in rows]
    if not contract_ids:
        raise NotFoundError("No contract matched this organization context")
    contracts = [_mapper.to_dict(dependencies.search.get(ContractId(contract_id))) for contract_id in contract_ids]
    return await answer(request.question, contracts, request.contract_id, request.history)