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
    instructions="""Read-only CLM analysis boundary. Every call is scoped to the
caller's organization - there is no unscoped read. Counts, sums and date
arithmetic are computed by the tools, never by the model.

TOOL ROUTING GUIDE (full taxonomy: agents/query_agent/docs/prompt-templates.md):
1. analyze_contracts: a question that needs reasoning / synthesis across clauses -
   "what are our biggest risks", "how is liability limited across the portfolio",
   "what does the Acme indemnity say". Runs the plan -> gather -> synthesise loop.
2. count_contracts: exact counts / breakdowns - "how many active NDAs", "break
   down by type". Deterministic.
3. list_contracts: the contracts matching a status/type/party/date/value filter.
   detail="full" only for a small filtered set.
4. find_contracts: EVERY contract whose clause/obligation text contains a phrase -
   "which contracts require liability insurance", "do any have a non-compete".
   Complete enumeration. Use this, NOT search_clauses, for "which contracts...".
5. search_clauses: ranked clause snippets - the ONLY tool that returns real
   clause text. Used for one-/few-contract DETAIL ("what does clause X say")
   AND, called once per topic, for a portfolio-wide risk/exposure review -
   find_contracts alone never returns text, only a match count.
6. aggregate_contracts: count|sum|avg|min|max of contract value, optionally
   grouped. The tool does the arithmetic.

find_contracts vs search_clauses: "which contracts mention X" -> find_contracts
(scans every contract, exact matched count, no text). "what does X say" ->
search_clauses (ranked detail, a sample, real text). A risk/exposure review
across several topics needs BOTH per topic - find_contracts to size the
matched set, search_clauses to read it; a topic checked with find_contracts
but never passed to search_clauses has no basis for a claim in the answer.

FILTERS: lifecycle_status and contract_type must be a value that exists in this
organization's portfolio (call count_contracts with no filter to see the
by_lifecycle_status / by_contract_type keys). Pass the stored spelling
("vendor-agreement"), not the user's words ("vendor agreements").

RESULT PRECEDENCE: count_contracts returns `matched` (respects the filter) plus
`by_lifecycle_status` / `by_contract_type` (whole portfolio, ignore the filter).
When a filter is set, `matched` is the answer - never a number from a by_* block.

COVERAGE: when an answer is synthesised from a sample of a larger matched set,
say so and offer the exact count or a narrower filter - never imply it covered
every contract.

ESCALATE: legal advice, market comparison, or predictions are out of scope -
report what the contracts state, not what the user should do.
""",
)
_dependencies: Dependencies | None = None


def get_dependencies() -> Dependencies:
    global _dependencies
    if _dependencies is None:
        _dependencies = build_dependencies(DEFAULT_DATABASE_PATH)
    return _dependencies


@app.tool()
async def analyze_contracts(request: ContractQueryRequest) -> dict:
    """Answer a question over contracts owned by an organization, grounded in contract evidence.

    ROUTING HEURISTICS:
    - contract_id=None: portfolio query ("Do we have non-competes?" "Which contracts expire soon?")
    - contract_id=<uuid>: specific contract ("What are renewal terms?" "Is there an SLA?")
    - history=list: multi-turn conversation ("Tell me more" → use history from prior turns)
    - history=empty/None: one-off question

    PROMPT EXAMPLES → PARAMETERS:
    1. "Do any contracts require liability insurance?"
       → analyze_contracts(question="...", contract_id=None)
    2. "In this contract, what is the renewal date?"
       → analyze_contracts(question="...", contract_id=<uuid>)
    3. "Who are the other parties?" (follow-up to prior answer)
       → analyze_contracts(question="...", history=[prior turns])

    ESCALATION HEURISTICS:
    - If retrieved evidence <50% relevant: return "Not covered in contracts"
    - If multiple contradictory clauses found: return all with confidence scores
    - If question requires inference: flag "Not stated; inferred from..."
    - If the question doesn't project onto any routing template (planner declined
      AND deterministic keyword/facet routing found nothing): the agent never
      guesses a plan - it returns `needs_clarification=true` with a targeted
      question. Pass `clarify_round` = how many consecutive clarification turns
      this conversation already had; the caller should present the terminal
      answer itself (not call again) once the agent's QUERY_CLARIFY_MAX_ROUNDS
      is reached - the agent also gates this itself as a backstop.

    SCOPE BOUNDARIES:
    - IN: Terms, obligations, dates, conditions explicitly stated in contract
    - OUT: Industry practices, regulatory requirements, "should be there"

    RETURNS: {question, answer, needs_clarification, sources[], grounded, debug_trace}
    """
    contracts = contracts_for_organization(
        get_dependencies(), DEFAULT_DATABASE_PATH, request.organization_id, request.contract_id
    )
    try:
        result = await answer(
            request.question, contracts, request.contract_id, request.history, request.clarify_round
        )
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
    """Search for contracts by text and filters. Complete enumeration (ALL matching contracts).

    WHEN TO USE THIS vs. analyze_contracts:
    - find_contracts: "List all contracts with non-compete clauses" (deterministic filter)
    - analyze_contracts: "Are there non-compete clauses?" (reasoning + evidence)

    PROMPT EXAMPLES → PARAMETERS:
    1. "Show contracts expiring in next 90 days"
       → find_contracts(query="expiring", expiring_within_days=90)
    2. "Which vendor contracts are active?"
       → find_contracts(query="", lifecycle_status="active", contract_type="vendor")
    3. "Find all deals with Acme Corp worth >$1M"
       → find_contracts(query="Acme Corp", min_value=1000000)

    KEY HEURISTIC: query parameter is full-text (ALL words must match).
    - "liability insurance" → matches only if both words present
    - "insurance" → matches "liability insurance", "cyber insurance", etc.
    - Empty query + filters → filters alone (e.g., expiring_within_days=90)

    RETURNS: {query, filters, total_matches, contracts: [{id, type, parties, value, ...}]}
    Note: No ranking or sorting - for deterministic discovery only.
    """
    contracts = contracts_for_organization(get_dependencies(), DEFAULT_DATABASE_PATH, organization_id)
    where = _where(lifecycle_status, contract_type, party, effective_year, expiring_within_days, min_value, max_value)
    return portfolio.find_contracts(contracts, text=query, where=where)


@app.tool()
def search_clauses(organization_id: str, query: str, limit: int = 8) -> list[dict]:
    """Search for specific clauses/obligations by keyword (no LLM, fast deterministic ranking).

    WHEN TO USE:
    - Internal step in query agent's reasoning (retrieves evidence before answering)
    - Direct search for specific clause text: "Find all liability caps"
    - Building fact-checking evidence: "What exactly does the contract say about..."
    - Portfolio-wide risk/exposure review: call ONCE PER NAMED TOPIC (e.g.
      "indemnification", "limitation of liability", "termination for
      convenience", "auto-renewal") - each call only returns text for its own
      query; a topic never passed here has no clause text anywhere in scope.

    PROMPT EXAMPLES:
    1. "Show me renewal clauses"
       → search_clauses(query="renewal", limit=10)
    2. "Find termination notice requirements"
       → search_clauses(query="termination notice", limit=5)

    RETURNS: [{contract_id, clause_text, page, type, score}, ...]
    - Ranked by relevance (highest score first)
    - Limit capped at 25 max (prevent token overflow)
    - Default limit=8 sufficient for most queries

    NOTE: This is deterministic keyword ranking, not semantic search.
    For semantic search (similar concepts), use analyze_contracts instead.
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