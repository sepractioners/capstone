# Kaggle CUAD End-to-End Scenario

The full scenario is tested with PDFs from the Kaggle-hosted CUAD (Contract Understanding Atticus Dataset). The synthetic-data loader downloads the dataset with `kagglehub`, selects a small category subset, and copies the PDFs into the directory consumed by the extraction pipeline.

Dataset source:

`konradb/atticus-open-contract-dataset-aok-beta`

The download script reads these categories by default:

- `Affiliate_Agreements`
- `Co_Branding`

The script copies the selected files from the dataset's `CUAD_v1/full_contract_pdf/Part_I/` tree into `synthetic_data_loader/data/cuad_subset/`. The dataset itself is downloaded and cached by `kagglehub`; only the selected PDFs are copied into this repository's working data directory.

## Download the Test PDFs

`uv sync --all-packages` already installs `kagglehub` (via the
`synthetic-data-loader` workspace member). Download the default categories:

```powershell
uv run python .\synthetic_data_loader\download_cuad_subset.py
```

To download different CUAD categories, pass their directory names as arguments:

```powershell
uv run python .\synthetic_data_loader\download_cuad_subset.py Affiliate_Agreements Co_Branding
```

To copy every available CUAD PDF category locally:

```powershell
uv run python .\synthetic_data_loader\download_cuad_subset.py --all
```

After downloading the full local set, build the reusable vector index with
the Ollama `nomic-embed-text:latest` model:

```powershell
uv run python -m extraction_agent.build_rag_index
```

Enable vector retrieval for extraction reruns with:

```powershell
$env:EXTRACTION_RAG_ENABLED = "1"
```

The index is local, ignored by Git, and reused across reruns. If the embedding
service or index is unavailable, extraction falls back to deterministic
contract profiles and records that fallback in the extraction trace.

If Kaggle authentication is required in the local environment, configure Kaggle access as required by `kagglehub` before running the download command.

## Run the Complete Scenario

Start with a small run to verify the environment, model provider, MCP subprocess, and SQLite persistence:

```powershell
uv run python .\synthetic_data_loader\run_pipeline.py --limit 3
```

The batch driver then performs this complete path for each selected PDF:

1. Load and hash the PDF.
2. Extract each page with the configured LLM.
3. Merge page results into one `ContractCandidate`.
4. Launch the MCP server over stdio and call `ingest_contract`.
5. Persist the original PDF and contract data through the app services and SQLite infrastructure.
6. Print lifecycle status, skipped stages, hard failures, and an aggregate summary.

To process every downloaded PDF:

```powershell
uv run python .\synthetic_data_loader\run_pipeline.py
```

By default, the batch database is written to the shared repository database `clm.sqlite3`, which is also used by the web portal. Use `--database-path` to select another SQLite file and `--data-dir` to process a different directory:

```powershell
uv run python .\synthetic_data_loader\run_pipeline.py `
  --data-dir .\synthetic_data_loader\data\cuad_subset `
  --database-path .\clm.sqlite3 `
  --organization-id org_177e99f3478a46c99df4a3d9ddd3ec1d `
  --limit 3
```

When `--organization-id` is omitted, the runner automatically binds imported
contracts to the only organization in the selected database. Pass the option
when the database contains multiple organizations.

The pipeline is intentionally tolerant of incomplete extraction. It records unsupported lifecycle stages in `skipped_stages` instead of fabricating legal facts. Running the same PDF again is idempotent because its source hash maps to the same contract number.
