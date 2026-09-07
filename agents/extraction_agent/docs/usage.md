# Usage

## Installation

From the repository root:

```powershell
uv sync --all-packages
```

This installs every workspace member (`app`, `mcp`, `agents`, `web`, ...) into
the shared `.venv`. The MCP subprocess spawned by `mcp_client.py` needs
`extraction_mcp_server` and `contract_lifecycle` importable; syncing the whole
workspace guarantees that.

## Python API

```python
from extraction_agent.pipeline import run

results = run(
    "path/to/contract.json",
    database_path="path/to/clm.sqlite3",
)

for result in results:
    print(result["contract_id"], result["lifecycle_status"])
```

The asynchronous equivalent is `await extraction_agent.pipeline.arun(...)`, which
also accepts an optional non-authoritative `extraction_directive` dict and an
`async progress_callback(payload)` for streaming safe stage events. The web agent
orchestrator uses `arun` with both; `run` covers the simple synchronous case.
`await extraction_agent.pipeline.acandidates(file_path)` runs `load → extract →
review` and returns the `ContractCandidate` list **without ingesting** - used by
the extraction eval harness.

## Model Configuration

All provider/model/timeout settings are resolved centrally by `agent_llm` from
the repo-root `.env` (see [`.env.example`](../../../.env.example)). Supported providers:

**Anthropic (default)**:
```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=sk-ant-...
```

**Ollama (local)**:
```env
LLM_PROVIDER=ollama
LLM_MODEL=gemma4:latest
OLLAMA_HOST=http://192.168.1.172:11434
```

**OpenRouter (cloud, any model)**:
```env
LLM_PROVIDER=openrouter
LLM_MODEL=meta-llama/llama-3.1-70b-instruct
OPENROUTER_API_KEY=sk-or-...
```

Override just this agent with `EXTRACTION_LLM_PROVIDER` / `EXTRACTION_LLM_MODEL`
when PDF extraction should differ from the shared values. JSON and CSV inputs do
not call the LLM.

## MCP Tools

`mcp_client.py` launches `python -m extraction_mcp_server.server` over stdio. The
server exposes three tools:

- `ingest_contract(candidate)`: persist one extracted candidate and return its lifecycle result.
- `get_contract(contract_id)`: read back the stored contract.
- `get_source_document(contract_id)`: return the original source bytes as base64, with media type and filename.

The client wrappers are `ingest_via_mcp`, `get_contract_via_mcp`, and `get_source_document_via_mcp` in `mcp_client.py`.

The older `clm_mcp_server.server` module remains only for backward compatibility;
new extraction work uses `extraction_mcp_server`, and contract analysis uses the
read-only `query_mcp_server` (see [mcp/README.md](../../../mcp/README.md)).

## Tests

Run the extraction-agent tests from the repository root:

```powershell
uv run pytest agents/tests
```

The structured pipeline tests exercise the real MCP subprocess, which needs the
whole workspace synced (`uv sync --all-packages`).
