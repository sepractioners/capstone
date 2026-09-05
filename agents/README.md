# Agents

The `agents` workspace contains AI-assisted extraction packages. Agents produce validated candidates and communicate with the CLM domain through the MCP server rather than importing domain internals directly.

## Extraction Agent

- [Extraction Agent](extraction_agent/README.md): PDF/JSON/CSV loading, LLM page extraction, merging, structured mapping, and MCP ingestion.
- [Architecture](extraction_agent/docs/architecture.md)
- [Agent Internals](extraction_agent/docs/agent-internals.md)
- [Usage](extraction_agent/docs/usage.md)
- [Kaggle CUAD Testing](extraction_agent/docs/kaggle-cuad.md)

Run agent tests with:

```powershell
python -m pytest .\agents\tests
```
