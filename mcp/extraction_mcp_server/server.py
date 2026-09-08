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
    instructions="""Write-capable CLM ingestion boundary. Persist extracted contracts through domain validation.

WORKFLOW:
1. Extract contract from PDF → build ContractCandidate object
2. Call ingest_contract(candidate) → persists with idempotency check
3. Check IngestResult.already_ingested: True = duplicate, False = new
4. Retrieve IngestResult.contract_id for later queries
5. Use get_contract() to verify parties/obligations were stored correctly
6. Use get_source_document() to re-check source for Admin Console

HEURISTICS FOR EXTRACTION QUALITY:
- responsible_party_legal_name: MUST match a signer (no orphaned obligations)
- field_conflicts: list both interpretations; don't guess conflicting dates
- review_findings: include severity (info/warning/error) for QA transparency
- extraction_trace: breadcrumbs (model, step, decision) for debugging

IDEMPOTENCY:
- Same source_document_hash always returns same contract_id
- Re-ingesting updates contract, doesn't duplicate
- Use source_document_hash to prevent duplicates during bulk uploads

KEY CONSTRAINTS:
- All dates as ISO date objects (YYYY-MM-DD) or None
- Currency required if total_value_amount set
- Obligation party must be a signer
- Empty extraction on non-empty page is a signal to retrieve RAG examples and retry
""",
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
    """Persist an extracted contract candidate through domain validation and invariants.

    HEURISTICS:
    - Idempotent: same source_document_hash returns existing contract (no duplicate)
    - responsible_party_legal_name in each obligation MUST match a signer
    - field_conflicts: if two interpretations exist (e.g., conflicting dates), list both; don't guess
    - review_findings: include severity (info/warning/error) to flag QA issues before ingestion
    - extraction_trace: include breadcrumbs (model, step, decision) for Admin Console debugging

    COMMON PATTERN:
    1. Extract structured data from PDF → ContractCandidate object
    2. Call ingest_contract(candidate)
    3. Check result.already_ingested: if True, contract already in database
    4. Retrieve result.contract_id for later queries (e.g., analyze_contracts)

    ANTI-PATTERNS:
    - Don't include non-signers in obligations' responsible_party (creates orphaned commitments)
    - Don't skip field_conflicts; let domain/human decide
    - Don't guess dates; use None if uncertain
    """
    return _ingest_contract(candidate, get_dependencies())


@app.tool()
def get_contract(contract_id: str) -> dict[str, Any]:
    """Retrieve a stored contract by ID to verify extraction or for Admin Console review.

    USAGE:
    - After ingest_contract(), use returned contract_id to get_contract() and verify parties/obligations
    - Admin Console uses this to display contract details and extraction metadata
    - Check lifecycle_status field: "draft" (new), "active" (in use), "archived"

    RETURNS:
    - Full contract object with parties, obligations, signers, key_dates, commercial_terms, review_findings
    - Includes extraction_trace showing how extraction proceeded
    """
    return _mapper.to_dict(get_dependencies().search.get(ContractId(contract_id)))


@app.tool()
def get_source_document(contract_id: str) -> dict[str, Any]:
    """Retrieve original PDF/document bytes (base64-encoded) for quality verification.

    WHEN TO USE:
    - After extraction, verify extraction accuracy by re-reading source document
    - Admin Console shows source alongside extracted obligations for side-by-side comparison
    - Useful for debugging: "Did extraction miss Section 3?"

    RETURNS:
    - content_base64: full document bytes (base64-encoded)
    - media_type: e.g., "application/pdf"
    - original_filename: filename at upload time
    - content_hash: SHA256 for reproducibility
    """
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