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
ground-truth JSONL, writing a JSON + Markdown report to
`platform_testing/reports/`.

```powershell
uv run python -m platform_testing.extraction_eval --limit 8
```

Ground truth lives in `platform_testing/fixtures/cuad_ground_truth.jsonl` - one
record per contract with `filename`, `title`, `parties`, `contract_type`,
`effective_date`, `expiration_date`, `clause_count`. A `null` field is not
scored, so the file can be filled in incrementally. The seed entries carry only
the filename-derived `contract_type` and issuer party; extend them by reading
the PDFs. Scoring: token-F1 for `title`, normalized-overlap F1 for `parties`,
exact match for `contract_type` and dates, tolerance ratio for `clause_count`.

## Prompt Policy

All evaluator prompts are YAML resources under `platform_testing/prompts/`. Prompts must not be embedded in Python code.

## Chrome MCP Browser Validation

An external Chrome MCP validation agent complements deterministic scenarios by
using the running portal like a user. It validates login, contract workflows,
the organization-wide Agent Workspace, attachment extraction, and SSE progress
rendering. It must use the portal's authenticated UI and must not read SQLite,
call MCP servers directly, or inspect hidden model reasoning. Browser evidence
is separate from the ignored generated reports in `platform_testing/reports/`.
