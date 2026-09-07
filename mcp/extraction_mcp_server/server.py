"""MCP server exposing only extraction ingestion tools."""
from __future__ import annotations

import base64
import os
from typing import Any

from contract_lifecycle.domain.exceptions import NotFoundError
from contract_lifecycle.domain.value_objects import ContractId
from contract_lifecycle.infrastructure.sqlite.contract_mapper import ContractMapper
try:  # mcp>=2.0
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError:  # mcp 1.x compatibility
    from mcp.server.fastmcp import FastMCP as MCPServer

from clm_mcp_core.dependencies import Dependencies, build_dependencies
from clm_mcp_server.ingest_contract_handler import ingest_contract as _ingest_contract
from clm_mcp_server.ingest_payload import ContractCandidate, IngestResult

DEFAULT_DATABASE_PATH = os.environ.get("CLM_DATABASE_PATH", "clm.sqlite3")
app = MCPServer(
    name="clm-extraction-mcp-server",
    instructions="Write-capable CLM ingestion boundary for extracted contract candidates.",
)
_dependencies: Dependencies | None = None
_mapper = ContractMapper()


def get_dependencies() -> Dependencies:
    global _dependencies
    if _dependencies is None:
        _dependencies = build_dependencies(DEFAULT_DATABASE_PATH)
    return _dependencies


@app.tool()
def ingest_contract(candidate: ContractCandidate) -> IngestResult:
    """Persist an extracted candidate through domain commands and invariants."""
    return _ingest_contract(candidate, get_dependencies())


@app.tool()
def get_contract(contract_id: str) -> dict[str, Any]:
    """Read back a contract produced by the extraction ingestion workflow."""
    return _mapper.to_dict(get_dependencies().search.get(ContractId(contract_id)))


@app.tool()
def get_source_document(contract_id: str) -> dict[str, Any]:
    """Fetch original source bytes to verify a completed extraction."""
    dependencies = get_dependencies()
    contract = dependencies.search.get(ContractId(contract_id))
    if contract.current_version is None:
        raise NotFoundError(f"Contract {contract_id} has no source version")
    stored = dependencies.blob_store.get(contract.current_version.document.content_hash)
    if stored is None:
        raise NotFoundError(f"No source document found for contract {contract_id}")
    return {
        "content_hash": stored.content_hash,
        "media_type": stored.media_type,
        "original_filename": stored.original_filename,
        "content_base64": base64.b64encode(stored.data).decode("ascii"),
    }


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()