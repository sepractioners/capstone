"""MCP server exposing only tenant-scoped contract analysis."""
from __future__ import annotations

import os

try:  # mcp>=2.0
    from mcp.server.mcpserver import MCPServer
except ModuleNotFoundError:  # mcp 1.x compatibility
    from mcp.server.fastmcp import FastMCP as MCPServer
from query_agent.agent import answer, get_trace
from query_agent.evidence import flatten_contract_evidence, keyword_rank
from query_agent import portfolio

from clm_mcp_core.dependencies import Dependencies, build_dependencies
from clm_mcp_core.tenant_contracts import contracts_for_organization
from .payload import ContractQueryRequest

DEFAULT_DATABASE_PATH = os.environ.get("CLM_DATABASE_PATH", "clm.sqlite3")
app = MCPServer(
    name="clm-query-mcp-server",
    instructions="Read-only CLM analysis boundary. Analyze only authorized organization contract evidence.",
)
_dependencies: Dependencies | None = None


def get_dependencies() -> Dependencies:
    global _dependencies
    if _dependencies is None:
        _dependencies = build_dependencies(DEFAULT_DATABASE_PATH)
    return _dependencies


@app.tool()
async def analyze_contracts(request: ContractQueryRequest) -> dict:
    """Answer a question over one or all contracts owned by the trusted organization context."""
    contracts = contracts_for_organization(
        get_dependencies(), DEFAULT_DATABASE_PATH, request.organization_id, request.contract_id
    )
    try:
        result = await answer(request.question, contracts, request.contract_id, request.history)
    except Exception as exc:  # noqa: BLE001 - keep the partial trace on failure
        return {
            "question": request.question,
            "error": {"code": "analysis_failed", "message": f"{type(exc).__name__}: {exc}"},
            "grounded": False,
            "debug_trace": get_trace(),
        }
    return {
        "question": request.question,
        **result.model_dump(mode="json"),
        "grounded": True,
        "debug_trace": get_trace(),
    }


def _where(
    lifecycle_status: str | None,
    contract_type: str | None,
    party: str | None,
    effective_year: int | None,
    expiring_within_days: int | None,
    min_value: float | None,
    max_value: float | None,
) -> dict:
    """Assemble a portfolio `where` filter from flat MCP params (drop the empties)."""
    raw = {
        "lifecycle_status": lifecycle_status,
        "contract_type": contract_type,
        "party": party,
        "effective_year": effective_year,
        "expiring_within_days": expiring_within_days,
        "min_value": min_value,
        "max_value": max_value,
    }
    return {key: value for key, value in raw.items() if value not in (None, "")}


@app.tool()
def find_contracts(
    organization_id: str,
    query: str,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
    party: str | None = None,
    effective_year: int | None = None,
    expiring_within_days: int | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
) -> dict:
    """Every tenant-owned contract whose clause / obligation / term text contains
    all the content words in ``query`` (e.g. "liability insurance", "non-compete").

    Complete enumeration, not a ranked sample - use this for "which contracts
    require X" / "do any contracts have X". Deterministic, no LLM.
    """
    contracts = contracts_for_organization(get_dependencies(), DEFAULT_DATABASE_PATH, organization_id)
    where = _where(lifecycle_status, contract_type, party, effective_year, expiring_within_days, min_value, max_value)
    return portfolio.find_contracts(contracts, text=query, where=where)


@app.tool()
def search_clauses(organization_id: str, query: str, limit: int = 8) -> list[dict]:
    """Return the evidence records best matching a query, without calling an LLM.

    Tenant-scoped: only organization-owned contracts are searched. Used by the
    query agent's reasoning loop and available to other read-only callers.
    """
    contracts = contracts_for_organization(get_dependencies(), DEFAULT_DATABASE_PATH, organization_id)
    records = [record for contract in contracts for record in flatten_contract_evidence(contract)]
    return keyword_rank(query, records, max(1, min(limit, 25)))


@app.tool()
def count_contracts(
    organization_id: str,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
    party: str | None = None,
    effective_year: int | None = None,
    expiring_within_days: int | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
) -> dict:
    """Exact contract counts for the trusted organization, optionally filtered.

    Deterministic - no LLM. Returns the total, the matched count for the filter,
    and breakdowns by lifecycle status and contract type over the whole set.
    """
    contracts = contracts_for_organization(get_dependencies(), DEFAULT_DATABASE_PATH, organization_id)
    where = _where(lifecycle_status, contract_type, party, effective_year, expiring_within_days, min_value, max_value)
    return portfolio.count_contracts(contracts, where=where)


@app.tool()
def list_contracts(
    organization_id: str,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
    party: str | None = None,
    effective_year: int | None = None,
    expiring_within_days: int | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
    detail: str = "summary",
) -> dict:
    """List tenant-owned contracts without calling an LLM.

    ``detail="summary"`` returns a compact row per contract; ``detail="full"``
    returns whole contract records (parties, clauses, obligations with
    trigger/consequence, dates, renewal/termination terms) for a small filtered
    set, falling back to summaries with a note when too many match.
    """
    contracts = contracts_for_organization(get_dependencies(), DEFAULT_DATABASE_PATH, organization_id)
    where = _where(lifecycle_status, contract_type, party, effective_year, expiring_within_days, min_value, max_value)
    return portfolio.list_contracts(contracts, where=where, detail=detail)


@app.tool()
def aggregate_contracts(
    organization_id: str,
    measure: str = "count",
    group_by: str = "",
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
    party: str | None = None,
    effective_year: int | None = None,
    expiring_within_days: int | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
) -> dict:
    """Deterministic count / sum / avg / min / max of contract value over a
    filtered set, optionally grouped by lifecycle_status, contract_type, or party.

    ``measure`` is count | sum_value | avg_value | min_value | max_value. All
    money and date arithmetic is done here - no LLM.
    """
    contracts = contracts_for_organization(get_dependencies(), DEFAULT_DATABASE_PATH, organization_id)
    where = _where(lifecycle_status, contract_type, party, effective_year, expiring_within_days, min_value, max_value)
    return portfolio.aggregate_contracts(contracts, measure=measure, group_by=group_by, where=where)


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()