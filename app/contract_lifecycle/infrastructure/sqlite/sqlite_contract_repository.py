"""SqliteContractRepository: the SQLite implementation of ContractRepository.

Depends on SqliteConnectionFactory, ContractSchema, and ContractMapper via
constructor injection rather than constructing them itself, so each can be
swapped or unit-tested independently (dependency inversion). It is fully
substitutable for any other ContractRepository implementation (Liskov
substitution) - callers never need to know it is backed by SQLite.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from ...domain.aggregates import Contract
from ...domain.events import DomainEvent
from ...domain.exceptions import ConcurrencyConflict, NotFoundError
from ...domain.repositories import ContractRepository
from ...domain.value_objects import ContractId, ContractNumber, LifecycleStatus
from .connection_factory import SqliteConnectionFactory
from .contract_mapper import ContractMapper
from .contract_schema import ContractSchema

_EVENT_FIELDS_EXCLUDED_FROM_TOP_LEVEL = {
    "event_id",
    "aggregate_id",
    "aggregate_version",
    "occurred_at",
}


class SqliteContractRepository(ContractRepository):
    def __init__(
        self,
        connection_factory: SqliteConnectionFactory,
        schema: Optional[ContractSchema] = None,
        mapper: Optional[ContractMapper] = None,
    ) -> None:
        self._connections = connection_factory
        self._mapper = mapper or ContractMapper()
        connection = self._connections.connect()
        try:
            (schema or ContractSchema()).create_all(connection)
        finally:
            connection.close()

    def next_identity(self) -> ContractId:
        return ContractId.new()

    def _load(self, row) -> Contract:
        contract = self._mapper.from_dict(json.loads(row["data"]))
        contract.version_at_load = row["row_version"]
        return contract

    def get(self, contract_id: ContractId) -> Contract:
        connection = self._connections.connect()
        try:
            row = connection.execute(
                "SELECT data, row_version FROM contracts WHERE id = ?", (str(contract_id),)
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise NotFoundError(f"No contract found with id {contract_id}")
        return self._load(row)

    def find_by_number(self, contract_number: ContractNumber) -> Optional[Contract]:
        connection = self._connections.connect()
        try:
            row = connection.execute(
                "SELECT data, row_version FROM contracts WHERE contract_number = ?",
                (str(contract_number),),
            ).fetchone()
        finally:
            connection.close()
        return self._load(row) if row else None

    def list_by_status(self, status: LifecycleStatus) -> list[Contract]:
        connection = self._connections.connect()
        try:
            rows = connection.execute(
                "SELECT data, row_version FROM contracts WHERE lifecycle_status = ?", (status.value,)
            ).fetchall()
        finally:
            connection.close()
        return [self._load(row) for row in rows]

    def save(self, contract: Contract) -> list[DomainEvent]:
        events = contract.pull_events()
        payload = json.dumps(self._mapper.to_dict(contract))
        now = datetime.now(timezone.utc).isoformat()

        connection = self._connections.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT row_version FROM contracts WHERE id = ?",
                (str(contract.id),),
            ).fetchone()

            if row is None:
                new_row_version = 1
                connection.execute(
                    """
                    INSERT INTO contracts
                        (id, contract_number, lifecycle_status, row_version, data, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(contract.id),
                        str(contract.contract_number),
                        contract.lifecycle_status.value,
                        new_row_version,
                        payload,
                        now,
                    ),
                )
            else:
                if row["row_version"] != contract.version_at_load:
                    connection.execute("ROLLBACK")
                    raise ConcurrencyConflict(
                        str(contract.id), contract.version_at_load, row["row_version"]
                    )
                new_row_version = row["row_version"] + 1
                cursor = connection.execute(
                    """
                    UPDATE contracts
                    SET lifecycle_status = ?, row_version = ?, data = ?, updated_at = ?
                    WHERE id = ? AND row_version = ?
                    """,
                    (
                        contract.lifecycle_status.value,
                        new_row_version,
                        payload,
                        now,
                        str(contract.id),
                        contract.version_at_load,
                    ),
                )
                if cursor.rowcount != 1:
                    connection.execute("ROLLBACK")
                    raise ConcurrencyConflict(
                        str(contract.id), contract.version_at_load, new_row_version
                    )

            for event in events:
                event_dict = {
                    k: v for k, v in event.__dict__.items() if k not in _EVENT_FIELDS_EXCLUDED_FROM_TOP_LEVEL
                }
                connection.execute(
                    """
                    INSERT INTO domain_events
                        (event_id, aggregate_id, aggregate_version, event_type, occurred_at, data)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.aggregate_id,
                        event.aggregate_version,
                        type(event).__name__,
                        event.occurred_at.isoformat(),
                        json.dumps(event_dict, default=str),
                    ),
                )

            connection.commit()
        finally:
            connection.close()

        contract.version_at_load = new_row_version
        return events
