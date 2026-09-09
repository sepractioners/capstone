# Query Agent — Small-Model Analysis & Benchmark

Status: **in progress**. Tracks why the query agent fails on small local models,
where the failures localise in the pipeline, the design change proposed to fix
them, and the benchmark that measures the trade-offs.

## Pipeline (our code)

`query_agent/agent.py::answer()`:

| Stage | Function | Prompt | LLM? | Gate |
|---|---|---|---|---|
| Route | `_plan` → `_guard_plan` | `_PLAN_PROMPT` | only if `QUERY_PLAN_TOOLS=1` | `QUERY_PLAN_TOOLS` |
| Retrieve | `_gather` | — | never (SQL over `clm.sqlite3`) | — |
| Reason | `_interpret` | `_INTERPRET_PROMPT` | yes | `QUERY_INTERPRET` |
| Compose | `_draft_answer` | `contract_query.yaml` | **yes, always** | — |
| Check | `_verify` | `_VERIFY_PROMPT` | yes | `QUERY_VERIFY` |

## Fixes already landed (this branch)

- `_slug_match` — `_infer_where` matched `vendor-agreement` but not `co-branding-agreement`
  (facet `.replace("-"," ")` vs the question keeping hyphens). Route filter bug.
- `_clause_query` — `find_contracts` searched the first bare regex keyword
  (`"liabilit"`) instead of the phrase the question names (`"liability insurance"`).
- `_guard_plan` filter-merge — the deterministic filter parse is now forced onto
  any planner-emitted call that left a filter empty. Planner picks tools; the
  parse owns scope.
- `contract_query.yaml` — replaced "for 'how many active?' read straight from
  `by_lifecycle_status`" with a precedence rule: filter set ⇒ answer is `matched`;
  `by_*` breakdowns ignore the filter. Rewrote `example_1` / added `example_1b`
  so the model can't lift the wrong number from the example.
- `_VERIFY_PROMPT` — rejects an answer that reads a `by_*` value while a filter is set.
- `_trim_lists_for_draft` — caps the draft payload to 15 summary rows (compensating;
  under review).
- `server.py` MCP instructions — facet-value rule + `matched` vs `by_*` precedence;
  fixed `contract_type="vendor"` → `"vendor-agreement"`.

## Failure localisation

Ground truth: Q1 24/15/1 · Q2 =2 · Q3 =4 · Q4 dist 7/6/5/4/4/4/3/3/3/1 · Q5 =15 · Q6 obligations present.

| Q | Class | Route | Retrieve | Compose (llama3.2:3b) | Compose (gemma:latest) |
|---|---|---|---|---|---|
| 1 | count-by-status | ✅ | ✅ | ✅ | — |
| 2 | filtered count | ✅ | ✅ matched=2 | ✅ | — |
| 3 | list | ✅ | ✅ 4 rows | ✅ | — |
| 4 | breakdown | ✅ | ✅ | ✅ | — |
| 5 | enumerate-by-phrase | ✅ query="liability insurance" | ✅ matched=15 | ❌ echoes question | ❌ `draft_answer: TimeoutError` |
| 6 | clause synthesis | ✅ | ✅ | ❌ SSE drop (5 LLM calls) | ❌ `draft_answer: ValidationError` |

**Route and Retrieve are solved. 100% of remaining failures are in Compose.**
For Q1–Q5, Compose only reformats a number Retrieve already produced.

Local model ranking on this hardware:

| Model | Speed | JSON schema | Structural Q | Synthesis Q |
|---|---|---|---|---|
| llama3.2:3b | ~1–2 min/call | OK | 4/4 | 0/2 |
| gemma:latest (5 GB) | draft > 300 s | ValidationError | — | 0/2 |
| gemma4:latest (9.6 GB) | every call > 120 s | — | 0/4 | 0/2 |

## Setup fragility (blocked reviewers on a fresh clone)

`clm.sqlite3`, `synthetic_data_loader/rag_knowledge.sqlite3`, `.env`, `.certs`
are all gitignored — a fresh clone has none of them; setup must build all.

On master, setup hard-aborts when Ollama is not running: `seed_database.py`
seeds tenant/admin, then `seed_rag_database` calls `embed()` on every record →
connection refused → non-zero exit → `exit 1` before the portfolio is seeded.
`build_rag_index` (a later step) aborts the same way.

Fix (this branch): setup runs `seed_database.py --skip-cuad --skip-faiss
--skip-rag` (no embedding calls in the tenant step) and treats
`build_rag_index` as best-effort (warn + continue). Tenant + admin + the 40-
contract validation portfolio now land offline with no Ollama. The RAG index is
extraction-only and the query agent never reads it, so it does not gate the
reviewer tour.

## Design change proposed

Compose is a pure function of Retrieve's output for every class except clause
synthesis. Split `_draft_answer`:

```
_gather → snippets present?
            ├── no  → _compose_deterministic()   (template QueryAnswer, 0 LLM calls)
            └── yes → LLM draft (contract_query.yaml, as today)
```

Route / Retrieve / Reason / Check unchanged. The LLM touches Compose only when
the question needs synthesis across unstructured clause text.

Expected: Q1–Q5 become model-independent and always correct; only Q6-class routes
to the LLM.

## Benchmark

Fixed: question set (Q1–Q6), ground truth, code fixes above, `QUERY_PLAN_TOOLS=0`.
Vary which stages are LLM-backed. Record per run: `verdict` (pass/partial/fail),
`wall_s`, `llm_calls`, `fail_mode`.

| Variant | Reason | Compose | Check |
|---|---|---|---|
| B0 baseline | LLM | LLM | LLM |
| B1 min-calls | off | LLM | off |
| B2 split-composer | LLM | det / LLM | LLM |
| B3 ceiling (optional, needs API key) | cloud | cloud | cloud |

Harness: `scripts/bench-query-agent.sh` → `platform_testing/reports/query_bench.tsv`.

### Results

_(filled by the harness)_

| variant | Q | verdict | wall_s | llm_calls | fail_mode |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## Decision (pending results)

- If B2 reaches 5/6 → small-model viability solved for the reviewer tour; the
  model question narrows to the Q6 synthesis class only.
- B3 sets the ceiling for that class.
