# Platform Testing

YAML-defined deterministic workflow scenarios for the CLM API and domain, with optional Gemma/Ollama evaluation after execution.

## Run a Scenario

```powershell
uv run python -m platform_testing.runner platform_testing/scenarios/clause_template_workflow.yaml
```

Use a temporary database by default. Reports are written to `platform_testing/reports/` as JSON and HTML. Set `PLATFORM_TESTING_DATABASE` to use a specific SQLite file.

Gemma evaluation is opt-in:

```powershell
$env:PLATFORM_TESTING_EVALUATE = "1"
uv run python -m platform_testing.runner platform_testing/scenarios/clause_template_workflow.yaml
```

The evaluator uses `any-llm`. Provider/model settings are resolved centrally by
`agent_llm` from the repo-root `.env` (see [`.env.example`](../.env.example)),
using the shared `LLM_*` values unless `PLATFORM_LLM_PROVIDER` /
`PLATFORM_LLM_MODEL` override them. Ollama/Gemma is the local default, but any
supported provider can be selected without changing scenario files. The
deterministic
runner executes only actions declared in the YAML `permissions.allowed_actions`
list. The model evaluates the completed trace; it does not select or execute tools.

## Extraction Accuracy Eval

`extraction_eval.py` runs the real extraction pipeline (`load → extract →
review`, no ingest) over a PDF directory and scores each field against a
ground-truth JSONL, writing a JSON + Markdown report to `reports/`.

```powershell
uv run python -m platform_testing.extraction_eval --limit 8
```

- **Fixture:** `fixtures/cuad_pdf/` — 8 CUAD contracts (CC BY 4.0, see its
  `ATTRIBUTION.md`), committed so the eval runs without the opt-in CUAD
  download. Point `--data-dir synthetic_data_loader/data/cuad_subset` at the
  larger local set once downloaded.
- **Ground truth:** `fixtures/cuad_ground_truth.jsonl` — one record per
  contract (`filename`, `title`, `parties`, `contract_type`, `effective_date`,
  `expiration_date`, `clause_count`). `null` = not scored. Scored today:
  `title` (token-F1), `parties` (overlap-F1), `contract_type` (exact),
  `effective_date` (exact). `expiration_date` / `clause_count` are `null` —
  fill them by reading the PDFs to widen coverage.
- The `extraction` role default is `anthropic/claude-haiku-4-5`. A small local
  model (`llama3.2:3b` on CPU) takes minutes per page and often exceeds the
  call timeout — use `--max-pages` and a capable model.

## Benchmarks

Deterministic, committed harnesses (config → report; only the model's output
varies). Reports land in `reports/` (gitignored).

```powershell
# Extraction: RAG-on vs RAG-off, one report
uv run python -m platform_testing.extraction_bench --model llama3.2:3b --rag both --limit 8 --max-pages 3

# Query-agent pipeline variants (needs the seeded validation portfolio + a running provider)
uv run python -m platform_testing.query_bench --model llama3.2:3b --variants B0,B2
```

- `extraction_bench.py` runs `extraction_eval` once per RAG setting in an
  isolated subprocess (no import-time env leakage) and merges the reports.
- `query_bench.py` variant table (`B0` LLM draft always · `B1` minimal calls ·
  `B2` split composer + verify · `B3` LLM planner on) and question set
  (`fixtures/query_bench_questions.jsonl`) are committed; it restarts the API
  per variant with an explicit env and scores against the fixture's regex
  ground truth.

## Prompt Policy

All evaluator prompts are YAML resources under `platform_testing/prompts/`. Prompts must not be embedded in Python code.

## Chrome MCP Browser Validation

An external Chrome MCP validation agent complements deterministic scenarios by
using the running portal like a user. It validates login, contract workflows,
the organization-wide Agent Workspace, attachment extraction, and SSE progress
rendering. It must use the portal's authenticated UI and must not read SQLite,
call MCP servers directly, or inspect hidden model reasoning. Browser evidence
is separate from the ignored generated reports in `platform_testing/reports/`.
