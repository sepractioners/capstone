# CLM MCP Server

The `mcp` package is the sanctioned integration boundary for external agents. It translates structured candidates into real `contract_lifecycle` application commands and reads persisted contracts and source documents back through MCP tools.

## Tools

- `ingest_contract`: persist an extracted candidate through lifecycle services and invariants.
- `get_contract`: retrieve a stored contract aggregate snapshot.
- `get_source_document`: retrieve the original source bytes and metadata.

See [clm_mcp_server/server.py](clm_mcp_server/server.py) and [clm_mcp_server/ingest_contract_handler.py](clm_mcp_server/ingest_contract_handler.py).

## Tests

```powershell
python -m pytest .\mcp\tests
```
