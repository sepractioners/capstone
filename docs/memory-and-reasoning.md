# Memory and Reasoning

Every LLM call in this platform is a bounded step with a schema and a timeout.
Deterministic Python still owns all control flow, retrieval wiring, lifecycle
transitions and authorization. Reasoning is added only where a single
"fill in the schema" call genuinely cannot do the job, and every new call
**falls back to the previous behaviour** on failure - it is recorded in the
trace, never allowed to fail the run.

## Observability vs. privacy

Two channels:

- **SSE / conversation memory** (what ordinary users and the run timeline see):
  safe events only - `run.started`, `progress`, `assistant.message`,
  `run.completed`, the answer + citations. Never prompts, tokens, provider
  secrets, source bytes, or the evidence context.
- **`agent_debug_traces`** - the *complete* per-step record: system prompt text,
  the exact context sent to each model call, the raw and parsed output, the
  reasoning/CoT field, a memory snapshot per step, retrieval pool + scores,
  timing, and model/provider. Rendered in the **Agent Console** (`web/admin`, a
  separate admin-only app), including the *partial* trace of a failed run so its
  failure reasoning survives. Always on in this build; a multi-tenant production
  deployment would gate or disable it and must still never expose provider
  secrets.

Everything persisted is tenant-scoped.

## Memory taxonomy

| Memory type | Extraction agent | Query agent | Orchestrator |
|---|---|---|---|
| **Working / short-term** | Per-document running state `{title, contract_type, parties[], defined_terms{}, last_heading, renewal_terms, termination_terms}` threaded page to page; per-page `reasoning` (logged to the trace, dropped from the candidate). Discarded after ingest. | Scratchpad: the planned tool calls, gathered evidence labels, and the interpretation's `what_matters`. Discarded after the response. | `execute_plan` step state - step *i*'s result summary feeds step *i+1*; persisted only as safe events. |
| **Episodic** | None. The durable technical record is the `extraction_trace` → `extraction_traces` table (admin-only). | None in the agent - it is stateless. It receives a read-only `history` list (role + text only) assembled by the orchestrator. | `agent_conversations / messages / runs / run_events` in SQLite, plus a **bounded context window** (recent turns) and a **rolling summary** (`agent_conversations.summary`). |
| **Semantic / long-term** | Hybrid RAG store (SQLite FTS5 + local embeddings) over `rag_knowledge.jsonl` + CUAD examples. Retrieved with the first few pages, not just page one. | For clause questions: in-request embedding ranking over authorized evidence (`query_agent/retrieval.py`), keyword fallback, via the `search_clauses` branch / MCP tool. Portfolio questions bypass this entirely (`count_contracts` / `list_contracts`). Persistent tenant-partitioned clause index is future work. | - |
| **Procedural** | `system_prompt.yaml`, RAG guidance, contract profiles. | `contract_query.yaml` + per-step prompts. | The planner prompt. |

**No cross-document memory in extraction.** `memory` is a local in
`extract_node` for one graph invocation. It is never shared between documents,
contracts, or tenants.

**Reference resolution.** "that contract" / "the one you just extracted" is
resolved from the most recent completed run's result in the same conversation
(`AgentRunStore.latest_run_result`) and from the rolling summary passed to the
query agent as history.

## Reasoning strategy per component

### Extraction agent - `load → extract → review → ingest`

- **Per page (chain of thought):** the page call fills a `reasoning` field first,
  then the typed fields. Reasoning is logged to the trace and dropped from the
  merged candidate.
- **Smarter retry:** a page is re-read not only when it comes back empty, but
  when the retrieved profile says this contract type needs fields a long page
  produced none of.
- **Document review (reflection + self-consistency):** one call over the
  assembled candidate + full text does the final `contract_type` classification,
  an independent read of the high-stakes fields (parties, dates, value) that is
  *voted* against the page-merge result, and internal-consistency checks
  (obligation → known party, date ordering, required fields). It raises
  `ReviewFinding`s; a `blocker` finding (or a directive that disagrees with the
  document) stops the write and returns `requires_human_confirmation`.
- **Obligation analysis (`obligation_analysis` trace stage):** the same review
  call also reads each material commitment/right as `{trigger, consequence,
  deadline basis, materiality}`. Deterministic checks flag an auto-renewal with
  no notice window, a termination-for-convenience right with no notice period, an
  obligation with timing but no recorded trigger, and a high-materiality
  obligation with no stated consequence. These inform (`info`/`warning`) - they
  never block. The triggers/consequences and renewal/termination terms are
  persisted onto the contract (`Obligation.consequence_of_failure`,
  `RenewalTerms`, `TerminationTerms`, `KeyDates` deadlines) via
  `Contract.record_extracted_terms`.
- **Date math (shared `contract_calc`):** the review pass computes the
  auto-renewal opt-out deadline (expiration − notice window), flags an obligation
  due after the contract expires, and flags a sub-week term. The same
  deterministic date/money helpers back the query agent's portfolio tools, so
  both agents agree on what "$1.5M" or "expiring within 90 days" means.

### Query agent - plan (tree of thought) → gather → interpret → draft → verify

One question can carry several needs at once - a count, a filtered list, a clause
lookup. The agent classifies the *kinds* of question and resolves each.

- **Plan (`plan` trace stage):** one LLM call branches on question type and emits
  one tool call per need (≤ `QUERY_MAX_TOOL_CALLS`), each with an optional `where`
  filter (`lifecycle_status`, `contract_type`, `party`, `effective_year`,
  `expiring_within_days`, `min_value` / `max_value`):
  - `count_contracts` / `list_contracts` - exact counts, filtered rosters, whole
    contract records.
  - `find_contracts` - every contract whose clause text contains a phrase
    (complete enumeration for "which contracts require X" / portfolio-wide clause
    questions).
  - `aggregate_contracts` - deterministic count / sum / avg / min / max of
    contract value over a filter, optionally grouped. The tool does the money and
    calendar arithmetic; the model never computes.
  - `search_clauses` - embedding-ranked snippets, for one-/few-contract clause
    detail only.

  The first four are deterministic (no LLM, no retrieval). Keyword guards add the
  tool the planner missed - including relative-date and value filters parsed from
  the question. Disable the plan call with `QUERY_PLAN_TOOLS=0`.
- **Gather:** run every call. Portfolio logic (`query_agent/portfolio.py`) is
  shared with the Query MCP `count_contracts` / `list_contracts` tools.
- **Interpret (`interpret` trace stage):** only when clause snippets were
  gathered - build the trigger → consequence → `what_matters` chain. Best-effort;
  disable with `QUERY_INTERPRET=0`.
- **Draft:** synthesise one answer across counts, lists, and clause evidence.
  When no clause snippets were gathered (a structural question - count / filtered
  count / list / breakdown / enumerate / aggregate) `_compose_deterministic`
  templates the answer + citations straight from the tool output with **no LLM
  call**; the LLM draft runs only for clause synthesis. Disable with
  `QUERY_DETERMINISTIC_COMPOSE=0`.
- **Verify:** `counts` / `contract_lists` are authoritative for numbers; clause
  claims must be backed by cited evidence. Drops unsupported citations, sets a
  calibrated confidence / the `uncertain` flag.

**Why not pure retrieval:** "how many active contracts" needs every contract's
status, and "which contracts require liability insurance" needs every matching
contract - not the top-`QUERY_SEARCH_K` snippets. Counting and enumeration are
deterministic scans; retrieval only ranks clause text for detail questions.

### Orchestrator - plan-and-execute

- `planner.plan(message, has_attachment)` returns an intent check plus ≤
  `PLANNER_MAX_STEPS` typed steps (`extract` / `analyze`). Deterministic
  guardrails clamp the plan (`extract` only with an attachment, step cap,
  non-actionable message → one clarification).
- `execute_plan` runs the steps in order, threads each step's summary into the
  next, and reacts to `requires_human_confirmation` by emitting a
  `needs_confirmation` event while still running any following analyze step with
  the new contract in scope.
- Every step still passes the same tenant checks and safe-event logging as the
  single-capability endpoints.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `EXTRACTION_REVIEW_ENABLED` | `1` | document review pass |
| `EXTRACTION_REVIEW_TEXT_CHARS` | `16000` | full-text budget sent to review |
| `EXTRACTION_PAGE_TAIL_CHARS` | `400` | previous-page continuity tail |
| `EXTRACTION_RAG_SAMPLE_PAGES` | `3` | pages joined for the RAG query |
| `QUERY_PLAN_TOOLS` | `1` | LLM plan step (off = the keyword-routed default plan runs) |
| `QUERY_MAX_TOOL_CALLS` | `5` | tool calls per question |
| `QUERY_LIST_FULL_MAX` | `10` | contracts returned as full records before summary fallback |
| `QUERY_EVIDENCE_BUDGET` | `30` | clause snippets sent to the answer step |
| `QUERY_SEARCH_K` | `8` | records pulled per search |
| `QUERY_INTERPRET` | `1` | trigger → consequence → what-matters step |
| `QUERY_DETERMINISTIC_COMPOSE` | `1` | template structural answers (no clause evidence) from tool output — no LLM draft call |
| `QUERY_VERIFY` | `1` | post-draft verification pass |
| `QUERY_FAST_TIMEOUT_SECONDS` | `120` | timeout for the best-effort plan / interpret calls |
| `PLANNER_MAX_STEPS` | `3` | orchestrator plan length cap |
| `AGENT_SUMMARY_MIN_TURNS` | `6` | turns before a rolling summary is written |

### LLM provider / embedding settings

Resolved centrally by `agent_llm` from the repo-root `.env` (see `.env.example`),
shared by every agent, the planner, and the summarizer. For any role the order is
`<ROLE>_LLM_*` → `LLM_*` (a global override) → a **per-role built-in default**:

| Role | Built-in default (no env set) |
|---|---|
| `extraction`, `review`, `planner`, `summary` | `anthropic` / `claude-haiku-4-5-20251001` |
| `query`, `platform` | `ollama` / `gemma4:latest` |

So `LLM_PROVIDER` / `LLM_MODEL` are **not defaults** - they are optional
overrides that point every role at one backend. The other shared knobs:

| Variable | Default | Effect |
|---|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | – (per-role built-ins above) | override provider / model for every role |
| `LLM_TEMPERATURE` | `0` | sampling temperature |
| `LLM_TIMEOUT_SECONDS` | `300` | per-call timeout |
| `LLM_RETRIES` | `2` | retries on a transient provider error (rate limit / 5xx) |
| `LLM_RETRY_BACKOFF_SECONDS` | `3` | base backoff between retries |
| `OLLAMA_HOST` | – | local/LAN Ollama base URL; sets the ollama `api_base` and, unless `EMBEDDING_URL` is set, the embedding endpoint |
| `EMBEDDING_MODEL` | `nomic-embed-text:latest` | embedding model |
| `EMBEDDING_URL` | `${OLLAMA_HOST}/api/embed` if `OLLAMA_HOST` set, else `http://127.0.0.1:11434/api/embed` | embedding endpoint (Ollama `/api/embed` shape) |

Per-role overrides: `EXTRACTION_LLM_*`, `REVIEW_LLM_*`, `QUERY_LLM_*`,
`PLANNER_LLM_*`, `SUMMARY_LLM_*`, `PLATFORM_LLM_*` (each supports `_PROVIDER`,
`_MODEL`, `_TEMPERATURE`, `_TIMEOUT_SECONDS`, `_API_BASE`).
