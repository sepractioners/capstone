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
| **Working / short-term** | Per-document running state `{title, contract_type, parties[], defined_terms{}, last_heading, renewal_terms, termination_terms}` threaded page to page; per-page `reasoning` (logged to the trace, dropped from the candidate). Discarded after ingest. | Scratchpad: the planned tool calls, gathered evidence labels, the interpretation's `what_matters`, and the `coverage` record (matched vs. actually read). Discarded after the response. | `execute_plan` step state - step *i*'s result summary feeds step *i+1*; persisted only as safe events. |
| **Episodic** | None. The durable technical record is the `extraction_trace` → `extraction_traces` table (admin-only). | None in the agent - it is stateless. It receives a read-only `history` list (role + text only) assembled by the orchestrator; also used to floor the clarification round count (`_history_clarify_floor`) when the caller doesn't track it. | `agent_conversations / messages / runs / run_events` in SQLite, plus a **bounded context window** (recent turns) and a **rolling summary** (`agent_conversations.summary`). Also owns the primary `clarify_round` count across turns (ADR-0006 D3). |
| **Semantic / long-term** | Hybrid RAG store (SQLite FTS5 + local embeddings) over `rag_knowledge.jsonl` + CUAD examples. Retrieved with the first few pages, not just page one. | For clause questions: in-request embedding ranking over authorized evidence (`query_agent/retrieval.py`), keyword fallback, via the `search_clauses` branch / MCP tool. Portfolio questions bypass this entirely (`count_contracts` / `list_contracts`). Persistent tenant-partitioned clause index is future work (deferred, ADR-0006). | - |
| **Procedural** | `system_prompt.yaml`, RAG guidance, contract profiles. | `templates.yaml` - the routing spec: one prompt template per question category, each with a tool allowlist, a planning `scaffold`, and (for T6-T9) a `deduction_procedure`. Plus `contract_query.yaml` for the draft/verify steps. | The planner prompt. |

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

### Query agent - plan → gather → interpret → coverage → draft → verify

One question can carry several needs at once - a count, a filtered list, a clause
lookup. The agent classifies the *kinds* of question and resolves each. Routing
is **spec-driven** (ADR-0006), not keyword-matched: a catalogue of twelve prompt
templates (`templates.yaml`) is the taxonomy the planner reasons from, not an
enumeration of literal questions - see
[`docs/query-agent-prompt-templates.md`](query-agent-prompt-templates.md) for
the full catalogue and [`agents/query_agent/README.md`](../agents/query_agent/README.md#original-hypothesis--template-mapping)
for which standing hypothesis each part of a template enforces.

- **Plan (`plan` trace stage):** one LLM call names the single **template**
  whose cues best fit the question - that fixes its tool allowlist - then emits
  one tool call per need (≤ `QUERY_MAX_TOOL_CALLS`).

  **Why one call, not several candidates evaluated against each other:** the
  template catalogue is handed to the model *in full* in this one call - all
  twelve templates' cues and scaffolds at once - so the model is already
  choosing among explicitly presented alternatives inside a single
  generation, not picking the first idea that comes to mind. That is weaker
  than true multi-candidate search (generate N plans, score each, keep the
  best) - there is no comparative-evaluation step here, and a single greedy
  generation can and does pick differently across repeated runs of the same
  question (observed directly this session). The design leans on this single
  call being *cheap to get wrong* instead of *hard to get wrong*: a bad or
  empty plan is caught downstream rather than prevented upfront - `_guard_plan`
  strips anything outside the named template's allowlist, a deterministic
  backstop is tried if the call fails or names nothing usable, the two
  ADR-0006 self-correction loops give gather and verify one bounded retry
  each, and a question that never resolves becomes a clarification, never a
  guess. Trading a more reliable but multi-call planning search for a cheap
  single call plus strong downstream backstops was a deliberate, not-yet-closed
  design trade-off, recorded as
  [ADR-0006 open question 4](adr/0006-query-agent-routing-retrieval-and-self-correction.md#open-questions)
  rather than decided here - see also the "spec-driven vs. still one-shot"
  note below.
  - `count_contracts` / `list_contracts` - exact counts, filtered rosters, whole
    contract records.
  - `find_contracts` - every contract whose clause text contains a phrase
    (complete enumeration for "which contracts require X" / portfolio-wide clause
    questions).
  - `aggregate_contracts` - deterministic count / sum / avg / min / max of
    contract value over a filter, optionally grouped. The tool does the money and
    calendar arithmetic; the model never computes.
  - `search_clauses` - embedding-ranked snippets, for one-/few-contract clause
    detail or, per T7-T9's templates, one call per named topic in a portfolio
    synthesis.

  `_guard_plan` does **filter-value hygiene only** - facet-spelling
  normalisation and forcing a parsed relative-date/value/facet filter onto an
  unscoped call - plus dropping any call outside the named template's
  allowlist. **No tool selection lives in code** (ADR-0006 D2); the model
  chooses tools by reasoning from the template spec, not a keyword table. If
  the LLM planner is unavailable or names nothing usable, a deterministic
  keyword/facet backstop (`_deterministic_route`) is tried - and is the *only*
  router when `QUERY_PLAN_TOOLS=0` (a labelled degraded mode for the
  fully-offline small-model tour, D-mode templates only). If **neither** the
  planner nor the backstop projects the question onto a template, the agent
  does not fabricate a plan (not a bare count, not a synthesized search
  phrase): it returns `needs_clarification=true`, a targeted question grounded
  in the portfolio's real facets, bounded by `QUERY_CLARIFY_MAX_ROUNDS` on
  both the orchestrator (primary owner of the round count across turns) and
  the agent itself as a second gate (ADR-0006 D3).
- **Gather:** run every call. Portfolio logic (`query_agent/portfolio.py`) is
  shared with the Query MCP `count_contracts` / `list_contracts` tools. **Bounded
  self-correction 1/2 (ADR-0006):** if the named template's mode needs real
  synthesis (`S`) but gather came back with zero clause text, replan once with
  that gap named explicitly before falling through - bounded by
  `QUERY_GATHER_REPLAN_MAX_ROUNDS`, 0 disables it.
- **Interpret (`interpret` trace stage):** only when clause snippets were
  gathered - build the trigger → consequence → `what_matters` chain, each point
  grounded in one specific evidence entry (empty evidence → empty output, never
  filled from the model's own prior knowledge of what this kind of clause
  usually contains). Best-effort; disable with `QUERY_INTERPRET=0`.
- **Coverage:** `matched` vs. what the model actually read
  (`evidence_fed`/`spans_portfolio`). Not a model call - pure arithmetic on
  numbers `gather` already produced, so `verify` has an objective fact to check
  `draft`'s wording against rather than trusting the drafter's own account of
  its thoroughness.
- **Draft:** synthesise one answer across counts, lists, and clause evidence.
  When no clause snippets were gathered (a structural question - count / filtered
  count / list / breakdown / enumerate / aggregate) `_compose_deterministic`
  templates the answer + citations straight from the tool output with **no LLM
  call**; the LLM draft runs only for clause synthesis. Disable with
  `QUERY_DETERMINISTIC_COMPOSE=0`. When `coverage.spans_portfolio` is true the
  draft must say the answer rests on a sample and offer the exact count or a
  narrower filter - never imply it covered every contract.
- **Verify:** `counts` / `contract_lists` are authoritative for numbers; clause
  claims must be backed by cited evidence; an answer implying completeness while
  coverage is partial is rejected. Drops unsupported citations, sets
  `confidence = min(draft.confidence, verify.adjusted_confidence)` - a
  conservative floor, verify can only ever lower trust in an answer, never
  inflate it. **Bounded self-correction 2/2 (ADR-0006):** if verify flags an
  unsupported claim, redraft once with the specific labels named before
  shipping - bounded by `QUERY_DRAFT_REVERIFY_MAX_ROUNDS`, 0 disables it; only
  wraps the LLM draft path, not `_compose_deterministic` (already grounded 1:1
  in tool output).

Both self-correction loops are **probabilistic improvements, not guarantees**:
bounded rounds, and on exhaustion, fall through to the pre-loop behaviour
unchanged - never a fabrication, never an infinite loop, never worse than not
looping at all. See [ADR-0006](adr/0006-query-agent-routing-retrieval-and-self-correction.md).

**Why not pure retrieval:** "how many active contracts" needs every contract's
status, and "which contracts require liability insurance" needs every matching
contract - not the top-`QUERY_SEARCH_K` snippets. Counting and enumeration are
deterministic scans; retrieval only ranks clause text for detail questions.

**What's spec-driven vs. what's still one-shot.** The *routing* decision (which
template, which tools) is spec-driven per question - the model reasons from the
template catalogue fresh each call, not from a fixed branch table. But within
one call, planning and drafting are still single-shot generation, not a
generate-then-evaluate search over multiple candidates (no tree-of-thought
branching at either the template-selection or the tool-call-plan level) - the
`draft` → `verify` split is the one place this pipeline already separates
generation from evaluation into two independent calls; extending that same
separation earlier in the pipeline is a considered future direction, not yet
built.

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
| `QUERY_PLAN_TOOLS` | `1` | LLM planner names a template + tool calls (off = degraded mode: deterministic keyword/facet routing, D-mode templates only) |
| `QUERY_MAX_TOOL_CALLS` | `20` | tool calls per question (T9's full decompose-per-topic recipe needs headroom - 5 silently starved it to one real evidence call) |
| `QUERY_LIST_FULL_MAX` | `10` | contracts returned as full records before summary fallback |
| `QUERY_EVIDENCE_BUDGET` | `30` | clause snippets sent to the answer step |
| `QUERY_SEARCH_K` | `8` | records pulled per search |
| `QUERY_INTERPRET` | `1` | trigger → consequence → what-matters step |
| `QUERY_DETERMINISTIC_COMPOSE` | `1` | template structural answers (no clause evidence) from tool output — no LLM draft call |
| `QUERY_VERIFY` | `1` | post-draft verification pass |
| `QUERY_FAST_TIMEOUT_SECONDS` | `120` | timeout for the best-effort plan / interpret calls |
| `QUERY_CLARIFY_MAX_ROUNDS` | `3` | bounds the ask-for-clarification loop when a question projects onto no template (ADR-0006 D3) |
| `QUERY_GATHER_REPLAN_MAX_ROUNDS` | `1` | bounds the gather-thin replan loop (ADR-0006); `0` disables |
| `QUERY_DRAFT_REVERIFY_MAX_ROUNDS` | `1` | bounds the unsupported-claim redraft loop (ADR-0006); `0` disables |
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
