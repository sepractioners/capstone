# ADR-0006: Query-agent routing, retrieval, and bounded self-correction

- **Status:** Proposed
- **Date:** 2026-09-11
- **Deciders:** Capstone team
- **Relates to:** [ADR-0002](0002-query-agent-evaluation-substrate.md), [ADR-0003](0003-query-agent-stress-corpus.md)
- **Supersedes:** [ADR-0004](0004-query-agent-routing-and-retrieval.md), [ADR-0005](0005-query-agent-self-correction-loops.md)
- **Superseded by:** —

## Context and problem statement

ADR-0004 and ADR-0005 recorded this overhaul in two passes, and both kept
getting edited in place as live testing surfaced more findings after their
initial write-up - against this repo's own stated ADR discipline
(`docs/adr/README.md`: *"ADRs are immutable once Accepted... a later decision
that changes course gets its own ADR"*). Neither had reached Accepted, but
editing them repeatedly instead of writing follow-on ADRs still made the
history hard to read as one coherent design. This ADR consolidates both into
a single clean record, with the full detail live testing added along the
way. ADR-0004 and ADR-0005 are retired (Status: Rejected, Superseded by this
ADR) rather than further edited.

**The original defect** (ADR-0004's starting point): the query agent turned a
question into a plan of deterministic tool calls
(`count_contracts`/`list_contracts`/`find_contracts`/`aggregate_contracts`/`search_clauses`)
via a keyword-regex router in `_guard_plan`
(`_CLAUSE_RE`/`_COUNT_RE`/`_LIST_RE`/`_MATH_RE`). Running the benchmark
question `q14` ("What are the most significant contractual risks across our
portfolio?") exposed it: "risks" matched no pattern, the plan degraded to a
bare `count_contracts`, and the answer was "40 contracts in total." The
fallback branch treated *any* unrecognised question as a count. A gitignored
`.env` (`QUERY_PLAN_TOOLS=0`) had silently promoted this regex router from a
correction layer to the *primary* router, invisibly, with no ADR. Separately,
`agents/tests/test_query_agent.py` was 9/12 failing on a pristine tree, and a
portfolio-spanning synthesis built from a small sample of clause evidence
could read as if it covered everything.

**What live testing found after the first fix landed** (ADR-0005's starting
point, expanded here): fixing the router alone was not the end of it.
Testing the fix against real models - `llama3.2:3b` locally, `gemma4:latest`
on a LAN host - surfaced four more concrete failure modes, each fixed in
turn:

1. **A fabricated fallback, reintroduced.** The first replacement for the
   regex router still guessed a plan when nothing routed -
   `find_contracts(_fallback_phrase(question))`, a synthesized search phrase
   that matched zero contracts for q14. Caught, reverted, and redesigned as
   the bounded clarification loop (D3 below) instead.
2. **A tool-call budget too small for the template that needed it most.**
   `T9_risk_exposure_review`'s own recipe needs, per named risk topic, one
   `find_contracts` (matched count) + one `search_clauses` (real clause text)
   call - four topics × two + `list_contracts` for deadlines = 9 calls. The
   default cap of 5 silently starved this to a single `search_clauses` call
   across the whole plan. Raised to 20; the planner's own prompt text was
   also hardcoded to say "(1 to 5)" independent of the actual config value -
   fixed to read `config.max_tool_calls`.
3. **A prompt whose own wording undermined its constraint.** The interpret
   stage's system prompt said, in the same sentence, "do not invent terms the
   evidence does not contain" *and* listed example risk categories
   ("uncapped liability, penalties") as illustrations. The model copied the
   named examples into its output regardless of whether the evidence
   supported them - not because the constraint was missing, but because of
   where the examples sat relative to it. Fixed by removing the concrete
   examples and requiring every point to name the evidence entry it came
   from.
4. **A single pass with no way to notice or correct a thin result.** Every
   stage in `answer()` ran once and handed forward regardless of what it
   found - `_verify` could flag an unsupported claim and the only consequence
   was a lower confidence number, not a correction. This is what ADR-0005
   introduced the two bounded self-correction loops for (D5, D6 below).

A separate, related question - whether domain retrieval needs its own
persistent store / MCP server - is also settled here (unchanged from
ADR-0004: no, for now).

## Decision drivers

- Routing must handle questions the authors did not enumerate - the space of
  contract questions is open.
- ADR-0002's guarantee holds: counts, sums and date arithmetic are computed
  by deterministic tools, never by the model; errors must be attributable to
  the agent, not to data variance.
- The evaluation model is a small local one (`llama3.2:3b`); the offline
  reviewer tour must still work without a capable model in the loop.
- Every read of contract data is tenant-scoped - there is no unscoped path.
- Keep the change small: the portfolio is tens of contracts in test, low
  thousands per real tenant. SQLite scans that in milliseconds - this rules
  out a persistent index/projection as a solution to a scale problem that
  does not exist yet.
- **Added by live testing**: a design that reads correctly on paper is not
  validated until it has been run against a real model and the exact output
  checked line by line - several of the findings above (D3's precursor bug,
  the interpret hallucination, the tool-call starvation) would not have
  surfaced from mocked unit tests alone, all of which were green throughout.
- **Added by live testing**: any self-correction mechanism must stay bounded
  and must degrade to today's safe behaviour on exhaustion - never a third
  attempt, never worse than not looping at all. A generic, unbounded
  reflection framework was explicitly rejected in favor of narrowly-targeted
  loops tied to concrete, observed failure signatures.

## Considered options

### Routing

1. **Keep extending the regex table.** Zero new concepts. Every new phrasing
   is a new `q14`; the table never converges. Rejected.
2. **Model writes SQL against the domain data** (generic or custom SQLite MCP
   server), bounded by query-cost limits. Maximum flexibility. Collides with
   ADR-0002 (the model would be computing the numbers); SQL is *harder* for a
   3B model than filling a filter param; solves a scale problem the data does
   not have. Rejected.
3. **A catalogue of prompt templates; the model names one, which fixes its
   tool allowlist (chosen).** The templates are the spec the model
   generalises from - not an enumeration of questions. Deterministic code
   shrinks to filter-value hygiene + allowlist enforcement. A labelled
   degraded mode keeps a minimal keyword router for the no-model path.

### Retrieval

1. **Persistent per-tenant domain index / flat projection of `clm.sqlite3`**
   (facet columns + FTS5 + vectors). Real value only at volumes not present
   yet (avoiding full-aggregate hydration; avoiding per-request
   re-embedding). Adds a build step, a persist hook, a parity invariant, and
   a new failure surface. Rejected **for now**; revisit at tens of thousands
   of contracts per tenant or a second consumer.
2. **In-process load + rank, as today, made explicit (chosen).** The query
   MCP server loads the tenant's contracts and `portfolio.py` filters in
   memory; `retrieval.py` ranks in-request.

### Self-correction (a question ADR-0004 did not address)

1. **A general N-stage reflection framework** - any stage can request a
   retry of any earlier stage, generically. Maximum flexibility, but no
   evidence from live testing supports needing it, and it multiplies the
   failure surface (a generic retry-routing layer is itself a new thing to
   get wrong). Rejected.
2. **Two narrowly-targeted bounded loops, one per concrete gap observed
   (chosen).** Gather → replan when a synthesis template's evidence comes
   back empty; verify → redraft when a claim is flagged unsupported. Each
   independently bounded, each with an unconditional exhaustion path back to
   pre-loop behaviour.
3. **Do nothing; treat the gaps as an accepted model-capability ceiling.**
   Cheapest, and possibly sufficient if a bigger model doesn't need this
   either - but the gaps were reproducible and the fix is small and bounded,
   so deferring indefinitely wasn't justified.

### Tool-call reasoning depth (a question neither prior ADR formally decided)

1. **Tree-of-thought / multi-candidate planning** - generate several
   candidate templates or plans, score each, converge on the best, at both
   the template-selection and tool-call-plan stages. Architecturally sound -
   a direct extension of the generate/evaluate split this design already
   uses once, at the very end (`draft` → `verify`) - applied earlier in the
   pipeline instead of only there. Not chosen for this pass: cost on the
   evaluation model is real (each call ran 90-450s locally on
   `llama3.2:3b`, ~10-25s on the remote `gemma4:latest`), and this is a
   trade-off decision that deserves its own deliberate choice, not a default
   applied as a side effect. Left as an open question (below), not rejected
   outright.
2. **Single greedy generation over the full template catalogue presented at
   once (chosen, unchanged from ADR-0004).** Cheaper; leans on downstream
   backstops (guard, deterministic route, the two self-correction loops, the
   clarification loop) to catch what a single pass gets wrong, rather than
   preventing the wrong pick upfront.

## Decision outcome

### Routing and retrieval (from ADR-0004, restated)

- **D1 - Spec-driven routing.** Tool selection is expressed as prompt
  templates in `agents/query_agent/prompts/templates.yaml` (human catalogue:
  `docs/query-agent-prompt-templates.md`). Each template declares a tool
  allowlist, a planning `scaffold`, and - for the four templates whose mode
  is `S` (T6-T9) - a `deduction_procedure` (see D9 below). `_Plan` carries a
  `template` field; the planner names one from the full catalogue in a
  single call (see the "Tool-call reasoning depth" option above and open
  question 5).
- **D2 - `_guard_plan` is filter-value hygiene only.** It normalises facet
  spelling (`_slug_match`/`_infer_where`), forces a parsed filter onto an
  unscoped call, and drops any planned call whose tool is not in the named
  template's allowlist. It performs **no tool selection** - the
  `_CLAUSE_RE`/`_COUNT_RE`/`_LIST_RE`/`_MATH_RE` branches this design
  replaced are gone from the shared path entirely.
- **D3 - Bounded clarification loop, never a fabricated plan.** A question
  with no usable plan - the LLM planner declined/timed out **and**
  deterministic keyword+facet routing (the backstop) also found nothing to
  project - is never turned into a guessed plan (not a bare `count_contracts`,
  not a synthesized search phrase, not a canned probe list - see Context
  item 1). The agent returns `needs_clarification=true` with a targeted
  question grounded in the portfolio's real facets. Bounded on both sides:
  the orchestrator is the primary owner (tracks consecutive clarification
  turns per conversation, stops calling the agent and surfaces a terminal
  message once `QUERY_CLARIFY_MAX_ROUNDS` is reached); the agent enforces the
  same bound itself as a second gate (`clarify_round` passed by the caller,
  floored by a `history`-derived count when the caller doesn't track it).
- **D4 - `QUERY_PLAN_TOOLS=0` is a labelled degraded mode**, not the
  default. It keeps a minimal keyword router (`_deterministic_route`) that
  serves the deterministic (🟢 **D**) templates; the architecture default is
  `QUERY_PLAN_TOOLS=1`.
- **D5 - Coverage is always conveyed.** `answer()` builds a `coverage` record
  (`matched`, `evidence_fed`, `truncated`, `spans_portfolio`) from the
  existing `matched`/`truncated` signals. When the matched set exceeds what
  the model read, the drafted answer must state the fraction read and offer
  the exact count or a narrower filter; `_verify` rejects an answer that
  implies completeness while `coverage` is partial.
- **D6 - Tenant scope is an invariant.** Every contract load, filter,
  retrieval and embed is scoped to the caller's `organization_id`. No tool
  and no template reads unscoped data.
- **D7 - Knowledge and domain retrieval stay separate.** The query agent
  never opens `rag_knowledge.sqlite3` (extraction-only).
- **D8 - Retrieval stays in-process.** No persistent domain index, no new
  MCP server, no CQRS read model.

### Self-correction (from ADR-0005, restated)

- **D9 - Gather sufficiency → bounded replan.** If the named template's mode
  needs real synthesis (`S`) and `gather()` returned zero clause snippets,
  replan once with that specific gap named in the planner's context (a fact,
  not a directed fix - stays clear of D2), then gather again. Bounded by
  `config.gather_replan_max_rounds` (`QUERY_GATHER_REPLAN_MAX_ROUNDS`,
  default 1; `0` disables). Exhausted: proceed exactly as if this loop didn't
  exist - interpret skips itself, the deterministic-compose safety net or a
  thin LLM draft runs unchanged.
- **D10 - Verify sufficiency → bounded redraft.** If `verify()`'s raw
  `_Verification` has `supported=False` or non-empty
  `unsupported_citation_labels`, redraft once with those specific labels
  named, then verify again. Bounded by `config.draft_reverify_max_rounds`
  (`QUERY_DRAFT_REVERIFY_MAX_ROUNDS`, default 1; `0` disables). Only wraps the
  LLM `draft`/`verify` pair, never `_compose_deterministic` (already grounded
  1:1 in tool output). Exhausted: ship the last draft with the existing
  `confidence = min(draft.confidence, verify.adjusted_confidence)` cap,
  applied uniformly whether it's the first or the last round.
- **D11 - Both loops are probabilistic improvements, not guarantees.**
  Stated explicitly so the goal is never overclaimed: bounded rounds, and on
  exhaustion, fall through to the pre-loop behaviour unchanged - never a
  fabrication, never an infinite loop, never worse than not looping at all.

### Template content (new, not formally recorded in either prior ADR)

- **D12 - Every `S`-mode template (T6-T9) gets a `deduction_procedure`
  field**: evidence → judgment reasoning, distinct from `scaffold` (which
  covers tool sequencing/gathering). Written as an active, step-ordered
  directive with a mandatory show-your-work field, not a passive list of
  criteria - a criteria list alone was tried first and had no measurable
  effect on model output (see Consequences). **Not yet wired into any
  production code path** - `_interpret()` and `_draft_answer()` are
  template-agnostic today; this field is populated and tested via a scratch
  harness, not read by `agent.py`. Wiring it in is deliberately left as
  follow-up work, not done here.
- **D13 - Every `D`-mode template (T1-T5, T10-T12) gets explicit
  tool/parameter-derivation rules merged into its `scaffold`.** Planning is
  the only LLM-touched decision point for these templates (no separate draft
  call); `scaffold` is the field actually wired into `_plan_prompt()`, so
  derivation guidance belongs there, not in a separate unwired field.
  Concretely: which tool variant to pick (e.g. `count_contracts` vs.
  `aggregate_contracts`), how to derive `group_by`/`measure`/query-phrase
  values from the question's own wording. Live-validated: T1's group-by
  derivation rule was followed correctly on the first live run against
  `gemma4:latest`, with the resolved plan's `reasoning` field echoing the
  rule back.

## Consequences

### Positive

- Open-ended questions (the `q14` class) route to synthesis instead of a
  wrong count, in both `QUERY_PLAN_TOOLS` modes.
- The routing spec is one reviewable YAML + one doc, not regexes spread
  through `agent.py`.
- Deterministic-arithmetic and tenant-scope guarantees are stated and
  testable.
- The `q14`-class thin-gather failure gets a second attempt before falling
  back to a count-only answer; an unsupported claim gets a bounded chance at
  correction instead of only a lower confidence number.
- Small change surface for the self-correction loops specifically - no new
  schema fields on `_Plan`/`_ToolCall`/`QueryAnswer` (feedback is a plain
  optional string parameter, added to the LLM call's context dict only when
  non-empty).
- Validated against real models, not only mocked tests: `llama3.2:3b`
  locally and `gemma4:latest` on a LAN host, including one full pass through
  the actual production path (`clm-agent` CLI → authenticated API →
  orchestrator → MCP → agent) for one question per template -
  [`docs/query-agent-quick-tour.md`](../query-agent-quick-tour.md).

### Negative / costs

- The template catalogue is a maintained artifact: a new question class
  means a new template in (up to) three places (`templates.yaml`, the human
  catalogue doc, and possibly the quick tour) kept in sync.
- `QUERY_PLAN_TOOLS=1` puts an LLM planner call on the critical path; on
  `llama3.2:3b` that call runs 90-450s and can time out. A LAN host running a
  bigger model cut this to ~10-25s in testing - a mitigation when reachable,
  not a fix for the offline tour, which still relies on the degraded mode.
- Each self-correction loop adds at most one extra LLM call; worst case
  (both loops fire) roughly doubles the latency of an already-slow request.
  Both are individually disable-able (`=0`) for the offline tour.
- **Live evidence that explicit instructions do not guarantee compliance on
  a small model.** A structural directive ("one `what_matters` point per
  clause, never one per dimension") was given to `llama3.2:3b` twice,
  reworded and reinforced the second time, and was not followed either time.
  This is treated as real evidence of a capability ceiling for some
  instructions on this model size, not a wording problem to keep iterating
  on - see `MCP_HEURISTICS.md` Pattern 6 for the full write-up. The practical
  implication: a scaffold's constraints reduce but cannot be the *only*
  defence against a small model's mistakes - pair them with an independent
  check (verify re-reading the draft against deterministic data) and a safe
  fallback (deterministic compose), not just a better-worded prompt.
- Re-embedding per request is unaddressed until a probe baseline shows it
  matters.

### Follow-up work

- Wire `deduction_procedure` (D12) into `_interpret()`/`_draft_answer()` for
  real, or decide it isn't worth the added prompt length given the
  structural-instruction-following evidence above.
- The four open findings flagged live in
  [`docs/query-agent-quick-tour.md`](../query-agent-quick-tour.md): T6
  answering from cross-contract evidence instead of the one named contract;
  T7's `find_contracts` AND-matching too literally ("payment obligations"
  found nothing); T10 listing contracts instead of obligation → party →
  due-date rows; T12's routing on one live run could not be confirmed from
  available logs.
- A `platform_testing/probe` baseline with `QUERY_PLAN_TOOLS=1` as the
  default, complementing the narrative quick-tour record with structured
  `expect_plan` scoring.
- Try the same questions against a bigger model on the remote host as a
  cheap way to characterise whether the structural-instruction-following gap
  (Consequences, above) is `llama3.2:3b`-specific or general.
- `auto_renew` as a structured `where` filter - `find_contracts` cannot match
  "auto-renewal" as a topic because the data encodes it as a
  `renewal_terms.auto_renew` boolean and prose that never contains the word
  "auto"; this is a tool/data mismatch, not a routing or self-correction
  concern, and is unaddressed by this ADR.

## Open questions

*Must be resolved (and this section emptied) before Status moves to Accepted.*

1. `expiring_within_days` default for "next quarter"/"soon" - 90 is assumed
   throughout; confirm.
2. Degraded-mode `_deterministic_route`: keep the current keyword coverage
   (handles 🟢 T1-T5, T10, T11) or narrow it further?
3. `QUERY_CLARIFY_MAX_ROUNDS` default (currently 3), `QUERY_GATHER_REPLAN_MAX_ROUNDS`
   and `QUERY_DRAFT_REVERIFY_MAX_ROUNDS` defaults (currently 1 each) - confirm
   against real conversations and real load, not just the single-question
   live tests run so far.
4. Tree-of-thought / multi-candidate planning (Considered options,
   "Tool-call reasoning depth") - deliberately left undecided rather than
   defaulted into. Revisit once the structural-instruction-following
   question (Consequences) has more evidence: if the gap turns out to be a
   small-model ceiling, multi-candidate search at planning time is a
   stronger candidate fix than more prompt wording.
5. Whether the four quick-tour findings (Follow-up work) are prompt-wording
   gaps (fixable the way T1's group-by rule was) or the same
   structural-instruction-following ceiling seen in the deduction-procedure
   tests - unclear without dedicated follow-up runs per finding.

## References

- [ADR-0002](0002-query-agent-evaluation-substrate.md) - evaluation substrate
- [ADR-0003](0003-query-agent-stress-corpus.md) - stress corpus (populates the
  in-process path for its tenant)
- [ADR-0004](0004-query-agent-routing-and-retrieval.md) - superseded by this
  ADR; retained for history
- [ADR-0005](0005-query-agent-self-correction-loops.md) - superseded by this
  ADR; retained for history
- [Prompt templates](../query-agent-prompt-templates.md)
- [Benchmark questions](../query-agent-benchmark-questions.md)
- [Quick tour](../query-agent-quick-tour.md) - one real question per template,
  run through the production CLI path
- [Query Agent](../../agents/query_agent/README.md)
- `MCP_HEURISTICS.md` Pattern 6, `AGENT_HYPOTHESES.md` H5/VH2 - the
  structured-reasoning-scaffold findings referenced in Consequences
