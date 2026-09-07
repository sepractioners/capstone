# Synthetic Data Loader

Downloads selected CUAD contract categories from Kaggle with `kagglehub` and runs them through the real extraction, MCP, application-service, and SQLite path.

See [Kaggle CUAD Scenario](../agents/extraction_agent/docs/kaggle-cuad.md) for setup and commands.

## Seed a portfolio without a model

`seed_contracts.py` generates valid, varied `ContractCandidate` objects (no LLM)
and runs them through the same `ingest_contract` handler, then binds each to a
local organization so it shows in the portal. All text is ASCII. Idempotent per
`--seed` value.

```powershell
uv run python sythetic_data_loader\seed_contracts.py --count 120
uv run python sythetic_data_loader\seed_contracts.py --count 120 --reset   # replace an earlier batch
```

Produces a realistic lifecycle spread (most `active`, some `approved`, a few
`in_review`) across ~10 contract types with parties, clauses, obligations,
signatures, key dates, and commercial terms.

To run complete-contract extraction with resumable JSONL checkpoints and
Markdown logging:

```powershell
uv run python .\sythetic_data_loader\download_cuad_subset.py --all --limit 198
uv run python .\sythetic_data_loader\run_contract_batch.py --limit 198
```

The current CUAD snapshot contains 198 unique PDFs. The runner logs every
contract result in `agents/extraction_agent/docs/improvement-test-log.md`.
