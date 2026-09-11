# Query Agent

Provider-agnostic contract analysis agent for answering organization-wide
questions about tenant-scoped stored contracts. A caller can optionally narrow
analysis to one contract; the normal chat experience is organization-wide.

## Reasoning shape: plan (tree of thought) → gather → interpret → draft → verify

One question often carries several needs at once (a count, a filtered list, a
clause lookup). The agent branches on the *kinds* of question and resolves each.

1. Receives a question, already-authorized contract snapshots, and an optional
   read-only conversation `history` (role + text only).
2. **Plan** (`QUERY_PLAN_TOOLS`, default on) - one LLM call names a **prompt
   template** ([`prompts/templates.yaml`](prompts/templates.yaml), catalogue:
   [`docs/query-agent-prompt-templates.md`](../../docs/query-agent-prompt-templates.md))
   and emits one tool call per distinct need (≤ `QUERY_MAX_TOOL_CALLS`), using
   only that template's tools:
   - `count_contracts` - exact counts / breakdowns. Deterministic, no LLM.
   - `list_contracts(detail)` - matching contracts as summary rows or whole
     records (`detail="full"`, small filtered sets).
   - `find_contracts(query)` - **every** contract whose clause/obligation text
     contains the phrase ("which contracts require liability insurance").
     Complete enumeration - not `search_clauses`.
   - `aggregate_contracts(measure, group_by?)` - count / sum / avg / min / max of
     contract value. All money and date arithmetic is done here - the model
     never computes.
   - `search_clauses(query)` - embedding-ranked clause snippets for one-/few-
     contract detail.

   Every deterministic tool shares an optional `where` filter: `lifecycle_status`,
   `contract_type`, `party`, `effective_year`, `expiring_within_days` (90 for
   "next quarter"), `min_value` / `max_value`. `_guard_plan` does **filter-value
   hygiene only**: it normalises facet spelling, forces a parsed filter
   ("signed in 2024", "expiring in 90 days", "over $1M") onto an unscoped call,
   and drops any call outside the template's allowlist. It does **no tool
   selection**. A question that fits no template routes to the
   `T9_risk_exposure_review` template — but only when the model actually names
   it with real calls. A question that projects onto **no** template on *either*
   the LLM planner or the deterministic backstop is never turned into a guessed
   plan: `answer()` returns `needs_clarification=true` with a targeted question
   grounded in the portfolio's real facets, bounded by `QUERY_CLARIFY_MAX_ROUNDS`
   on both the orchestrator and the agent (ADR-0004 D3).

   `QUERY_PLAN_TOOLS=0` is a **degraded mode** for the fully-offline reviewer tour
   on a small local model: no LLM planner, deterministic keyword routing to the
   deterministic templates only.
3. **Gather** - run every planned call. The portfolio tools (`query_agent/portfolio.py`)
   are shared with the Query MCP `count_contracts` / `list_contracts` tools.
4. **Interpret** (`QUERY_INTERPRET`, default on) - only when clause snippets were
   gathered: build the trigger → consequence → `what_matters` model. Best-effort.
5. **Coverage** - `matched` vs what the model actually read. When a synthesis
   rests on a sample of a larger matched set (`spans_portfolio`), the answer must
   say so and offer the exact count or a narrower filter.
6. **Draft** a structured answer that synthesises across counts, lists, and
   clause evidence, with citations, confidence, and an uncertainty flag.
7. **Verify** - checks the draft; `counts` / `contract_lists` are authoritative
   for numbers, clause claims must be backed by cited evidence, and an answer
   that implies completeness while coverage is partial is rejected.

The contract data is authoritative - the LLM cannot retrieve outside what the
Query MCP supplies. The scratchpad (tool calls, evidence labels, `what_matters`)
is working memory, discarded after the response. Every step falls back
gracefully; only the final draft step can fail the request.

## Prompt templates

The planner names one **prompt template** per question; that fixes its tool
allowlist. Full catalogue - each template's cues, scaffold, answer contract and
coverage rule: **[`docs/query-agent-prompt-templates.md`](../../docs/query-agent-prompt-templates.md)**.
Machine source the planner loads: [`prompts/templates.yaml`](prompts/templates.yaml).

Tools: 🔢 `count_contracts` · 📇 `list_contracts` · 🔎 `find_contracts` ·
∑ `aggregate_contracts` · 📄 `search_clauses`. **D** = deterministic (no LLM
draft; the templates degraded mode routes to) · **S** = LLM synthesis · **cov**
= must convey coverage when the matched set exceeds what the model read.

| id | template | mode | tools |
|---|---|---|---|
| T1 | `portfolio_census` | D | 🔢 ∑ |
| T2 | `filtered_roster` | D cov | 📇 🔢 |
| T3 | `clause_presence` | D cov | 🔎 🔢 |
| T4 | `financial_rollup` | D | ∑ 📇 |
| T5 | `expiring_and_renewals` | D→S | 📇 🔎 📄 |
| T6 | `clause_detail` | S | 📇 📄 |
| T7 | `cross_contract_synthesis` | S cov | 🔎 📄 |
| T8 | `comparative_review` | S cov | 📇 📄 |
| T9 | `risk_exposure_review` | S cov | 🔎 📇 📄 — **fallback** for any unrouted question |
| T10 | `obligation_tracker` | D | 📇 🔎 |
| T11 | `counterparty_profile` | D | 📇 🔢 ∑ |
| T12 | `out_of_scope` | — | (none — escalate) |

### Original hypothesis → template mapping

The templates are how the standing hypotheses / heuristics are enforced in the
routing layer. Sources: [`AGENT_HYPOTHESES.md`](../../AGENT_HYPOTHESES.md),
[`MCP_HEURISTICS.md`](../../MCP_HEURISTICS.md) §2 (Query MCP Server).

| Hypothesis / heuristic | Enforced by |
|---|---|
| **H3** — embedded tool descriptions improve parameter mapping | the template mechanism itself: the planner names a template (an embedded description = allowlist + cues + scaffold), never picks raw tools |
| **H5 / VH2** — structured cognitive loops (Goal → Constraints → Escalate) prevent hallucination | every template `scaffold` states goal + constraints; the `coverage` rule is the "don't overclaim" constraint; T12 is the escalate path |
| **VH1** — training-data quality > model size | the **D** templates (T1–T5, T10, T11) + `QUERY_DETERMINISTIC_COMPOSE`: a small model only routes, the tools compute — this is all `QUERY_PLAN_TOOLS=0` degraded mode serves |
| **VH3** — grounding via plan → prep → pipeline | the `gather` step each template drives: deterministic portfolio tools + `search_clauses` retrieval within `QUERY_EVIDENCE_BUDGET` |
| **H2** — conversation history improves multi-turn accuracy | the *multi-turn follow-up* handling — resolve the referent from `history`, then apply the template the follow-up implies (untested; this is where H2 is measured) |
| **§2.1** — question scope (portfolio vs one contract) | T6 `clause_detail` resolves a named contract first; every other template is organization-scoped |
| **§2.2** — escalate when evidence is weak | T12 `out_of_scope`; T6's "not stated in `<contract>`"; the **cov** rule on T2/T3/T7/T8/T9 (flag partial coverage, offer the count / a narrower filter) |
| **§2.3** — `find_contracts` (exact enumeration) vs reasoning | the T3 (🔎, complete matched count) vs T6/T7 (📄, ranked sample) split *is* this heuristic |
| **§2.4** — history for follow-ups | the *multi-turn follow-up* row above |

## Configuration

Provider, model, temperature, timeout, `OLLAMA_HOST`, and embedding settings are
resolved centrally by `agent_llm` from the repo-root `.env` (see
[`.env.example`](../../.env.example)). The shared defaults apply to every agent;
set `QUERY_LLM_PROVIDER` / `QUERY_LLM_MODEL` / `QUERY_LLM_TIMEOUT_SECONDS` etc.
only when this agent should differ from the shared `LLM_*` values.

Query-agent behavioural knobs (read directly by `query_agent/config.py`):

```env
QUERY_PLAN_TOOLS=1              # 0 = degraded mode (no LLM planner; see above)
QUERY_INTERPRET=1
QUERY_VERIFY=1
QUERY_DETERMINISTIC_COMPOSE=1   # structural answers templated from tool output
QUERY_MAX_TOOL_CALLS=5
QUERY_LIST_FULL_MAX=10
QUERY_EVIDENCE_BUDGET=30
QUERY_SEARCH_K=8
QUERY_FAST_TIMEOUT_SECONDS=120
QUERY_CLARIFY_MAX_ROUNDS=3      # bounds the ask-for-clarification loop (ADR-0004 D3)
```

Routing and retrieval architecture:
[ADR-0004](../../docs/adr/0004-query-agent-routing-and-retrieval.md).

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
