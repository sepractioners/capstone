import asyncio
import dataclasses
import os
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from clm_mcp_server.dependencies import build_dependencies
from clm_mcp_server.ingest_contract_handler import ingest_contract
from clm_mcp_server.ingest_payload import ContractCandidate, ExtractedParty
from clm_mcp_server.query_contract_handler import analyze_contracts
from clm_mcp_server.query_payload import ContractQueryRequest
from query_agent.agent import QueryAnswer


def _candidate() -> ContractCandidate:
    return ContractCandidate(
        source_document_hash="query-test-hash",
        source_uri="file:///query-test.pdf",
        source_media_type="application/pdf",
        source_content_base64="Zml4dHVyZQ==",
        title="Services Agreement",
        contract_type="services-agreement",
        parties=[ExtractedParty(legal_name="Acme"), ExtractedParty(legal_name="Customer")],
    )


def test_query_handler_exposes_only_requested_organization_contracts() -> None:
    descriptor, database_path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(descriptor)
    try:
        dependencies = build_dependencies(database_path)
        contract_id = ingest_contract(_candidate(), dependencies).contract_id
        connection = sqlite3.connect(database_path)
        connection.execute("CREATE TABLE contract_tenants (contract_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL)")
        connection.execute("INSERT INTO contract_tenants VALUES (?, ?)", (contract_id, "org-a"))
        connection.commit()
        connection.close()
        from query_agent import agent as query_agent_module

        def _resp(parsed):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])

        calls = AsyncMock(side_effect=[
            _resp(query_agent_module._Plan(template="T6_clause_detail", calls=[
                query_agent_module._ToolCall(tool="search_clauses", query="agreement")
            ])),
            _resp(query_agent_module._Interpretation()),
            _resp(QueryAnswer(answer="Grounded answer", confidence=0.9, citations=[])),
            _resp(query_agent_module._Verification(supported=True, adjusted_confidence=0.9)),
        ])
        pinned = dataclasses.replace(query_agent_module.config, plan_tools=True, deterministic_compose=False)
        with patch("agent_llm.client.acompletion", new=calls), patch.object(
            query_agent_module, "config", pinned
        ), patch(
            "query_agent.agent.rank_with_scores", side_effect=lambda q, r, k, c=None: ([(1.0, x) for x in r[:k]], {"mode": "test"})
        ):
            result = asyncio.run(analyze_contracts(
                ContractQueryRequest(question="What agreement is this?", organization_id="org-a"),
                dependencies,
                database_path,
            ))
        assert result.answer == "Grounded answer"
        with pytest.raises(Exception, match="No contract matched"):
            asyncio.run(analyze_contracts(
                ContractQueryRequest(question="What agreement is this?", organization_id="org-b"),
                dependencies,
                database_path,
            ))
    finally:
        os.remove(database_path)