# ADR-0005: Bounded in-request self-correction (replan-on-thin-gather, redraft-on-unsupported)

- **Status:** Rejected
- **Date:** 2026-09-11
- **Deciders:** Capstone team
- **Relates to:** [ADR-0004](0004-query-agent-routing-and-retrieval.md)
- **Supersedes:** —
- **Superseded by:** [ADR-0006](0006-query-agent-routing-retrieval-and-self-correction.md)

> **Retired.** Consolidated into [ADR-0006](0006-query-agent-routing-retrieval-and-self-correction.md)
> along with ADR-0004, with the additional detail live testing surfaced.
> Kept as-is below for history - not further edited.

## Context and problem statement

ADR-0004 made every stage of `answer()` (plan → gather → interpret → coverage →
draft → verify) run at most once and hand forward regardless of what it found -
the fix for that ADR's bug was making "admit I can't answer" a legal outcome
instead of a fabricated one. That scope boundary was deliberate, but live
testing against `llama3.2:3b` after ADR-0004 landed exposed two specific gaps
where a later stage's finding never changes what an earlier stage did:

1. **Gather can come back thin for a template that structurally needs real
   evidence, and nothing notices.** Running the benchmark question
   `q14_portfolio_risk_summary` repeatedly against `T9_risk_exposure_review`
   (mode `S` - needs synthesis over real clause text) produced a plan that
   called `find_contracts` for every named risk topic (match counts only) but
   `search_clauses` (the only tool that returns clause text) for **zero**
   topics, more than once across separate runs even after raising
   `QUERY_MAX_TOOL_CALLS` and rewording the template scaffold to pair the two
   tools per topic. Interpret correctly skipped itself on zero snippets, and
   `_compose_deterministic` correctly produced a safe, fully-cited, count-only
   answer - honest, but never a **second chance** at synthesising the actual
   risk review the question asked for.
2. **Verify can flag an unsupported claim, and the only consequence is a lower
   confidence number.** `_verify` already checks the draft against
   deterministic data and returns `unsupported_citation_labels` for claims it
   can't back - but that only fed `confidence = min(draft.confidence,
   verify.adjusted_confidence)`. The unsupported claim itself was never removed
   or corrected before the answer shipped; it stayed in the response text.

A separate finding from the same live testing - `find_contracts` structurally
cannot match "auto-renewal" as a topic because the data encodes it as a
`renewal_terms.auto_renew` boolean and prose that never contains the word
"auto" - is **not** addressed by this ADR. That is a tool/data mismatch fixable
with a structured filter, independent of model behaviour or self-correction;
tracked separately.

## Decision drivers

- Every invariant from ADR-0004 must survive unchanged: bounded rounds, and on
  exhaustion, fall through to the existing safe behaviour - never a
  fabrication, never an infinite loop, never worse than not looping at all.
- `_guard_plan` must not gain tool-selection logic (ADR-0004 D2) - feedback
  passed back into a replan must name the *gap*, never the *fix*.
- The evaluation model is a small local one; each LLM call has run 90-190s live
  in this session. A corrective loop roughly doubles worst-case latency for
  exactly the questions that are already the slowest (open-ended synthesis) -
  the design must keep that cost visible and minimal by default.
- Reuse the shape of the one bounded-retry precedent already in the codebase
  (`agent_llm.client.acall_retrying`: a `should_retry` predicate, a capped
  loop, a hint appended on retry) rather than inventing a new retry idiom.

## Considered options

1. **A general N-stage reflection framework** (any stage can request a retry of
   any earlier stage, generically). Maximum flexibility, but no evidence from
   this session supports needing it, and it multiplies the failure surface (a
   generic retry-routing layer is itself a new thing to get wrong). Rejected.
2. **Two narrowly-targeted bounded loops, one per concrete gap observed
   (chosen).** Loop A: gather → replan, triggered only when a synthesis-mode
   template's gather produced zero clause text. Loop B: verify → redraft,
   triggered only when verify flags an unsupported claim. Each loop is capped
   independently, each has an unconditional exhaustion path back to
   pre-ADR-0005 behaviour.
3. **Do nothing; treat the observed gaps as an accepted model-capability
   ceiling.** Cheapest, and possibly correct if a bigger model turns out not to
   need this either - but the gaps are reproducible and the fix is small and
   bounded, so deferring it indefinitely isn't justified yet.

## Decision outcome

Option 2.

- **D1 - Loop A (gather → replan).** After `_gather()`, if the named
  template's YAML `mode` contains `S` (`_TEMPLATE_NEEDS_EVIDENCE`, built the
  same way as `_TEMPLATE_TOOLS`) and `gathered["snippets"]` is empty, replan
  once via `_plan(..., feedback=<gap>)` then gather again, bounded by
  `config.gather_replan_max_rounds` (default 1, env `QUERY_GATHER_REPLAN_MAX_ROUNDS`).
  The feedback text states the fact ("you gathered match counts but no clause
  text") never the fix ("call search_clauses") - the model still chooses the
  calls. Exhausted: proceed exactly as pre-ADR-0005 (interpret skips itself,
  the deterministic-compose safety net or a thin LLM draft runs unchanged).
- **D2 - Loop B (verify → redraft).** Only wraps the LLM `_draft_answer()` /
  `_verify()` pair - never `_compose_deterministic()`, which is already
  grounded 1:1 in tool output. If `verify()`'s raw `_Verification` (now
  returned alongside the adjusted `QueryAnswer` - see D4) has
  `supported=False` or non-empty `unsupported_citation_labels`, redraft once
  via `_draft_answer(..., feedback=<the specific labels>)` then verify again,
  bounded by `config.draft_reverify_max_rounds` (default 1, env
  `QUERY_DRAFT_REVERIFY_MAX_ROUNDS`). Exhausted: ship the last draft with the
  existing `confidence = min(draft.confidence, verify.adjusted_confidence)`
  cap - unchanged from pre-ADR-0005 behaviour, applied uniformly whether it's
  the first or the last round.
- **D3 - No schema changes for feedback.** Both `_plan()` and `_draft_answer()`
  gain an optional `feedback: str = ""` parameter, added to the LLM call's
  user payload dict as `prior_attempt_gap` / `prior_attempt_unsupported` only
  when non-empty. `_Plan` / `_ToolCall` / `QueryAnswer` are unchanged.
- **D4 - `_verify()` returns `tuple[QueryAnswer, _Verification | None]`.** The
  raw verification (previously discarded after producing the adjusted answer)
  is what `answer()` checks to decide whether a redraft is worth trying. Its
  only call site is `answer()` itself; no other module calls `_verify()`
  directly.
- **D5 - Trace stays probe-compatible with no probe changes.** Both loops
  reuse the existing phase names (`"plan"` / `"plan_resolved"` / `"draft_answer"`
  / `"verify"`) rather than inventing new ones - `platform_testing/probe/query_agent_probe.py`'s
  `_LLM_PHASES` allowlist and `_resolved_plan()` (which already reads the
  *last* `"plan_resolved"` step) both keep working across a replan/redraft
  round unmodified. A retry round is distinguishable in the trace by the
  presence of `prior_attempt_gap` / `prior_attempt_unsupported` in that
  step's recorded context, and by an explicit `note` on the manually-recorded
  `"plan_resolved"` steps.
- **D6 - Both loops are probabilistic improvements, not guarantees.** Stated
  explicitly so the goal isn't overclaimed: these loops improve how often a
  well-evidenced, verified answer comes out on the first request, for the
  failure modes observed. They do not guarantee every question gets a
  complete synthesis - a small model can still exhaust its retry budget. What
  is guaranteed is termination and safety: bounded rounds, and on exhaustion,
  the answer is never worse than it would have been with no loop at all.

## Consequences

### Positive

- The `q14`-class thin-gather failure now gets a real second attempt before
  falling back to a count-only answer, in both directions this session
  observed (sometimes the model pairs 2-4 topics with real evidence given the
  chance; the replan gives it one more chance to do so consistently).
- An unsupported claim that survives to the draft no longer merely lowers a
  confidence number while staying in the response text - it gets a bounded
  chance at correction.
- No new schema surface, no new trace-consumer changes, no change to
  ADR-0004's routing/allowlist/tenant-scope invariants.

### Negative / costs

- Worst case adds 2 extra LLM calls (1 replan + 1 redraft) on top of the
  existing up to 4 (plan, interpret, draft, verify) - on `llama3.2:3b`, each
  call has run 90-190s live this session, so a worst-case request roughly
  doubles in latency. Defaults are the smallest useful bound (1 round each,
  not more) given this cost; both are independently disable-able (`=0`) for
  the offline/degraded-mode tour.
- Two more config knobs to explain (`QUERY_GATHER_REPLAN_MAX_ROUNDS`,
  `QUERY_DRAFT_REVERIFY_MAX_ROUNDS`).

### Follow-up work

- Validate live: rerun `q14` against `llama3.2:3b` 3-5 times with both loops
  enabled; compare the rate of a real multi-topic synthesis against the
  un-looped baseline from the ADR-0004 live-testing session.
- Confirm the simpler D-mode templates (T1-T5, T10-T12) never trigger either
  loop via `platform_testing/probe/query_agent_probe.py --all`.
- Try the same question against a more capable local model (`gemma4:latest`)
  to characterize whether the gap these loops address is a capability ceiling
  specific to `llama3.2:3b`, informing whether the round-count defaults should
  differ by model tier.
- The `auto-renewal` find_contracts/data mismatch (Context, above) - separate,
  smaller fix, not a self-correction concern.

## Open questions

*Must be resolved (and this section emptied) before Status moves to Accepted.*

1. `QUERY_GATHER_REPLAN_MAX_ROUNDS` / `QUERY_DRAFT_REVERIFY_MAX_ROUNDS` default
   of 1 each - confirm against the live multi-run validation (follow-up work,
   above) once it's been done; may warrant a different default per loop.
2. Whether the gather-thinness gap is a `llama3.2:3b` capability ceiling or a
   scaffold-wording gap that would recur on any model - pending the `gemma4`
   comparison.

## References

- [ADR-0004](0004-query-agent-routing-and-retrieval.md) - spec-driven routing;
  the invariants this ADR builds on
- [Prompt templates](../query-agent-prompt-templates.md)
- [Query Agent](../../agents/query_agent/README.md)
