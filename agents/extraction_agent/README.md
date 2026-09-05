# Capstone Week 1

The extraction agent turns contract source files into validated contract candidates and submits them to the Contract Lifecycle Management domain through the MCP server.

## Supported Inputs

- **PDF**: page-by-page LLM extraction, followed by merging and deduplication.
- **JSON**: one candidate or one candidate per list item.
- **CSV**: one candidate per row, including numbered party columns such as `party_1_name` and `party_1_role`.

## Documentation

- [Architecture](docs/architecture.md): end-to-end flow across the extraction agent, MCP client, MCP server, application services, domain, and SQLite storage.
- [Agent Internals](docs/agent-internals.md): LangGraph state, PDF and structured-input branches, prompt execution, merging, mapping, and MCP handoff.
- [Kaggle CUAD Scenario](docs/kaggle-cuad.md): dataset source, download steps, subset selection, and complete PDF pipeline test.
- [Usage](docs/usage.md): installation, Python API, model configuration, MCP tools, and tests.
- [Troubleshooting and Lessons Learned](docs/troubleshooting.md): async LLM behavior, local-model extraction quality, prompt tuning, and known limitations.

## Quick Start

Install the sibling packages:

```powershell
python -m pip install -e .\app
python -m pip install -e .\mcp
python -m pip install -e .\agents
```

For the complete Kaggle-backed scenario, follow [Kaggle CUAD Scenario](docs/kaggle-cuad.md). For a direct API example, see [Usage](docs/usage.md).
