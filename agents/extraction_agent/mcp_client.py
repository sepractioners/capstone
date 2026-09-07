"""Thin client for the write-capable extraction MCP server over stdio.

This is the only place the extraction agent talks to the CLM domain.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .schema import ContractCandidate

logger = logging.getLogger(__name__)


def _server_params(database_path: Optional[str]) -> StdioServerParameters:
    """Build stdio launch parameters for the extraction MCP server."""
    env = dict(os.environ)
    if database_path:
        env["CLM_DATABASE_PATH"] = database_path
    return StdioServerParameters(command=sys.executable, args=["-m", "extraction_mcp_server.server"], env=env)


async def _call_tool(name: str, arguments: dict[str, Any], database_path: Optional[str]) -> dict[str, Any]:
    """Start the MCP server, call one tool, and normalize its response."""
    params = _server_params(database_path)
    logger.debug("MCP call start tool=%s database=%s", name, database_path)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            logger.debug("MCP call complete tool=%s error=%s", name, getattr(result, "is_error", False))
            return _parse_tool_result(name, result)


async def ingest_via_mcp(candidate: ContractCandidate, database_path: Optional[str] = None) -> dict[str, Any]:
    """Send an extracted candidate to the server's ingest tool."""
    return await _call_tool("ingest_contract", {"candidate": candidate.model_dump(mode="json")}, database_path)


async def get_contract_via_mcp(contract_id: str, database_path: Optional[str] = None) -> dict[str, Any]:
    """Fetch a persisted contract by id through the MCP server."""
    return await _call_tool("get_contract", {"contract_id": contract_id}, database_path)


async def get_source_document_via_mcp(contract_id: str, database_path: Optional[str] = None) -> dict[str, Any]:
    """Returns {content_hash, media_type, original_filename, content_base64}
    for the document a contract's current version was extracted from -
    what a UI would call to show the original next to the extraction."""
    return await _call_tool("get_source_document", {"contract_id": contract_id}, database_path)


def _parse_tool_result(tool_name: str, result: Any) -> dict[str, Any]:
    """Raise MCP tool errors and decode structured or text responses."""
    if getattr(result, "is_error", False):
        raise RuntimeError(f"{tool_name} tool call failed: {result}")
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured
    return json.loads(result.content[0].text)
