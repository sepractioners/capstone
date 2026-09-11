# Query Agent — Consolidated Benchmark Report

*Re-gathered 2026-09-09 from the codebase, docs, git history, and the recovered
deleted files. This document collates every benchmark fact that exists for the
query agent; nothing here is a new run.*

> **Update (routing overhaul).** The routing described below (`_guard_plan`
> keyword tool-selection, `QUERY_PLAN_TOOLS=0` as the effective default) has been
> replaced — see [ADR-0006](adr/0006-query-agent-routing-retrieval-and-self-correction.md) and
> [the prompt-template catalogue](query-agent-prompt-templates.md). Routing is now
> a named prompt template per question; `_guard_plan` is filter-value hygiene
> only; `q14` routes to `T9_risk_exposure_review` instead of a bare count. The
> committed baseline (`platform_testing/reports/query-probe-20260909T182544Z.*`)
> is the *pre-overhaul* picture; re-run the probe
> (`platform_testing/probe/query_agent_probe.py`) for the current one.

---

## 0. Provenance of the source material

| Source | Location | State |
|---|---|---|
| Benchmark harness (current) | `platform_testing/query_bench.py` | committed `aecc835` |
| Question set + ground truth | `platform_testing/fixtures/query_bench_questions.jsonl` | committed `aecc835`, 6 questions |
| Harness docs | `platform_testing/README.md` §Benchmarks | committed |
| Raw run output | `platform_testing/reports/query_bench.tsv` | **gitignored, never tracked**; partial run 2026-09-09 02:16 |
| Generated `query-bench-<stamp>.{json,md}` | `platform_testing/reports/` | **none — no run was ever committed** |
| Analysis + results narrative | `docs/query-agent-small-model-analysis.md` | **DELETED** `1224b29`; recovered here from `git show 1224b29^:…` |
| Old harness | `scripts/bench-query-agent.sh` | **DELETED** `aecc835`; recovered here |
| Old scorer | `scripts/bench_score.py` | **DELETED** `aecc835`; recovered here |
| Expected deterministic answers | `README.md` §Validation Data, `docs/adr/0002` | committed |
| Query-agent hypotheses (H2 history, H5 structured prompts) | [`AGENT_HYPOTHESES.md`](../../../docs/hypotheses/agent-hypotheses.md) | committed, untested |

Recovered files sit next to this report:
`query-agent-small-model-analysis.md`, `bench-query-agent.sh`, `bench_score.py`.

Deleted-file history:
- `docs/query-agent-small-model-analysis.md` — introduced `6688a9c`, extended in
  `831439e` (added the "Setup fragility" section), deleted unchanged in `1224b29`
  as "session working notes". Final content == the recovered copy.
- `scripts/bench-query-agent.sh` + `scripts/bench_score.py` — replaced wholesale
  by `platform_testing/query_bench.py` in `aecc835`.

---

## 1. What the benchmark measures

The capstone thesis is **agent reasoning quality** — planning, tool selection,
cross-contract enumeration, aggregation discipline, citation
(`docs/adr/0002`). The query-agent benchmark isolates that by fixing the data
substrate and varying only which pipeline stages are LLM-backed.

### Pipeline under test (`query_agent/agent.py::answer()`)

| Stage | Function | LLM? | Gate |
|---|---|---|---|
| Route | `_plan` → `_guard_plan` | only if `QUERY_PLAN_TOOLS=1` | `QUERY_PLAN_TOOLS` |
| Retrieve | `_gather` | never (SQL over `clm.sqlite3`) | — |
| Reason | `_interpret` | yes | `QUERY_INTERPRET` |
| Compose | `_compose_deterministic` (structural) / `_draft_answer` (clause synthesis) | structural: no · synthesis: yes | `QUERY_DETERMINISTIC_COMPOSE` |
| Check | `_verify` | yes | `QUERY_VERIFY` |

### Substrate

`seed_contracts.py --seed capstone-review-2026 --count 40` — deterministic,
offline, no LLM. Formalised in ADR-0002 (still **Proposed**). ADR-0003
(real-contract stress corpus, also **Proposed**) is the planned depth extension;
not yet built.

Snapshot:

| Lifecycle | Count | | Contract type | Count |
|---|---|---|---|---|
| active | 24 | | distribution-agreement | 7 |
| approved | 15 | | master-services-agreement | 6 |
| in_review | 1 | | services-agreement | 5 |
| **Total** | **40** | | amendment / co-branding / affiliate | 4 each |
| | | | vendor / reseller / license | 3 each |
| | | | nda | 1 |

Known substrate gap: `contract_value`, `effective_date`, `execution_date` are
dropped in the `seed_contracts.py → ingest_contract` mapping, so
`aggregate_contracts` sum/avg and "signed in 2024" filters return empty on this
portfolio. Value/date paths are therefore **not** exercised by this benchmark.

---

## 2. Question set and ground truth

`platform_testing/fixtures/query_bench_questions.jsonl` (committed):

| ID | Question | Class | Ground truth (regex/substring on lowercased answer) |
|---|---|---|---|
| q1_by_status | How many contracts do we have, by lifecycle status? | count-by-status | contains `24` and `15`; matches `\b1\b.*review\|review.*\b1\b\|1 in review` |
| q2_filtered_count | How many active vendor agreements do we have? | filtered-count | matches `(^\|[^0-9])2([^0-9]\|$)`; **reject** `(24\|40)\s*(active\s+)?(vendor\|contract)` |
| q3_list | List all co-branding agreements | list | matches `(^\|[^0-9])4\s+(contract\|co-?branding)` |
| q4_breakdown | Break down contracts by type | breakdown | contains `7` and `distribution`; matches `nda\D*1\b` |
| q5_enumerate | Which contracts mention liability insurance? | enumerate-by-phrase | matches `(^\|[^0-9])15([^0-9]\|$)` |
| q6_clause_synthesis | What payment obligations do we have across all contracts? | clause-synthesis | matches `pay\|invoic\|obligation`; length > 80 |

`_score()` verdicts: **fail** (empty / `unavailable` / `RemoteProtocolError` /
`Traceback` / `TimeoutError`), **wrong** (ground truth not met), **pass**.

### Expected deterministic answers (README / ADR-0002)

| Question | Answer | Computed by |
|---|---|---|
| contracts by lifecycle status | 40 total — active **24**, approved **15**, in_review **1** | `count_contracts` breakdown, no LLM |
| active vendor agreements | **2** | filter + count, no LLM |
| co-branding agreements | **4** (with names) | `list_contracts`, no LLM |
| contracts mentioning liability insurance | **15** | `find_contracts`, no LLM |
| breakdown by type | distribution 7, MSA 6, services 5, amendment/co-branding/affiliate 4, vendor/reseller/license 3, nda 1 | `count_contracts` group_by, no LLM |
| payment obligations across all contracts | prose synthesis | **LLM** (`_draft_answer`) |

---

## 3. Variant table

`platform_testing/query_bench.py` `VARIANTS` (committed). `temperature 0`,
`LLM_PROVIDER=ollama`, API restarted per variant with an explicit env.

| Variant | `PLAN_TOOLS` | `INTERPRET` | `VERIFY` | `DET_COMPOSE` | Intent |
|---|---|---|---|---|---|
| **B0** | 0 | 1 | 1 | 0 | LLM draft for every question (baseline) |
| **B1** | 0 | 0 | 0 | 1 | minimal calls |
| **B2** | 0 | 1 | 1 | 1 | split composer + verify |
| **B3** | 1 | 1 | 1 | 1 | LLM planner on |

(Recovered analysis-doc naming: B0 baseline / B1 min-calls / B2 split-composer /
B3 ceiling. The old doc also noted an optional cloud-API "B3 ceiling" for the
Q6 synthesis class specifically.)

---

## 4. Results

### 4a. Failure localisation (recovered analysis doc — pre-fix, `QUERY_PLAN_TOOLS=0`)

Ground truth: Q1 24/15/1 · Q2 =2 · Q3 =4 · Q4 dist 7/6/5/4/4/4/3/3/3/1 · Q5 =15 · Q6 obligations present.

| Q | Class | Route | Retrieve | Compose `llama3.2:3b` | Compose `gemma:latest` |
|---|---|---|---|---|---|
| 1 | count-by-status | ok | ok | ok | — |
| 2 | filtered count | ok | ok matched=2 | ok | — |
| 3 | list | ok | ok 4 rows | ok | — |
| 4 | breakdown | ok | ok | ok | — |
| 5 | enumerate-by-phrase | ok, query="liability insurance" | ok matched=15 | **echoes question** | **`draft_answer: TimeoutError`** |
| 6 | clause synthesis | ok | ok | **SSE drop (5 LLM calls)** | **`draft_answer: ValidationError`** |

> "Route and Retrieve are solved. 100% of remaining failures are in Compose.
> For Q1–Q5, Compose only reformats a number Retrieve already produced."

Local-model ranking on the test hardware:

| Model | Speed | JSON schema | Structural Q | Synthesis Q |
|---|---|---|---|---|
| llama3.2:3b | ~1–2 min/call | OK | 4/4 | 0/2 |
| gemma:latest (5 GB) | draft > 300 s | ValidationError | — | 0/2 |
| gemma4:latest (9.6 GB) | every call > 120 s | — | 0/4 | 0/2 |

### 4b. Post-fix partial run — `platform_testing/reports/query_bench.tsv` (2026-09-09 02:16, old harness)

The fix (deterministic structural compose, commit `6688a9c`; planner-guard
tweak, commit `bc048e5`) had landed. This TSV is a **partial** run and mixes the
old scored format (B1 rows) with the capture-only format (B2 rows).

**B1 (minimal calls)** — only Q4–Q6 recorded:

| Q | verdict | wall | llm_calls | fail_mode |
|---|---|---|---|---|
| 4 | fail | 126s | 0 | crash |
| 5 | wrong | 2s | 0 | ok |
| 6 | wrong | 3s | 0 | ok |

**B2 (split composer + verify)** — Q1–Q5 recorded, raw grounded answers, scored
here against the committed ground truth:

| Q | wall | llm_calls | answer (verbatim `answer` field) | verdict |
|---|---|---|---|---|
| 1 | 150s | 1 | "40 contracts total: active 24, approved 15, in_review 1." | **pass** |
| 2 | 74s | 1 | "2 contract(s) match lifecycle_status=active, contract_type=vendor-agreement." | **pass** |
| 3 | 41s | 1 | "4 contract(s) match the filter: Adventure Robotics – Margie's Health…; First Line Analytics – Southridge Health…; Coho Financial – Nod Logistics…; Graphic Design Analytics – Wide World Energy Co-Branding Agreement." | **pass** |
| 4 | 53s | 1 | "40 contracts total: distribution-agreement 7, master-services-agreement 6, services-agreement 5, amendment 4, co-branding-agreement 4, affiliate-agreement 4, vendor-agreement 3, reseller-agreement 3, license-agreement 3, nda 1." | **pass** |
| 5 | 84s | 1 | "15 contract(s) mention liability + insurance: Tailspin Energy – Fourth Coffee Financial Amendment; Woodgrove Analytics – Litware Pharma MSA; Wide World Health – Wide World Cloud Distribution Agreement; …" | **pass** |
| 6 | — | — | *(not captured in this run)* | — |

All B2 answers carry `"grounded": true`, `confidence 0.5`, `uncertain: false`,
`citations[].contract_id: "portfolio"`, and **exactly 1 LLM call** (the verify
pass; compose was deterministic).

**B2 structural score: 5 / 5** on Q1–Q5. Q6 (clause synthesis) unmeasured in
this file. B0 and B3 were never run.

---

## 5. Standing conclusions

From the recovered analysis doc's "Decision (pending results)" plus the partial
run:

- **Route + Retrieve are not the problem.** On `QUERY_PLAN_TOOLS=0` the
  deterministic keyword/facet router picks the right tool and filter for all six
  classes, and `_gather` returns the correct matched counts (2, 4, 15).
- **The structural classes (Q1–Q5) are now model-independent.** After splitting
  compose, count/list/breakdown/enumerate answers are templated from tool output
  with 0 LLM calls in compose; a wrong number is a code bug, not model variance.
  The partial B2 run confirms 5/5.
- **The clause-synthesis class (Q6) remains the open risk.** It needs a capable
  model; on `llama3.2:3b` it dropped the SSE connection after 5 LLM calls, and
  `gemma*` variants hit `ValidationError` / `TimeoutError`. No green Q6 result
  exists anywhere.
- **Decision rule recorded (not yet closed):** if B2 reaches 5/6 the small-model
  reviewer tour is viable and the model question narrows to Q6 only; a cloud
  "B3 ceiling" run would bound that class. Neither the full B2 (with Q6) nor B3
  has been run.

### Related untested hypotheses ([`AGENT_HYPOTHESES.md`](../../../docs/hypotheses/agent-hypotheses.md))

- **H2** — conversation history improves multi-turn accuracy ≥20%. Query MCP
  already accepts `history`; benchmark not built.
- **H5** — structured Goal→Constraints→Escalate system prompts cut hallucination
  ≥40%. Hypothesis only; `agents/query_agent/prompts.py` not audited.

---

## 6. To produce a real current report

```bash
# needs the capstone-review-2026 portfolio seeded + Ollama (or configured provider) up
uv run python -m platform_testing.query_bench --model llama3.2:3b --variants B0,B1,B2,B3
# writes platform_testing/reports/query-bench-<UTC>.{json,md}
```

For the Q6 ceiling, run B0/B3 with a capable provider/model via the shared
`LLM_*` env. For depth beyond the tidy synthetic portfolio (paraphrase recall,
multi-currency aggregation, messy party resolution), ADR-0003's stress corpus
must be built first — issues #19–#26 in `docs/implementation-plan.md`.
