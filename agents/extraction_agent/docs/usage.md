# Usage

## Installation

From the repository root, install the sibling packages into the same Python environment:

```powershell
python -m pip install -e .\app
python -m pip install -e .\mcp
python -m pip install -e .\agents
```

The MCP subprocess must be able to import both `clm_mcp_server` and `contract_lifecycle`. Installing all three packages avoids import-path problems when the client launches the server in a separate process.

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

The asynchronous equivalent is `await extraction_agent.pipeline.arun(...)`.

## Model Configuration

Set the LLM provider and model for PDF extraction with:

```powershell
$env:EXTRACTION_LLM_PROVIDER = "anthropic"
$env:EXTRACTION_LLM_MODEL = "claude-haiku-4-5-20251001"
```

Any provider supported by `any-llm` works the same way. A local Ollama model, for example:

```powershell
$env:EXTRACTION_LLM_PROVIDER = "ollama"
$env:EXTRACTION_LLM_MODEL = "gemma4:latest"
```

JSON and CSV inputs do not call the LLM.

## MCP Tools

The server exposes three tools:

- `ingest_contract(candidate)`: persist one extracted candidate and return its lifecycle result.
- `get_contract(contract_id)`: read back the stored contract.
- `get_source_document(contract_id)`: return the original source bytes as base64, with media type and filename.

The client wrappers are `ingest_via_mcp`, `get_contract_via_mcp`, and `get_source_document_via_mcp` in `mcp_client.py`.

## Tests

Run the extraction-agent tests from the repository root:

```powershell
python -m pytest .\agents\tests
```

The structured pipeline tests exercise the real MCP subprocess and therefore require the `app`, `mcp`, and `agents` packages to be installed in the active environment.
