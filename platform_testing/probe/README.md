# Subsystem probes

Direct-call validators for one agent at a time — no API, no orchestrator. A
probe drives the subsystem against a seeded database, records the full step
trace (system prompt + exact context in, raw + parsed model output out, timing),
and scores the deterministic parts against committed ground truth.

Contrast with `platform_testing/query_bench.py` / `extraction_bench.py`, which
exercise the whole stack through the running API.

## Query agent

```powershell
uv run python -m platform_testing.probe.query_agent_probe --org capstone --all
uv run python -m platform_testing.probe.query_agent_probe --org capstone --question q14_portfolio_risk_summary
```

- `--org` is **required** — every contract load, filter, and retrieval is scoped
  to that organization; the probe never runs unscoped.
- `--plan-tools 0|1` overrides `QUERY_PLAN_TOOLS` for the run; `--model` overrides
  `LLM_MODEL`. The resolved config is recorded in the report.
- Reads `platform_testing/fixtures/query_bench_questions.jsonl`. Each question may
  carry `expect_plan` (a list of `{tool, filters?}`) — the probe diffs it against
  the **resolved plan** (structured output), which is a deterministic routing
  score even though a model produced the plan.
- Writes `platform_testing/reports/query-probe-<UTC stamp>.{json,md}` (gitignored;
  commit a baseline explicitly).

The Markdown report shows, per question: the resolved plan, every deterministic
tool result, and every LLM call with its exact system prompt, input context, and
raw + parsed output.
