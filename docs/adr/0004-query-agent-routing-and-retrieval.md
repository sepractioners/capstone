# ADR-0004: Spec-driven query-agent routing; retrieval stays in-process

- **Status:** Rejected
- **Date:** 2026-09-09
- **Deciders:** Capstone team
- **Relates to:** [ADR-0002](0002-query-agent-evaluation-substrate.md), [ADR-0003](0003-query-agent-stress-corpus.md)
- **Supersedes:** —
- **Superseded by:** [ADR-0006](0006-query-agent-routing-retrieval-and-self-correction.md)

> **Retired.** Consolidated into [ADR-0006](0006-query-agent-routing-retrieval-and-self-correction.md)
> along with ADR-0005, with the additional detail live testing surfaced.
> Kept as-is below for history - not further edited.

## Context and problem statement

The query agent turns a natural-language question into a plan of deterministic
tool calls (`count_contracts` / `list_contracts` / `find_contracts` /
`aggregate_contracts` / `search_clauses`), runs them, and synthesises an answer.
Tool selection today is a keyword-regex router in
`agents/query_agent/agent.py::_guard_plan` (`_CLAUSE_RE` / `_COUNT_RE` /
`_LIST_RE` / `_MATH_RE`).

Running the benchmark question `q14` ("What are the most significant contractual
risks across our portfolio?") on the seeded portfolio exposed the failure mode:

- **The regex router cannot generalise.** "risks" matches no pattern, so the plan
  degrades to a bare `count_contracts` and the answer is "40 contracts in total."
  The fallback branch treats *any* unrecognised question as a count.
- **A benchmark shortcut is the silent default.** `.env` (gitignored) sets
  `QUERY_PLAN_TOOLS=0`, which promotes the regex router from a correction layer
  under the LLM planner to the *primary* router. This was done to get green
  small-model numbers; there is no ADR and it is invisible in code review.
- **No green signal.** `agents/tests/test_query_agent.py` is 9/12 failing on a
  pristine tree — the `6688a9c` deterministic-compose split was never reflected
  in the tests.
- **Coverage is not conveyed.** When `find_contracts` matches hundreds of
  contracts and the synthesis reads the top ~30 clauses, the answer can read as
  exhaustive.

A separate question was whether domain retrieval needs its own persistent store /
MCP server. This ADR settles both.

## Decision drivers

- Routing must handle questions the authors did not enumerate — the space of
  contract questions is open.
- ADR-0002's guarantee holds: counts, sums and date arithmetic are computed by
  deterministic tools, never by the model; errors must be attributable to the
  agent, not to data variance.
- The evaluation model is a small local one (`llama3.2:3b`); the offline reviewer
  tour must still work without a capable model in the loop.
- Every read of contract data is tenant-scoped — there is no unscoped path.
- Keep the change small: the portfolio is tens of contracts in test, low
  thousands per real tenant. SQLite scans that in milliseconds.

## Considered options

### Routing

1. **Keep extending the regex table.** Zero new concepts. Every new phrasing is a
   new `q14`; the table never converges. Rejected.
2. **Model writes SQL against the domain data (generic or custom SQLite MCP
   server), bounded by query-cost limits.** Maximum flexibility. Collides with
   ADR-0002 (the model would be computing the numbers); SQL is *harder* for a 3B
   model than filling a filter param; solves a scale problem the data does not
   have. Rejected.
3. **A catalogue of prompt templates; the model names one, which fixes its tool
   allowlist (chosen).** The templates are the spec the model generalises from —
   not an enumeration of questions. Deterministic code shrinks to filter-value
   hygiene + allowlist enforcement. A labelled degraded mode keeps a minimal
   keyword router for the no-model path.

### Retrieval

1. **Persistent per-tenant domain index / flat projection of `clm.sqlite3`
   (facet columns + FTS5 + vectors).** Real value only at volumes we do not have
   (avoiding full-aggregate hydration; avoiding per-request re-embedding). Adds a
   build step, a persist hook, a parity invariant, and a new failure surface.
   Rejected **for now**; revisit when a tenant reaches tens of thousands of
   contracts or a second consumer appears.
2. **In-process load + rank, as today, made explicit (chosen).** The query MCP
   server loads the tenant's contracts and `portfolio.py` filters in memory;
   `retrieval.py` ranks in-request. Add a `(text_hash → vector)` cache later only
   if the probe shows re-embedding is a material cost next to the 40–150s LLM
   calls.

## Decision outcome

- **D1 — Spec-driven routing.** Tool selection is expressed as prompt templates
  in `agents/query_agent/prompts/templates.yaml` (human catalogue:
  `docs/query-agent-prompt-templates.md`). Each template declares its tool
  allowlist, an instruction scaffold, and a coverage rule. `_Plan` gains a
  `template` field; the planner names one.
- **D2 — `_guard_plan` is filter-value hygiene only.** It normalises facet
  spelling (`_slug_match` / `_infer_where`), forces a parsed filter onto an
  unscoped call, and drops any planned call whose tool is not in the named
  template's allowlist. It performs **no tool selection**. The
  `_CLAUSE_RE`/`_COUNT_RE`/`_LIST_RE`/`_MATH_RE` selection branches are removed
  from the shared path.
- **D3 — Bounded clarification loop, never a fabricated plan.** A question with
  no usable plan - the LLM planner declined/timed out **and** deterministic
  keyword + facet routing (the backstop) also found nothing to project - is
  never turned into a guessed plan (not a bare `count_contracts`, not a
  synthesized search phrase, not a canned probe list). The agent instead returns
  `needs_clarification=true` with a targeted question grounded in the
  portfolio's real facets, and relies on the caller to re-ask with the enriched
  context (the human's answer usually supplies the missing filter/topic, which
  routes on the next turn). This is bounded on **both** sides:
  - the orchestrator is the primary owner - it tracks consecutive clarification
    turns per conversation and stops calling the agent, surfacing a terminal
    message itself, once `QUERY_CLARIFY_MAX_ROUNDS` is reached;
  - the agent enforces the same bound itself as a second gate (`clarify_round`
    passed by the caller, floored by a `history`-derived count when the caller
    doesn't track it) - so it never asks indefinitely even if the caller ignores
    the signal.
- **D4 — `QUERY_PLAN_TOOLS=0` is a labelled degraded mode**, not the default. It
  keeps a minimal keyword router (moved to `_deterministic_route`) that serves
  the deterministic (🟢 **D**) templates; the architecture default is
  `QUERY_PLAN_TOOLS=1`. `.env.example` carries the `=1` default with a comment.
- **D5 — Coverage is always conveyed.** `answer()` builds a `coverage` record
  (`matched`, `evidence_fed`, `truncated`, `spans_portfolio`) from the existing
  `matched` / `truncated` signals. When the matched set exceeds what the model
  read, the drafted answer must state the fraction read and offer the exact count
  or a narrower filter; `_verify` rejects an answer that implies completeness
  while `coverage` is partial.
- **D6 — Tenant scope is an invariant.** Every contract load, filter, retrieval
  and embed is scoped to the caller's `organization_id`. No tool and no template
  reads unscoped data. Stated in `templates.yaml` and the catalogue.
- **D7 — Knowledge and domain retrieval stay separate.** The query agent never
  opens `rag_knowledge.sqlite3` (extraction-only). Unchanged; recorded here as an
  invariant.
- **D8 — Retrieval stays in-process.** No persistent domain index, no new MCP
  server, no CQRS read model — deferred with the rationale in the Retrieval
  options above.

## Consequences

### Positive

- Open-ended questions (the `q14` class) route to synthesis instead of a wrong
  count, in both `QUERY_PLAN_TOOLS` modes.
- The routing spec is one reviewable YAML + one doc, not regexes spread through
  `agent.py`.
- Deterministic-arithmetic and tenant-scope guarantees are stated and testable.
- A committed subsystem probe (`platform_testing/probe/query_agent_probe.py`)
  scores the resolved plan against `expect_template` / `expect_plan` and shows
  every LLM call's exact input and output.
- Small change surface — no data-layer work.

### Negative / costs

- The template catalogue is a maintained artifact: a new question class means a
  new template in two places (YAML + doc) kept in sync.
- `QUERY_PLAN_TOOLS=1` puts an LLM planner call on the critical path; on
  `llama3.2:3b` that call runs 90–450s and can time out. The degraded mode
  remains the fallback for the offline tour, with weaker template choice for
  ambiguous questions. A LAN host running a bigger model (`gemma4:latest`) cut
  this to ~10–25s per call in testing - not a fix, a mitigation available when
  one is reachable.
- Re-embedding per request is unaddressed until a probe baseline shows it matters.

### Follow-up work

Status as of the live-testing pass that closed most of this out:

- ~~Wire `templates.yaml` into `_PLAN_PROMPT`; rewrite `_guard_plan` per
  D2–D3.~~ **Done.**
- ~~Rebuild the query MCP server `instructions` + tool docstrings from the
  catalogue.~~ **Done.**
- ~~Fix the 9 `test_query_agent.py` failures; add `expect_template` +
  allowlist assertions.~~ **Done** - rewritten, 22 query-agent-specific tests,
  full sweep 112/112 (`agents/ mcp/ web/ platform_testing/`).
- ~~Implement the `coverage` record and the `_verify` completeness check.~~
  **Done.**
- Commit a fresh probe baseline once `QUERY_PLAN_TOOLS=1` is the default -
  **superseded, not done as originally scoped.** Instead of a probe-only
  baseline, validated live through the actual production path
  (`clm-agent` CLI → API → orchestrator → MCP → agent) against a real model:
  one question per template, T1–T12, captured in
  [`docs/query-agent-quick-tour.md`](../query-agent-quick-tour.md) with 4
  open findings still flagged there (not blocking, not silently dropped).
  A `platform_testing/probe` baseline specifically is still worth committing
  separately if the structured `expect_plan` scoring is wanted alongside the
  narrative quick-tour record.
- **New this pass, not originally scoped:** two bounded in-request
  self-correction loops (gather→replan, verify→redraft) - see
  [ADR-0005](0005-query-agent-self-correction-loops.md), which this ADR's D1–D8
  remain the foundation for.

## Open questions

*Must be resolved (and this section emptied) before Status moves to Accepted.*

1. ~~Does the planner emit `calls` itself, or only name the `template` and let
   `_guard_plan` expand the template's default calls?~~ **Resolved:** the
   planner emits calls itself; `_guard_plan` never expands a template into
   calls on the model's behalf - a template named with no calls is treated as
   unrouted (D3).
2. `expiring_within_days` default for "next quarter" / "soon" — 90 is assumed
   throughout; confirm.
3. Degraded-mode `_deterministic_route`: keep the current keyword coverage
   (handles 🟢 T1–T5, T10, T11) or narrow it further?
4. `QUERY_CLARIFY_MAX_ROUNDS` default (currently 3) — confirm against real
   conversations once the probe/orchestrator can be exercised live.
5. `_plan()` is one greedy LLM call over the full template catalogue, not a
   multi-candidate search (generate several candidate templates/plans, score
   each, converge). Discussed at design-review depth and validated as sound —
   it would be a direct extension of the generate/evaluate split this ADR
   already uses once, at the very end (draft → verify), applied earlier in the
   pipeline instead of only there. Not built: cost on the evaluation model
   (each call has run 90–450s locally on `llama3.2:3b`, ~10–25s on the remote
   `gemma4:latest`) makes this a real trade-off decision, not a default to
   apply without deciding it deliberately. Revisit alongside ADR-0005's
   self-correction loops, which partially cover the same failure mode (a bad
   single-shot plan) with a cheaper, narrower bounded-retry mechanism instead
   of upfront multi-candidate evaluation.

## References

- [ADR-0002](0002-query-agent-evaluation-substrate.md) — evaluation substrate
- [ADR-0003](0003-query-agent-stress-corpus.md) — stress corpus (populates the
  in-process path for its tenant)
- [Prompt templates](../query-agent-prompt-templates.md)
- [Benchmark questions](../query-agent-benchmark-questions.md)
- [Query Agent](../../agents/query_agent/README.md)
