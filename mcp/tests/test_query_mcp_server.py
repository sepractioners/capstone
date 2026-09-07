import base64
import os
import sqlite3
import tempfile

import pytest

from clm_mcp_core.dependencies import build_dependencies
from contract_lifecycle.domain.exceptions import NotFoundError
from clm_mcp_server.ingest_contract_handler import ingest_contract
from clm_mcp_server.ingest_payload import ContractCandidate, ExtractedParty
from query_mcp_server import server


def test_query_mcp_lists_only_organization_owned_contracts(monkeypatch) -> None:
    descriptor, database_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    try:
        dependencies = build_dependencies(database_path)
        candidate = ContractCandidate(
            source_document_hash="query-mcp-listing",
            source_uri="file:///listing.pdf",
            source_media_type="application/pdf",
            source_content_base64=base64.b64encode(b"fixture").decode(),
            title="Listing Agreement",
            contract_type="vendor-agreement",
            parties=[ExtractedParty(legal_name="Acme"), ExtractedParty(legal_name="Vendor")],
        )
        contract_id = ingest_contract(candidate, dependencies).contract_id
        connection = sqlite3.connect(database_path)
        connection.execute("CREATE TABLE contract_tenants (contract_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL)")
        connection.execute("INSERT INTO contract_tenants VALUES (?, ?)", (contract_id, "org-a"))
        connection.commit()
        connection.close()
        monkeypatch.setattr(server, "DEFAULT_DATABASE_PATH", database_path)
        monkeypatch.setattr(server, "get_dependencies", lambda: dependencies)

        listed = server.list_contracts("org-a")
        assert listed["matched"] == 1 and listed["detail"] == "summary"
        assert listed["contracts"][0]["id"] == contract_id
        assert listed["contracts"][0]["title"] == "Listing Agreement"

        full = server.list_contracts("org-a", contract_type="vendor-agreement", detail="full")
        assert full["detail"] == "full"
        assert full["contracts"][0]["parties"][0]["legal_name"] == "Acme"

        counts = server.count_contracts("org-a")
        assert counts["total"] == 1 and counts["matched"] == 1
        assert counts["by_contract_type"] == {"vendor-agreement": 1}
        assert server.count_contracts("org-a", lifecycle_status="active")["matched"] == 0

        found = server.find_contracts("org-a", "listing agreement")
        assert found["matched"] == 1 and found["contracts"][0]["id"] == contract_id
        assert server.find_contracts("org-a", "nonexistent phrase zzz")["matched"] == 0

        agg = server.aggregate_contracts("org-a", measure="count")
        assert agg["matched"] == 1 and agg["value"] == 1
        assert server.aggregate_contracts("org-a", measure="count", party="Acme")["matched"] == 1
        assert server.aggregate_contracts("org-a", measure="count", party="Nobody")["matched"] == 0

        with pytest.raises(NotFoundError, match="No contract matched"):
            server.list_contracts("org-b")
        with pytest.raises(NotFoundError, match="No contract matched"):
            server.count_contracts("org-b")
    finally:
        os.remove(database_path)


def test_search_clauses_is_tenant_scoped_and_needs_no_llm(monkeypatch) -> None:
    descriptor, database_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    try:
        dependencies = build_dependencies(database_path)
        candidate = ContractCandidate(
            source_document_hash="query-mcp-search",
            source_uri="file:///search.pdf",
            source_media_type="application/pdf",
            source_content_base64=base64.b64encode(b"fixture").decode(),
            title="Search Agreement",
            contract_type="vendor-agreement",
            parties=[ExtractedParty(legal_name="Acme"), ExtractedParty(legal_name="Vendor")],
        )
        contract_id = ingest_contract(candidate, dependencies).contract_id
        connection = sqlite3.connect(database_path)
        connection.execute("CREATE TABLE contract_tenants (contract_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL)")
        connection.execute("INSERT INTO contract_tenants VALUES (?, ?)", (contract_id, "org-a"))
        connection.commit()
        connection.close()
        monkeypatch.setattr(server, "DEFAULT_DATABASE_PATH", database_path)
        monkeypatch.setattr(server, "get_dependencies", lambda: dependencies)

        hits = server.search_clauses("org-a", "vendor agreement title", limit=5)
        assert hits and all(hit["contract_id"] == contract_id for hit in hits)
        with pytest.raises(NotFoundError, match="No contract matched"):
            server.search_clauses("org-b", "anything")
    finally:
        os.remove(database_path)