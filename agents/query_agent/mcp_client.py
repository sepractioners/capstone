"""Client for the read-only query MCP server over stdio."""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _server_params(database_path: str | None) -> StdioServerParameters:
    env = dict(os.environ)
    if database_path:
        env["CLM_DATABASE_PATH"] = database_path
    return StdioServerParameters(command=sys.executable, args=["-m", "query_mcp_server.server"], env=env)


async def _call_tool(name: str, arguments: dict[str, Any], database_path: str | None) -> dict[str, Any]:
    async with stdio_client(_server_params(database_path)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
    if getattr(result, "is_error", False):
        raise RuntimeError(f"{name} tool call failed: {result}")
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    return json.loads(result.content[0].text)


async def analyze_via_mcp(
    question: str,
    organization_id: str,
    contract_id: str | None = None,
    database_path: str | None = None,
    history: list[dict[str, str]] | None = None,
    clarify_round: int = 0,
) -> dict[str, Any]:
    """Call the CLM MCP analysis tool with API-authorized organization context.

    ``clarify_round``: consecutive clarification turns this conversation already
    had (0 for a fresh question) - see ``ContractQueryRequest.clarify_round`` /
    ADR-0004 D3. The caller (the orchestrator) owns tracking this and should stop
    calling once it reaches the agent's ``QUERY_CLARIFY_MAX_ROUNDS``.
    """
    return await _call_tool(
        "analyze_contracts",
        {
            "request": {
                "question": question,
                "organization_id": organization_id,
                "contract_id": contract_id,
                "history": history or [],
                "clarify_round": clarify_round,
            }
        },
        database_path,
    )


async def search_via_mcp(
    query: str, organization_id: str, limit: int = 8, database_path: str | None = None
) -> list[dict[str, Any]]:
    """Call the read-only clause search tool with API-authorized organization context."""
    result = await _call_tool(
        "search_clauses",
        {"organization_id": organization_id, "query": query, "limit": limit},
        database_path,
    )
    return result if isinstance(result, list) else result.get("result", [])


async def count_via_mcp(
    organization_id: str,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
    database_path: str | None = None,
) -> dict[str, Any]:
    """Call the deterministic count tool with API-authorized organization context."""
    return await _call_tool(
        "count_contracts",
        {
            "organization_id": organization_id,
            "lifecycle_status": lifecycle_status,
            "contract_type": contract_type,
        },
        database_path,
    )


async def list_via_mcp(
    organization_id: str,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
    detail: str = "summary",
    database_path: str | None = None,
) -> dict[str, Any]:
    """Call the deterministic list tool with API-authorized organization context."""
    return await _call_tool(
        "list_contracts",
        {
            "organization_id": organization_id,
            "lifecycle_status": lifecycle_status,
            "contract_type": contract_type,
            "detail": detail,
        },
        database_path,
    )