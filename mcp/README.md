# CLM MCP Servers

The `mcp` package provides two sanctioned agent boundaries over shared CLM dependency and tenant-lookup infrastructure in `clm_mcp_core`.

## Tools

### Extraction MCP: `extraction_mcp_server.server`

- `ingest_contract`: persist an extracted candidate through lifecycle services and invariants.
- `get_contract` and `get_source_document`: verify a contract or original source produced by extraction.
- Write-capable and used only by `extraction_agent`.

### Query MCP: `query_mcp_server.server`

- `count_contracts(organization_id, lifecycle_status?, contract_type?)`: exact contract counts and breakdowns by status/type. Deterministic, no LLM.
- `list_contracts(organization_id, lifecycle_status?, contract_type?, detail?)`: the matching contracts - `detail="summary"` rows or `detail="full"` whole contract records (parties, clauses, obligations with trigger/consequence, dates, renewal/termination terms) for a small filtered set. Deterministic, no LLM.
- `find_contracts(organization_id, query, ...filters)`: every contract whose clause / obligation / term text contains all the content words in `query` (e.g. "liability insurance", "non-compete"). Complete enumeration, not a ranked sample - for "which contracts require X". Deterministic, no LLM.
- `aggregate_contracts(organization_id, measure, group_by?, ...filters)`: deterministic `count` / `sum_value` / `avg_value` / `min_value` / `max_value` of contract value over a filtered set, optionally grouped by `lifecycle_status` / `contract_type` / `party`. All money and date math done here. Deterministic, no LLM.
- Filters shared by `count_contracts` / `list_contracts` / `find_contracts` / `aggregate_contracts`: `lifecycle_status`, `contract_type`, `party`, `effective_year`, `expiring_within_days`, `min_value`, `max_value`.
- `search_clauses`: return the evidence records best matching a query (deterministic keyword rank, no LLM) - used by the query agent's `search_clauses` branch and available to other read-only callers. Evidence records include `renewal_terms`, `termination_terms`, `risk_profile`, the `key_dates:renewal_deadline` / `key_dates:termination_notice_deadline` deadlines, and each obligation's trigger + consequence in its label.
- `analyze_contracts`: answer a cited provider-agnostic question over one or all contracts belonging to a supplied, trusted organization context. Its `ContractQueryRequest` carries an optional `history` (role + text turns) for follow-up questions. The agent plans which of the tools above each question needs. `count_contracts` / `list_contracts` share `query_agent/portfolio.py` with these MCP tools.
- Read-only and used only by `query_agent`.

The web orchestrator supplies the organization ID only after JWT authorization; each query tool checks `contract_tenants` before returning metadata or evidence. A standalone MCP deployment must authenticate and derive this context rather than trusting arbitrary caller input.

See [extraction_mcp_server/server.py](extraction_mcp_server/server.py), [query_mcp_server/server.py](query_mcp_server/server.py), and [clm_mcp_core/tenant_contracts.py](clm_mcp_core/tenant_contracts.py). The existing [clm_mcp_server/server.py](clm_mcp_server/server.py) remains extraction-only compatibility for older callers.

## Compatibility

`clm_mcp_server`, `extraction_mcp_server`, and `query_mcp_server` import
`MCPServer` from `mcp.server.mcpserver` when available (`mcp>=2.0`) and fall back
to `mcp.server.fastmcp.FastMCP` on `mcp` 1.x, which is API-compatible for the
tool/run usage here.

## Tests

```powershell
uv run pytest mcp/tests
```
