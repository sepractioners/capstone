# CLM Agent CLI

The CLI is an authenticated HTTP/SSE client of the web agent orchestrator. It does not call LLM providers, databases, or MCP tools directly.

```powershell
uv sync --all-packages
$env:CLM_AGENT_TOKEN = "<access-token>"
uv run clm-agent ask "Which contracts expire this quarter?"
uv run clm-agent extract .\vendor.pdf --instruction "Extract this as a vendor agreement"
uv run clm-agent task "extract this and tell me how it compares to our other vendor contracts" --file .\vendor.pdf
uv run clm-agent watch run_123
uv run clm-agent chat
```

`task` posts to the Auto endpoint; the planner decides the extract/analyze
steps and progress lines show `Plan:` and `Step n/total:`.

Use `--json` with `ask`, `extract`, `task`, or `watch` for machine-readable
terminal output. Progress remains on standard error.