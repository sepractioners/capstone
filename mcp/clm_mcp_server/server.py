"""Legacy extraction MCP compatibility server.

New callers use ``extraction_mcp_server.server`` for write tools and
``query_mcp_server.server`` for read-only organization analysis.
"""
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

from .dependencies import Dependencies, build_dependencies
from .ingest_contract_handler import ingest_contract as _ingest_contract
from .ingest_payload import ContractCandidate, IngestResult

DEFAULT_DATABASE_PATH = os.environ.get("CLM_DATABASE_PATH", "clm.sqlite3")

app = MCPServer(
    name="clm-mcp-server",
    instructions=(
        "The only sanctioned way to write contract data into the Contract "
        "Lifecycle Management database. ingest_contract fast-forwards a "
        "structured contract extraction through the real domain commands "
        "and invariants; get_contract reads back what was stored; "
        "get_source_document returns the original PDF/JSON/CSV bytes a "
        "contract was extracted from, for verifying extraction quality."
    ),
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
    """Ingest one extracted contract, fast-forwarding it through the real
    lifecycle commands as far as the extracted data legitimately supports.
    Idempotent: re-ingesting the same source_document_hash returns the
    existing contract instead of creating a duplicate."""
    return _ingest_contract(candidate, get_dependencies())


@app.tool()
def get_contract(contract_id: str) -> dict[str, Any]:
    """Read back a previously ingested contract by its id."""
    contract = get_dependencies().search.get(ContractId(contract_id))
    return _mapper.to_dict(contract)


@app.tool()
def get_source_document(contract_id: str) -> dict[str, Any]:
    """Fetch the original source document/record a contract's current
    version was extracted from - a base64-encoded blob plus media type
    and original filename - so extraction quality can be verified against
    the source it came from."""
    deps = get_dependencies()
    contract = deps.search.get(ContractId(contract_id))
    if contract.current_version is None:
        raise NotFoundError(f"Contract {contract_id} has no version, so no source document")

    content_hash = contract.current_version.document.content_hash
    stored = deps.blob_store.get(content_hash)
    if stored is None:
        raise NotFoundError(f"No source document stored for content_hash {content_hash}")

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
