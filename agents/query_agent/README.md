# Query Agent

Provider-agnostic contract analysis agent for answering organization-wide
questions about tenant-scoped stored contracts. A caller can optionally narrow
analysis to one contract; the normal chat experience is organization-wide.

## Reasoning shape: plan (tree of thought) → gather → interpret → draft → verify

One question often carries several needs at once (a count, a filtered list, a
clause lookup). The agent branches on the *kinds* of question and resolves each.

1. Receives a question, already-authorized contract snapshots, and an optional
   read-only conversation `history` (role + text only).
2. **Plan** (`QUERY_PLAN_TOOLS`, default on) - one LLM call classifies the
   question by type and emits one tool call per distinct need (≤ `QUERY_MAX_TOOL_CALLS`):
   - `count_contracts(lifecycle_status?, contract_type?)` - exact counts /
     breakdowns. Deterministic, no LLM, no retrieval.
   - `list_contracts(lifecycle_status?, contract_type?, detail)` - the matching
     contracts as summary rows or (`detail="full"`, small filtered sets) whole
     contract records.
   - `find_contracts(query)` - **every** contract whose clause/obligation text
     contains the phrase ("which contracts require liability insurance", "what are
     our payment obligations across all contracts"). Complete enumeration.
   - `aggregate_contracts(measure, group_by?)` - deterministic count / sum / avg /
     min / max of contract value over a filtered set, optionally grouped ("total
     value of active contracts", "average value by contract type"). All money and
     date arithmetic is done here - the model never computes.
   - `search_clauses(query)` - embedding-ranked clause/obligation snippets for
     one-/few-contract detail questions.

   Every deterministic tool shares an optional `where` filter: `lifecycle_status`,
   `contract_type`, `party`, `effective_year`, `expiring_within_days` (e.g. 90 for
   "next quarter"), `min_value` / `max_value`. Deterministic keyword guards add the
   tool the planner missed - including relative-date and value filters parsed from
   the question ("signed in 2024", "expiring in 90 days", "over $1M").
3. **Gather** - run every planned call. The portfolio tools (`query_agent/portfolio.py`)
   are shared with the Query MCP `count_contracts` / `list_contracts` tools.
4. **Interpret** (`QUERY_INTERPRET`, default on) - only when clause snippets were
   gathered: build the trigger → consequence → `what_matters` model. Best-effort.
5. **Draft** a structured answer that synthesises across counts, lists, and
   clause evidence, with citations, confidence, and an uncertainty flag.
6. **Verify** - checks the draft; `counts` / `contract_lists` are authoritative
   for numbers, clause claims must be backed by cited evidence.

The contract data is authoritative - the LLM cannot retrieve outside what the
Query MCP supplies. The scratchpad (tool calls, evidence labels, `what_matters`)
is working memory, discarded after the response. Every step falls back
gracefully; only the final draft step can fail the request.

## Configuration

Provider, model, temperature, timeout, `OLLAMA_HOST`, and embedding settings are
resolved centrally by `agent_llm` from the repo-root `.env` (see
[`.env.example`](../../.env.example)). The shared defaults apply to every agent;
set `QUERY_LLM_PROVIDER` / `QUERY_LLM_MODEL` / `QUERY_LLM_TIMEOUT_SECONDS` etc.
only when this agent should differ from the shared `LLM_*` values.

Query-agent behavioural knobs (read directly by `query_agent/config.py`):

```env
QUERY_PLAN_TOOLS=1
QUERY_INTERPRET=1
QUERY_VERIFY=1
QUERY_MAX_TOOL_CALLS=5
QUERY_LIST_FULL_MAX=10
QUERY_EVIDENCE_BUDGET=30
QUERY_SEARCH_K=8
QUERY_FAST_TIMEOUT_SECONDS=120
```

Any provider available through `any-llm` works the same way; no provider-specific
client is embedded in the agent.

## Orchestration and MCP

The web agent orchestrator invokes this agent for analysis messages and for
`analyze` steps scheduled by the Auto planner. It derives the user and
organization context from the bearer token, assembles the conversation `history`
(rolling summary + recent turns), persists safe run events, and streams progress
over SSE. The analysis path delegates to the read-only `query_mcp_server`, which
rechecks organization membership before running `count_contracts`,
`list_contracts`, `search_clauses`, or invoking this agent. Provider failures
return a terminal run failure rather than a fabricated answer.

See [Architecture](docs/architecture.md) and
[Memory and Reasoning](../../docs/memory-and-reasoning.md).
