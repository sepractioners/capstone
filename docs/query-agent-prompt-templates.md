# Query-Agent Prompt Templates

The routing specification the query agent's planner reasons from — a catalogue of
**prompt templates**, each declaring the tools it may use, the instruction
scaffold, and its coverage rule. The planner names one template per question;
that fixes the tool allowlist. `_guard_plan` then does only filter-value hygiene
(facet spelling, forcing a parsed filter onto an unscoped call) and drops any
call outside the named template's tools. **No tool selection lives in code.**

- Machine copy the planner loads: [`agents/query_agent/prompts/templates.yaml`](../agents/query_agent/prompts/templates.yaml)
- Decision record: [ADR-0004](adr/0004-query-agent-routing-and-retrieval.md)
- Benchmark questions: [`docs/query-agent-benchmark-questions.md`](query-agent-benchmark-questions.md)
- **Which standing hypothesis each template enforces:** [`agents/query_agent/README.md`](../agents/query_agent/README.md#original-hypothesis--template-mapping)

**Invariant — tenant scope:** every tool call is scoped to the caller's
`organization_id`. There is no unscoped read of contract data on any path.

**Invariant — deterministic arithmetic:** counts, sums, and date math are
computed by the tools, never by the model.

## Tools

🔢 `count_contracts` · 📇 `list_contracts` · 🔎 `find_contracts` · ∑ `aggregate_contracts` · 📄 `search_clauses`

## Mode markers

🟢 **D** deterministic — composes with no LLM draft; the only templates the
`QUERY_PLAN_TOOLS=0` degraded mode routes to well ·
🔵 **S** needs LLM synthesis over retrieved evidence ·
⚠️ **cov** coverage-sensitive — when the matched set exceeds what the model read,
the answer must say so and offer the exact count or a narrower filter.

---

## Question taxonomy → templates

| Category | Template | Mode |
|---|---|---|
| 📊 Portfolio census (how many / breakdown) | T1 `portfolio_census` | 🟢 |
| 📇 Filtered roster (list matching structured criteria) | T2 `filtered_roster` | 🟢 ⚠️ |
| 🔍 Clause presence (which contracts contain phrase X) | T3 `clause_presence` | 🟢 ⚠️ |
| 💰 Financial aggregation (sum / avg / min / max value) | T4 `financial_rollup` | 🟢 |
| 📅 Temporal / lifecycle (expiring, renewing, signed when) | T5 `expiring_and_renewals` | 🟢→🔵 |
| 📄 Clause detail (one/few contracts) | T6 `clause_detail` | 🔵 |
| 🧩 Cross-contract synthesis ("what are our X across all") | T7 `cross_contract_synthesis` | 🔵 ⚠️ |
| ⚖️ Comparative / consistency | T8 `comparative_review` | 🔵 ⚠️ |
| 🚨 Open-ended risk / exposure | T9 `risk_exposure_review` | 🔵 ⚠️ |
| ✅ Obligation / action tracking | T10 `obligation_tracker` | 🟢 |
| 🤝 Counterparty analysis | T11 `counterparty_profile` | 🟢 |
| 🚫 Out-of-scope / advice | T12 `out_of_scope` | — |
| 🔄 Multi-turn follow-up | *inherits the template the follow-up implies* | — |

**T9 is suggested to the planner** for a question that fits no other template —
an open analytical ask like "what should I worry about": decompose into probes,
retrieve, synthesise. It is advisory to the *model*, not a code fallback: if the
model doesn't route (declines, times out, or names T9 with no calls) **and**
deterministic keyword/facet routing also finds nothing, the agent does not
guess a plan on the model's behalf. It asks the human — a targeted question
grounded in the portfolio's real facets — and tries again once the answer
enriches the context, bounded by `QUERY_CLARIFY_MAX_ROUNDS` on both the
orchestrator and the agent. See [ADR-0004 D3](adr/0004-query-agent-routing-and-retrieval.md).

**Degraded mode** (`QUERY_PLAN_TOOLS=0`, no model in the routing loop) routes
deterministically and serves the 🟢 templates well; 🔵 questions still reach an
LLM draft but the template choice for ambiguous questions is weaker.

---

## Templates

Field key: 🎯 intent · 🗣️ cues · 🛠️ tools + plan · 📤 answer · 🚧 coverage · 🛑 escalate

### 📊 T1 · `portfolio_census` — 🟢
- 🎯 A count or breakdown of the portfolio
- 🗣️ "how many contracts", "break down by type", "count of NDAs", "how many of each status"
- 🛠️ 🔢 `count_contracts(filter?)` — or ∑ `aggregate_contracts(measure=count, group_by=…)` when grouped. No text tool.
- 📤 total + breakdown book, tool-verbatim; cite `portfolio`
- 🛑 never — always answerable

### 📇 T2 · `filtered_roster` — 🟢 ⚠️
- 🎯 List the contracts matching structured criteria
- 🗣️ "list active vendor agreements", "which contracts are with Acme", "show approved MSAs"
- 🛠️ 📇 `list_contracts(where=…)` (exact facet spelling); `detail=full` only for a small set; add 🔢 for a count
- 🚧 matched > rows returned → "N match — showing first K"
- 🛑 never

### 🔍 T3 · `clause_presence` — 🟢 ⚠️
- 🎯 Which contracts contain / require / mention a phrase
- 🗣️ "which contracts require liability insurance", "do any have a non-compete", "mentioning arbitration"
- 🛠️ 🔎 `find_contracts(query=<key phrase only>, where?)` — full text scan; **not** 📄
- 🚧 exact matched count is authoritative; names to the cap + "and N more"
- 🛑 vague phrase ("problematic terms") → hand to 🚨 T9

### 💰 T4 · `financial_rollup` — 🟢
- 🎯 sum / avg / min / max of contract value
- 🗣️ "total value of active contracts", "average value by type", "how much do we pay Acme", "deals over $1M"
- 🛠️ ∑ `aggregate_contracts(measure=…, group_by?, where?)`; 📇 `list_contracts(min_value=)` for "over $X"
- 📤 tool-computed figure(s) only — **model never does arithmetic**
- 🛑 value data absent → "contract value isn't recorded for these"

### 📅 T5 · `expiring_and_renewals` — 🟢 → 🔵
- 🎯 What's expiring / renewing / was signed when
- 🗣️ "expiring next quarter", "renews automatically this year", "signed in 2024", "up for renewal"
- 🛠️ 📇 `list_contracts(expiring_within_days=90 | effective_year=…)` (pass days, never compute a date); add 📄 `"renewal notice period"` **only** if asked what notice is required
- 🚧 convey matched count
- 🛑 never for the list; notice detail is 📄 T6

### 📄 T6 · `clause_detail` — 🔵
- 🎯 What a specific clause says, for one or a few contracts
- 🗣️ "what does the indemnity clause in the Acme MSA say", "explain termination terms for X", "liability cap in our largest deal"
- 🛠️ 📇 `list_contracts` to resolve the named contract if needed → 📄 `search_clauses(query=<topic>)` scoped
- 📤 the clause reading + citation; "not stated in <contract>" when absent
- 🚧 bounded by construction — low risk

### 🧩 T7 · `cross_contract_synthesis` — 🔵 ⚠️
- 🎯 "What are our X across the portfolio"
- 🗣️ "payment obligations across all contracts", "our indemnification exposure", "how is liability limited across the portfolio"
- 🛠️ 🔎 `find_contracts(query=<topic phrase>)` for the matched set + 📄 `search_clauses(query=<question>)` for top-K evidence → interpret → draft
- 🚧 **required:** "based on the N most relevant clauses across M matching contracts — ask about a specific contract or request the full list"
- 🛑 never — but must not imply completeness

### ⚖️ T8 · `comparative_review` — 🔵 ⚠️
- 🎯 Compare a contract to a cohort, or check consistency
- 🗣️ "how does the Acme deal compare to our other vendor agreements", "are our NDAs consistent", "which contracts have the most unfavourable terms"
- 🛠️ 📇 `list_contracts(where=<cohort>)` + 📄 `search_clauses(<the terms>)` → interpret → draft
- 🚧 state cohort size vs how many were examined
- 🛑 "unfavourable" with no criterion → ask which dimension, or fall to 🚨 T9

### 🚨 T9 · `risk_exposure_review` — 🔵 ⚠️ · **fallback**
- 🎯 "What should I worry about"
- 🗣️ "biggest contractual risks", "where are we most exposed", "what needs attention" — **and any question that fits no other template**
- 🛠️ decompose into topic **pairs**: for each of indemnification, limitation of liability, termination for convenience, auto-renewal → 🔎 `find_contracts(query=<topic>)` (matched count) **and** 📄 `search_clauses(query=<topic>)` (real clause text — 🔎 alone never returns text); also 📇 `list_contracts(expiring_within_days=90)` → interpret(`what_matters`, evidence-grounded only) → draft. `QUERY_MAX_TOOL_CALLS` (default 20) covers the full 4-topic pairing + the deadline check with headroom to spare.
- 📤 prioritised, severity-tagged findings + citations; never a risk without a cited clause — a topic matched via 🔎 but never read via 📄 is a named gap, not a finding
- 🚧 **required:** "reviewed <these dimensions> across N contracts — a first pass, not exhaustive"

### ✅ T10 · `obligation_tracker` — 🟢
- 🎯 What do we owe, when, to whom
- 🗣️ "what do we owe and when", "obligations due soon", "our reporting obligations"
- 🛠️ 📇 `list_contracts(detail=full)` for obligations, or 🔎 `find_contracts` on obligation text; date-bound where implied
- 📤 obligation → responsible party → due date; never invent a date
- 🛑 never

### 🤝 T11 · `counterparty_profile` — 🟢
- 🎯 Everything about / ranking of parties
- 🗣️ "everything with Acme", "top counterparties by value", "who have we signed the most with"
- 🛠️ 📇 `list_contracts(party=…)`; ∑ `aggregate_contracts(group_by=party)` for rankings
- 📤 roster or ranking, tool-verbatim
- 🛑 never

### 🚫 T12 · `out_of_scope` — no tools
- 🎯 Legal opinion, market comparison, business recommendation
- 🗣️ "should we renew", "is this clause market-standard", "what happens if we breach"
- 🛠️ none → "I can report what your contracts say, not whether you should act / what is market-standard / what a court would do"
- 🛑 always; offer the in-scope reframe

### 🔄 Multi-turn follow-up
- 🗣️ "tell me more", "what about the second one", "and the termination terms"
- 🛠️ resolve the referent from `history` + prior cited `contract_id`s → apply the template the follow-up implies (usually 📄 T6)

---

## How the taxonomy feeds the build

| Consumer | Takes from here |
|---|---|
| `_PLAN_PROMPT` (`agents/query_agent/agent.py`) | the template list + cues; returns `{template, reasoning, calls}` |
| `agents/query_agent/prompts/templates.yaml` | id → tools / cues / scaffold / coverage (source of truth for `_plan`) |
| `mcp/query_mcp_server/server.py` `instructions` + tool docstrings | per-tool "use this not that" (🔍 T3: `find_contracts` not `search_clauses`; 📄 T6: the reverse) |
| `agents/query_agent/prompts/contract_query.yaml` | answer-shape + coverage phrasing for 🔵 templates |
| `platform_testing/fixtures/query_bench_questions.jsonl` | `expect_template` + `expect_plan` per question |
| degraded mode (`QUERY_PLAN_TOOLS=0`) | routes the 🟢 templates deterministically |
