# Agents

The `agents` workspace contains specialized extraction and contract-analysis packages. The web orchestrator selects a capability from the user's explicit chat mode and streams safe progress to the UI or CLI. Extraction uses the write-capable Extraction MCP server; query uses the read-only Query MCP server. Neither agent imports CLM domain internals directly.

`agent_llm` is the shared LLM layer for every agent, the planner, and the
conversation summarizer: role-based provider/model/timeout/embedding settings
(`settings_for(role)`, `EMBEDDING`) loaded from the repo-root `.env`, plus the one
client (`agent_llm.client.acall` / `acall_retrying`) and embedding helper
(`agent_llm.embeddings.embed`) they all call. Only the system prompts and
per-agent behavioural knobs live in the individual packages. `agent_trace`
provides the shared full-fidelity step recorder. `contract_calc` holds the
deterministic date and money helpers (`parse_date`, `parse_money`,
`resolve_timeframe_days`, `total_value`, `days_between`, …) so no model ever
parses a date or adds up money - shared by the query agent's portfolio tools and
the extraction agent's review checks.

## Extraction Agent

- [Extraction Agent](extraction_agent/README.md): PDF/JSON/CSV loading, LLM page extraction, merging, structured mapping, and MCP ingestion.
- [Architecture](extraction_agent/docs/architecture.md)
- [Agent Internals](extraction_agent/docs/agent-internals.md)
- [Usage](extraction_agent/docs/usage.md)
- [Kaggle CUAD Testing](extraction_agent/docs/kaggle-cuad.md)

Run agent tests with:

```powershell
uv run pytest agents/tests
```

## Query Agent

- [Query Agent](query_agent/): provider-agnostic contract analysis over tenant-scoped evidence.
- [Architecture](query_agent/docs/architecture.md)
- Reasoning: plan (tree of thought - classify the question into count /
  list / clause needs) → gather (deterministic `count_contracts` /
  `list_contracts`, embedding-ranked `search_clauses`) → interpret → draft →
  verify.
- Stateless: the orchestrator passes a read-only conversation `history`.
- Uses `any-llm`; provider/model/embedding config is resolved centrally by
  `agent_llm` from the repo-root `.env`.
- Returns structured answers with confidence and contract/clause citations.

See [Memory and Reasoning](../../docs/architecture/memory-and-reasoning.md) for the memory
taxonomy and reasoning strategy across both agents and the orchestrator.
