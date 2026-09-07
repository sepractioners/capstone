"""Tenant-authorized contract lookup shared by read-only query tools."""
from __future__ import annotations

import sqlite3

from contract_lifecycle.domain.exceptions import NotFoundError
from contract_lifecycle.domain.value_objects import ContractId
from contract_lifecycle.infrastructure.sqlite.contract_mapper import ContractMapper

from .dependencies import Dependencies

_mapper = ContractMapper()


def contracts_for_organization(
    dependencies: Dependencies, database_path: str, organization_id: str, contract_id: str | None = None
) -> list[dict]:
    """Return only snapshots owned by an organization, optionally narrowed to one contract."""
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT contract_id FROM contract_tenants WHERE organization_id = ?"
            + (" AND contract_id = ?" if contract_id else ""),
            (organization_id, contract_id) if contract_id else (organization_id,),
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        raise NotFoundError("No contract matched this organization context")
    return [_mapper.to_dict(dependencies.search.get(ContractId(row[0]))) for row in rows]