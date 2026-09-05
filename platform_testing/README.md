# Platform Testing

YAML-defined deterministic workflow scenarios for the CLM API and domain, with optional Gemma/Ollama evaluation after execution.

## Run a Scenario

```powershell
$env:PYTHONPATH = "app;mcp;agents;web;."
python -m platform_testing.runner platform_testing/scenarios/clause_template_workflow.yaml
```

Use a temporary database by default. Reports are written to `platform_testing/reports/` as JSON and HTML. Set `PLATFORM_TESTING_DATABASE` to use a specific SQLite file.

Gemma evaluation is opt-in. Copy the environment template first:

```powershell
Copy-Item platform_testing\.env.example platform_testing\.env
$env:PLATFORM_TESTING_EVALUATE = "1"
python -m platform_testing.runner platform_testing/scenarios/clause_template_workflow.yaml
```

The evaluator uses `any-llm`, so provider and model settings come from
`platform_testing/.env` through `PLATFORM_LLM_PROVIDER` and
`PLATFORM_LLM_MODEL`. Ollama/Gemma is the local default, but any supported
provider can be selected without changing scenario files. The deterministic
runner executes only actions declared in the YAML `permissions.allowed_actions`
list. The model evaluates the completed trace; it does not select or execute tools.

## Prompt Policy

All evaluator prompts are YAML resources under `platform_testing/prompts/`. Prompts must not be embedded in Python code.
