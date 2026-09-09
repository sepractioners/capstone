# Query-Agent Benchmark — Questions, Expected Answers, Variants

Single source for the query-agent benchmark question set: the 6 committed
questions plus 8 draft clause-synthesis additions, each tagged, with expected
answers, tool path, and last-recorded results. Structured blocks are TOML so the
file doubles as a data source; prose headings keep it readable as Markdown.

- Harness: [`platform_testing/query_bench.py`](../platform_testing/query_bench.py)
- Committed fixture: [`platform_testing/fixtures/query_bench_questions.jsonl`](../platform_testing/fixtures/query_bench_questions.jsonl)
- Analysis: [`docs/query-agent-small-model-analysis.md`](query-agent-small-model-analysis.md)
- Consolidated report: [`docs/query-agent-benchmark.md`](query-agent-benchmark.md)
- Scope decision: [`docs/adr/0002-query-agent-evaluation-substrate.md`](adr/0002-query-agent-evaluation-substrate.md)

## Tag vocabulary

| Tag | Meaning |
|---|---|
| `status:committed` | in the fixture today |
| `status:draft` | proposed here, not yet in the fixture |
| `compose:deterministic` | answer templated from tool output, 0 LLM calls in compose |
| `compose:llm` | answer needs an LLM draft (`_draft_answer`) |
| `class:*` | question class the harness records |
| `tool:*` | primary MCP/portfolio tool exercised |
| `verify:pinned` | expected answer verified against the seeded portfolio |
| `verify:needs-run` | expected answer must be computed against a live seed before it is ground truth |
| `perf:fast` / `perf:slow` | observed wall time (< 10s vs tens of seconds to minutes on `llama3.2:3b`) |
| `risk:hallucination` | model may invent values/citations; verify pass must check every cited clause |
| `hybrid:date-filter` | combines a deterministic relative-date filter with synthesis |

---

## Substrate

```toml
[substrate]
seed        = "capstone-review-2026"
count       = 40
generator   = "synthetic_data_loader/seed_contracts.py"   # deterministic, offline, no LLM
lifecycle_status = { active = 24, approved = 15, in_review = 1 }
contract_type = { "distribution-agreement" = 7, "master-services-agreement" = 6, "services-agreement" = 5, "amendment" = 4, "co-branding-agreement" = 4, "affiliate-agreement" = 4, "vendor-agreement" = 3, "reseller-agreement" = 3, "license-agreement" = 3, "nda" = 1 }

[substrate.persisted]
clauses      = ["Payment Terms", "Governing Law", "Term and Termination", "Insurance", "Indemnification", "Limitation of Liability"]  # first 3 on every contract; rest rotate
obligations  = "1-3 per contract, each with a description and a due date"
expiration_date = true

[substrate.not_persisted]   # dropped in seed_contracts.py -> ingest_contract mapping
fields = ["contract_value", "effective_date", "execution_date"]
consequence = "aggregate_contracts sum/avg and effective-date filters return empty; no benchmark question may depend on them"
```

## Config and variants

```toml
[config]
temperature = 0
provider    = "ollama"          # any any-llm provider
model       = "llama3.2:3b"     # default; clause-synthesis needs a capable model
api_restarted_per_variant = true
scoring     = "query_bench.py::_score  ->  fail | wrong | pass"
# fail  = empty OR contains: unavailable / remoteprotocolerror / traceback / timeouterror
# wrong = ground truth not met
# pass  = every expect_* satisfied and no reject_regex hit ; match target = answer, lower-cased

[variant.B0]
env    = { QUERY_PLAN_TOOLS = 0, QUERY_INTERPRET = 1, QUERY_VERIFY = 1, QUERY_DETERMINISTIC_COMPOSE = 0 }
intent = "LLM draft for every question (baseline)"
status = "never run"

[variant.B1]
env    = { QUERY_PLAN_TOOLS = 0, QUERY_INTERPRET = 0, QUERY_VERIFY = 0, QUERY_DETERMINISTIC_COMPOSE = 1 }
intent = "minimal calls"
status = "partial: q4 fail(crash), q5 wrong, q6 wrong; q1-q3 not recorded"

[variant.B2]
env    = { QUERY_PLAN_TOOLS = 0, QUERY_INTERPRET = 1, QUERY_VERIFY = 1, QUERY_DETERMINISTIC_COMPOSE = 1 }
intent = "split composer + verify"
status = "partial: q1-q5 all PASS (1 llm call each, 41-150s); q6 not recorded"

[variant.B3]
env    = { QUERY_PLAN_TOOLS = 1, QUERY_INTERPRET = 1, QUERY_VERIFY = 1, QUERY_DETERMINISTIC_COMPOSE = 1 }
intent = "LLM planner on"
status = "never run"
```

---

## Committed questions (q1–q6)

```toml
[[question]]
id       = "q1_by_status"
n        = 1
question = "How many contracts do we have, by lifecycle status?"
tags     = ["status:committed", "class:count-by-status", "compose:deterministic", "tool:count_contracts", "verify:pinned", "perf:slow"]
expect_all   = ["24", "15"]
expect_regex = '\b1\b.*review|review.*\b1\b|1 in review'
reject_regex = ""
tool_path    = "count_contracts(group_by=lifecycle_status)"
llm_calls    = 0
expected_answer = "40 total - active 24, approved 15, in_review 1"
last_result  = { variant = "B2", verdict = "pass", wall_s = 150, llm_calls = 1, answer = "40 contracts total: active 24, approved 15, in_review 1." }

[[question]]
id       = "q2_filtered_count"
n        = 2
question = "How many active vendor agreements do we have?"
tags     = ["status:committed", "class:filtered-count", "compose:deterministic", "tool:count_contracts", "verify:pinned", "perf:slow"]
expect_all   = []
expect_regex = '(^|[^0-9])2([^0-9]|$)'
reject_regex = '(24|40)\s*(active\s+)?(vendor|contract)'   # guard: must not read the by_* breakdown
tool_path    = "count_contracts(where lifecycle_status=active, contract_type=vendor-agreement)"
llm_calls    = 0
expected_answer = "2"
last_result  = { variant = "B2", verdict = "pass", wall_s = 74, llm_calls = 1, answer = "2 contract(s) match lifecycle_status=active, contract_type=vendor-agreement." }

[[question]]
id       = "q3_list"
n        = 3
question = "List all co-branding agreements"
tags     = ["status:committed", "class:list", "compose:deterministic", "tool:list_contracts", "verify:pinned", "perf:slow"]
expect_all   = []
expect_regex = '(^|[^0-9])4\s+(contract|co-?branding)'
reject_regex = ""
tool_path    = "list_contracts(where contract_type=co-branding-agreement)"
llm_calls    = 0
expected_answer = "4 contracts, with names"
last_result  = { variant = "B2", verdict = "pass", wall_s = 41, llm_calls = 1, answer = "4 contract(s) match the filter: Adventure Robotics - Margie's Health Co-Branding Agreement; First Line Analytics - Southridge Health Co-Branding Agreement; Coho Financial - Nod Logistics Co-Branding Agreement; Graphic Design Analytics - Wide World Energy Co-Branding Agreement." }

[[question]]
id       = "q4_breakdown"
n        = 4
question = "Break down contracts by type"
tags     = ["status:committed", "class:breakdown", "compose:deterministic", "tool:count_contracts", "verify:pinned", "perf:slow"]
expect_all   = ["7", "distribution"]
expect_regex = 'nda\D*1\b'
reject_regex = ""
tool_path    = "count_contracts(group_by=contract_type)"
llm_calls    = 0
expected_answer = "distribution 7, MSA 6, services 5, amendment/co-branding/affiliate 4, vendor/reseller/license 3, nda 1"
last_result  = { variant = "B2", verdict = "pass", wall_s = 53, llm_calls = 1, answer = "40 contracts total: distribution-agreement 7, master-services-agreement 6, services-agreement 5, amendment 4, co-branding-agreement 4, affiliate-agreement 4, vendor-agreement 3, reseller-agreement 3, license-agreement 3, nda 1." }

[[question]]
id       = "q5_enumerate"
n        = 5
question = "Which contracts mention liability insurance?"
tags     = ["status:committed", "class:enumerate-by-phrase", "compose:deterministic", "tool:find_contracts", "verify:pinned", "perf:slow"]
expect_all   = []
expect_regex = '(^|[^0-9])15([^0-9]|$)'
reject_regex = ""
tool_path    = "find_contracts(phrase=\"liability insurance\")   # complete enumeration"
llm_calls    = 0
expected_answer = "15 contracts"
last_result  = { variant = "B2", verdict = "pass", wall_s = 84, llm_calls = 1, answer = "15 contract(s) mention liability + insurance: Tailspin Energy - Fourth Coffee Financial Amendment; Woodgrove Analytics - Litware Pharma Master Services Agreement; Wide World Health - Wide World Cloud Distribution Agreement; ..." }

[[question]]
id       = "q6_clause_synthesis"
n        = 6
question = "What payment obligations do we have across all contracts?"
tags     = ["status:committed", "class:clause-synthesis", "compose:llm", "tool:find_contracts", "tool:search_clauses", "verify:pinned", "perf:slow", "risk:hallucination"]
expect_all   = []
expect_regex = 'pay|invoic|obligation'
reject_regex = ""
min_len      = 80
tool_path    = "find_contracts + search_clauses -> interpret -> draft_answer"
llm_calls    = ">=1"
expected_answer = "prose synthesis of payment/invoice obligation terms"
last_result  = { variant = "B1", verdict = "wrong", note = "no green q6 result on record; llama3.2:3b dropped SSE after 5 LLM calls; gemma* hit ValidationError/TimeoutError" }
```

---

## Draft clause-synthesis questions (q7–q14)

All `compose:llm`, `class:clause-synthesis`, `status:draft`, `verify:needs-run`.
Expected answers must be pinned against a live `--seed capstone-review-2026
--count 40` run before use as ground truth. Route/gather to a capable model
(B0 or B3); not for the small-model reviewer tour.

```toml
[[question]]
id       = "q7_governing_law"
question = "What governing law and jurisdiction provisions apply across our contracts?"
tags     = ["status:draft", "class:clause-synthesis", "compose:llm", "tool:find_contracts", "tool:search_clauses", "verify:needs-run", "perf:slow", "risk:hallucination"]
expect_regex = 'govern|jurisdiction|law of|courts of'
min_len      = 120
tool_path    = "find_contracts(\"governing law\") + search_clauses -> interpret -> draft"
expected_answer = "the jurisdictions represented and how many contracts fall under each"
needs_verification = ["jurisdiction list", "per-jurisdiction counts"]

[[question]]
id       = "q8_termination_rights"
question = "How can we terminate our contracts and what notice is required?"
tags     = ["status:draft", "class:clause-synthesis", "compose:llm", "tool:find_contracts", "tool:search_clauses", "verify:needs-run", "perf:slow", "risk:hallucination"]
expect_regex = 'terminat|notice|cure|breach'
expect_all   = ["day"]
min_len      = 150
tool_path    = "find_contracts(\"termination\") + search_clauses -> interpret -> draft"
expected_answer = "termination-for-convenience vs for-cause rights and the notice windows (e.g. 30/60/90 days)"
needs_verification = ["notice-period values", "which contracts allow termination for convenience"]

[[question]]
id       = "q9_indemnification"
question = "What indemnification obligations have we taken on across the portfolio?"
tags     = ["status:draft", "class:clause-synthesis", "compose:llm", "tool:find_contracts", "tool:search_clauses", "verify:needs-run", "perf:slow", "risk:hallucination"]
expect_regex = 'indemnif|hold harmless|defend'
min_len      = 120
tool_path    = "find_contracts(\"indemnification\") + search_clauses -> interpret -> draft"
expected_answer = "which contracts carry an indemnity, the triggering events, mutual vs one-way"
needs_verification = ["count of contracts with an indemnification clause", "contract names"]

[[question]]
id       = "q10_liability_caps"
question = "How is our liability limited across our contracts?"
tags     = ["status:draft", "class:clause-synthesis", "compose:llm", "tool:find_contracts", "tool:search_clauses", "verify:needs-run", "perf:slow", "risk:hallucination"]
expect_regex = 'liabilit|limitation|cap|consequential|aggregate'
min_len      = 120
tool_path    = "find_contracts(\"limitation of liability\") + search_clauses -> interpret -> draft"
expected_answer = "liability caps, consequential-damages exclusions, and carve-outs"
needs_verification = ["count with a limitation-of-liability clause", "cap formulation wording"]

[[question]]
id       = "q11_insurance_requirements"
question = "What insurance are we required to carry, and under which contracts?"
tags     = ["status:draft", "class:clause-synthesis", "compose:llm", "tool:find_contracts", "tool:search_clauses", "verify:needs-run", "perf:slow", "risk:hallucination"]
expect_regex = 'insurance|coverage|policy|liability'
min_len      = 120
tool_path    = "find_contracts(\"insurance\") + search_clauses -> interpret -> draft"
expected_answer = "insurance types/limits required, and the 15 contracts that mention liability insurance (cross-check q5)"
needs_verification = ["coverage amounts", "cross-check the 15-contract count from q5"]

[[question]]
id       = "q12_payment_terms_variation"
question = "Summarize how payment terms vary across our contracts - net terms, late fees, and invoicing cadence."
tags     = ["status:draft", "class:clause-synthesis", "compose:llm", "tool:find_contracts", "tool:search_clauses", "verify:needs-run", "perf:slow", "risk:hallucination"]
expect_regex = 'net\s?\d|invoic|payment|late|interest'
min_len      = 150
tool_path    = "find_contracts(\"payment terms\") + search_clauses -> interpret -> draft"
expected_answer = "distinct net-payment windows (e.g. Net 30/45/60), late-fee/interest provisions, invoicing frequency"
needs_verification = ["distinct net-term values", "late-fee percentages"]

[[question]]
id       = "q13_upcoming_obligations"
question = "What obligations are coming due in the next 90 days, and what do they require of us?"
tags     = ["status:draft", "class:clause-synthesis", "compose:llm", "hybrid:date-filter", "tool:list_contracts", "tool:search_clauses", "verify:needs-run", "perf:slow", "risk:hallucination"]
expect_regex = 'due|deadline|within|obligation|by '
min_len      = 150
tool_path    = "list_contracts(obligations / expiring_within_days) + search_clauses -> interpret -> draft"
expected_answer = "enumerated near-term obligation descriptions with their due dates"
needs_verification = ["which obligation due dates fall inside 90 days of the fixed seed clock"]
note = "blends a deterministic relative-date filter with synthesis; check the model does not invent due dates"

[[question]]
id       = "q14_portfolio_risk_summary"
question = "What are the most significant contractual risks across our portfolio?"
tags     = ["status:draft", "class:clause-synthesis", "compose:llm", "tool:find_contracts", "tool:search_clauses", "verify:needs-run", "perf:slow", "risk:hallucination"]
expect_regex = 'risk|liabilit|indemnif|terminat|exposure|auto[- ]?renew'
min_len      = 200
tool_path    = "find_contracts(multi-phrase) + search_clauses -> interpret -> draft"
expected_answer = "prioritized synthesis over indemnity exposure, high/uncapped liability, near-term expirations, auto-renewal traps"
needs_verification = ["every risk cited is backed by a real clause citation (no fabrication)"]
```

---

## Results to date

```toml
# platform_testing/reports/query_bench.tsv - gitignored, partial run 2026-09-09 02:16
# (old scripts/bench-query-agent.sh harness; B2 rows re-scored here against the committed ground truth)

[[result]]
variant = "B2"; scored = "5/5 on q1-q5"; llm_calls_each = 1; wall_s = [150, 74, 41, 53, 84]
grounded = true; confidence = 0.5; uncertain = false; citation_contract_id = "portfolio"
q6 = "not captured"

[[result]]
variant = "B1"; recorded = "q4-q6 only"
q4 = { verdict = "fail", wall_s = 126, fail_mode = "crash" }
q5 = { verdict = "wrong", wall_s = 2 }
q6 = { verdict = "wrong", wall_s = 3 }

[[result]]
variant = "B0"; status = "never run"
[[result]]
variant = "B3"; status = "never run"
```

### Standing conclusions

- Route + Retrieve are solved for all 6 committed classes on `QUERY_PLAN_TOOLS=0`.
- q1–q5 are model-independent after the deterministic-compose split; B2 confirms 5/5.
- q6 (and the q7–q14 drafts) are the open risk: they need a capable model and
  have no green result on record.
- Decision rule (pending a full run): B2 at >= 5/6 makes the small-model reviewer
  tour viable and narrows the model question to the synthesis class; a cloud B0/B3
  run bounds that class.

## To run

```bash
# needs the capstone-review-2026 portfolio seeded + a running provider
uv run python -m platform_testing.query_bench --model llama3.2:3b --variants B0,B1,B2,B3
# writes platform_testing/reports/query-bench-<UTC>.{json,md}
```

For q7–q14, add them to `platform_testing/fixtures/query_bench_questions.jsonl`
(one JSON object per line: `id`, `question`, `class`, `expect_regex`, optional
`expect_all` / `reject_regex` / `min_len`), pin the expected answers against the
seed, then run B0/B3 with a capable model.
