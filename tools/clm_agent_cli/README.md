# CLM Agent CLI

The CLI is an authenticated HTTP/SSE client of the web agent orchestrator. It does not call LLM providers, databases, or MCP tools directly, so **the API must be running** (`scripts/run-all.ps1` / `scripts/run-all.sh`) before any command.

## Authentication

Every command needs a bearer token. Three ways to provide one:

1. **Wrapper (easiest)** — `scripts/agent.ps1` / `scripts/agent.sh` log in for you
   using the built-in review account (`admin@capstone.local` /
   `CapstoneAdmin!2026`), export `CLM_AGENT_TOKEN` + `CLM_API_URL`, and run
   `clm-agent`. Pass `--email` / `--password` (or `-Email` / `-Password`) to use
   a different account.
2. **Env var** — obtain a token from the API and export it:
   ```powershell
   $body = @{ grant_type = "password"; username = "admin@capstone.local"; password = "CapstoneAdmin!2026" }
   $env:CLM_AGENT_TOKEN = (Invoke-RestMethod -Uri https://localhost:8443/auth/token -Method Post -Body $body -SkipCertificateCheck).access_token
   $env:CLM_API_URL = "https://localhost:8443"
   ```
3. **Prompt** — with no `--token` and no `CLM_AGENT_TOKEN`, `clm-agent` prompts
   for the token interactively.

The credentials above are a local review account created by
`run-all --bootstrap`; they are not a production secret.

## Usage

```powershell
uv sync --all-packages
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