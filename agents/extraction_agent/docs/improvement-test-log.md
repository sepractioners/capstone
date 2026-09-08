# Extraction Improvement Test Log

This log records extraction-quality hypotheses, experiments, commands, observed results, and follow-up decisions. Add an entry for every test run while improving the extraction agent.

## 2026-09-05 Baseline Review

### Evidence Reviewed

- `docs/troubleshooting.md`
- `docs/agent-internals.md`
- `extraction_node.py`
- `system_prompt.yaml`
- `schema.py`
- `graph.py`

### Previous Findings

- An earlier local Gemma/Ollama run reportedly returned schema-valid but empty optional fields; this is an observation to reproduce, not proof that the model cannot extract those fields.
- A directive prompt and worked example reportedly improved title, parties, clauses, and dates on a CUAD co-branding document; the comparison should be rerun with captured raw responses and field counts.
- Local inference latency is a runtime characteristic, not an extraction-quality failure by itself.
- Contract-type-specific field applicability and source evidence still need explicit validation.

### Local Model Availability

- Ollama executable: available.
- `gemma4:latest`: available.
- Controlled first-page extraction probe: exceeded the interactive tool window before a model response was collected.
- This is classified as `inconclusive_timeout`, not `model_failure` or `empty_extraction`.
- No claim about local-model quality is conclusive until a completed probe is recorded with its configured timeout, attempt count, raw parsed result, and field coverage.

## 2026-09-05 Agent Improvement

### Hypothesis

Missing fields may be caused partly by agent orchestration rather than only model capability: the page call previously received only a 200-character previous-page tail, contract type and commercial terms were weakly specified, and an empty structured response was accepted without a re-read.

### Changes Under Test

- Pass compact working memory containing observed title, contract type, and parties across PDF pages.
- Add explicit contract-type and commercial-term extraction instructions.
- Add a silent field verification checklist to the YAML prompt; no reasoning trace is requested or stored.
- Retry once when a non-empty page produces a suspiciously empty extraction.
- Wait up to 900 seconds per local LLM attempt by default, retrying up to three attempts with increasing backoff.
- Log timeout/provider failures separately from empty structured responses.

### Validation

| Test | Command | Result |
| --- | --- | --- |
| Python syntax | `.venv\\Scripts\\python.exe -m py_compile agents/extraction_agent/extraction_node.py agents/extraction_agent/graph.py` | Passed |
| Merge regression | `.venv\\Scripts\\python.exe -m pytest agents/tests/test_merge_node.py` | Could not run: pytest is not installed in `.venv` |
| Merge regression fallback | `python -m pytest agents/tests/test_merge_node.py` | Passed: 5 tests |
| Extraction resilience and merge regression | `python -m pytest agents/tests/test_extraction_node_resilience.py agents/tests/test_merge_node.py` | Passed: 7 tests in 72.70 seconds |
| Local Gemma first-page probe | Ollama `gemma4:latest` against a CUAD PDF page | Exceeded the interactive tool window before response; result is `inconclusive_timeout`, not a quality judgment |

### Next Required Experiments

1. Run one completed first-page Gemma extraction with a 900-second attempt budget and save parsed JSON plus field counts.
2. Run the same page twice, allowing the full retry budget, to measure variance.
3. Run a two-page sample with and without working memory and compare parties/title/type retention.
4. Validate fields against contract-type profiles and source evidence rather than treating every absent field as an error.
5. Run a small PDF scenario through the full pipeline and record lifecycle status, missing fields, timeout state, and attempt count.
6. Compare hosted/provider results only after the local baseline is complete.

## 2026-09-05 Completed Local Gemma Probe

### Fixture

- Model: Ollama `gemma4:latest`
- Provider: `ollama`
- Source: `2ThemartComInc_19990826_10-12G_EX-10.10_6700288_EX-10.10_Co-Branding Agreement_ Agency Agreement.pdf`
- Page: 1
- Extracted page text: 3,205 characters
- Response: completed successfully with HTTP 200 from Ollama

### Observed Coverage

```json
{
	"title": true,
	"contract_type": false,
	"parties": 2,
	"clauses": 12,
	"obligations": 0,
	"key_dates": 1,
	"commercial_terms": 0,
	"signers": 0
}
```

The model extracted the title `CO-BRANDING AND ADVERTISING AGREEMENT`, two named
parties, twelve definition clauses, and an effective date of `1999-06-21`.
The page did not contain a signature block, commercial pricing, or a clear
operational obligation. The zero counts for those fields are therefore not
automatically extraction failures.

### Corrected Assessment

- The local model is capable of returning substantial structured extraction.
- A missing `contract_type` is an agent classification gap worth improving;
	the title strongly supports `co-branding-agreement` but the model left it
	empty.
- Missing obligations, commercial terms, and signers on this page require
	contract-type/page-profile validation before being labelled defects.
- The earlier long-running/cancelled probe was a runtime observation only and
	must not be used as evidence of poor extraction quality.

### Next Improvement

Add contract-type profiles and source-backed field status so the system can
distinguish `missing`, `not_applicable`, `uncertain`, and `needs_human_confirmation`.
For this fixture, classification should be proposed from the title and sent
to human confirmation rather than silently defaulting to `unclassified`.

## 2026-09-05 Structured Trace and UI Observability

### Added

- Page-level extraction events with attempt counts and timeout/failure status.
- Working-memory keys recorded without exposing model chain-of-thought.
- Explicit RAG state recorded as disabled until profile/vector retrieval is implemented.
- Field coverage counts for title, type, parties, clauses, obligations, dates,
  commercial terms, and signers.
- Tenant-authorized `/contracts/{contract_id}/extraction-trace` endpoint.
- Contract-reader trace panel showing structured events, retries, memory keys,
  field coverage, and retrieval status.

### Validation

| Test | Result |
| --- | --- |
| Frontend TypeScript and production build | Passed |
| Python compilation for agent, MCP, and web packages | Passed |
| Fresh direct-ingest trace round trip | Passed |
| Reused source hash after a prior attempt | Returns the existing idempotent contract; its original trace is retained rather than replaced |

The trace UI intentionally shows observable execution metadata only. It does
not expose hidden model reasoning or imply that RAG was used when retrieval is
disabled.

## 2026-09-05 Contract Profile Retrieval Foundation

### Added

- YAML contract profiles for co-branding agreements, affiliate agreements,
  amendments, and unclassified contracts.
- Deterministic profile retrieval from source filename and first-page text.
- Profile context injected into page extraction prompts.
- Required and recommended field metadata for future applicability validation.
- Trace metadata for selected profile and retrieval mode.

### Validation

| Test | Result |
| --- | --- |
| Profile matches co-branding source/title | Passed |
| Unknown source remains unclassified | Passed |
| Extraction resilience and merge tests | Passed: 9 tests |
| Frontend typecheck and production build | Passed |

This is a deterministic profile-retrieval seam, not vector RAG yet. A vector
backend can replace `retrieve_profile()` while preserving the profile result
shape and trace contract.

## 2026-09-05 Hybrid Text and Semantic RAG

### Design

- SQLite FTS5 retrieves exact legal terms and entities.
- Ollama embeddings retrieve semantically similar procedural knowledge and
	Kaggle examples.
- Results are merged with a weighted lexical/vector score.
- The source document remains authoritative; RAG supplies context and field
	expectations only.

### Built Index

- Procedural profile records: `3`
- Kaggle CUAD example records: `31`
- Total hybrid records: `34`
- Query `Co-Branding Agreement.pdf` with its title retrieved the co-branding
	procedural profile with score `0.9469`.

### Validation

| Test | Result |
| --- | --- |
| Hybrid FTS/vector deterministic test | Passed |
| Hybrid co-branding retrieval against built local index | Passed |
| Full focused extraction/RAG suite | Passed: 10 tests |

## 2026-09-05 Dataset Import and Rerun Strategy

### Dataset Inputs

`import_rag_dataset.py` accepts JSON or JSONL exports with common fields such
as `text`, `sentence`, `context`, `clause`, `label`, `category`, and
`contract_type`. This provides a stable ingestion boundary for curated Kaggle
exports, LEDGAR-style clause records, and ContractNLI-style context records.

### Rerun Policy

1. Retrieve exact lexical matches and semantic knowledge records.
2. Compare retrieved field expectations with the previous extraction.
3. Re-extract only missing, uncertain, or conflicting fields when possible.
4. Preserve prior confirmed values and source evidence.
5. Record the new attempt, retrieval records, and field changes in the trace.
6. Require human confirmation before accepting conflicts or changing a
	previously confirmed field.

	### Contract Batch Failure and Repair

	- Sample: `2ThemartComInc_19990826_10-12G_EX-10.10_6700288_EX-10.10_Co-Branding Agreement_ Agency Agreement.pdf`
	- Failure: `AttributeError: 'str' object has no attribute 'legal_name'`
	- Classification: agent orchestration bug in cross-page memory, not an LLM timeout or extraction-quality result.
	- Cause: party memory stored names as strings, then the next page combined those strings with `ExtractedParty` objects and accessed `.legal_name` on every item.
	- Repair: normalize party memory through `_update_party_memory()` and keep JSON-safe names only.
	- Validation: `11` focused extraction/RAG/memory/merge tests passed.

## 2026-09-05 Kaggle Contract-Level Validation Setup

### Corpus

- The expanded CUAD Kaggle snapshot contains `198` unique PDF contracts across
	all available categories in `CUAD_v1/full_contract_pdf/Part_I`.
- The requested target was 200 complete contracts; this dataset snapshot does
	not contain 200 unique files, so no duplicates are being added.
- A second licensed dataset is required to reach a 200-contract corpus.

### Runner

`synthetic_data_loader/run_contract_batch.py` invokes the real extraction agent
once per complete PDF and appends both:

- JSONL checkpoint records under `platform_testing/reports/`
- Human-readable results to this Markdown log

The runner resumes completed source files, records failures independently, and
does not treat a slow local LLM as a corpus-level failure.

Run the available corpus with:

```powershell
uv run python .\synthetic_data_loader\run_contract_batch.py --limit 198
```

### Setup Validation

- Local corpus count: `198` PDFs.
- Runner compilation: passed.
- Smoke command with `--limit 0`: passed and intentionally invoked zero LLM extractions.
- Full local-Gemma batch: not started automatically because inference may take
	approximately ten minutes or more per contract.

The full command is resumable. Completed sources are skipped, and each
completed or failed contract is appended to this Markdown log.

### Contract Sample: `2ThemartComInc_19990826_10-12G_EX-10.10_6700288_EX-10.10_Co-Branding Agreement_ Agency Agreement.pdf`
- Timestamp: `2026-09-05T19:34:27.338645+00:00`
- Status: `failed`
- Lifecycle statuses: `none`
- Error type: `AttributeError`
- Error: `'str' object has no attribute 'legal_name'`

### Contract Sample: `2ThemartComInc_19990826_10-12G_EX-10.10_6700288_EX-10.10_Co-Branding Agreement_ Agency Agreement.pdf`
- Timestamp: `2026-09-05T21:44:43.714200+00:00`
- Attempt: `2`
- Status: `completed`
- Lifecycle statuses: `approved`
- Trace events: `10`
- Completed page events: `10`
- Failed page events: `0`
- Retrieved profiles: `co-branding-agreement`

### Contract Sample: `ACCELERATEDTECHNOLOGIESHOLDINGCORP_04_24_2003-EX-10.13-JOINT VENTURE AGREEMENT.PDF`
- Timestamp: `2026-09-05T22:53:51.325052+00:00`
- Attempt: `1`
- Status: `completed`
- Lifecycle statuses: `approved`
- Trace events: `4`
- Completed page events: `4`
- Failed page events: `0`
- Retrieved profiles: `co-branding-agreement`

### Contract Sample: `AgapeAtpCorp_20191202_10-KA_EX-10.1_11911128_EX-10.1_Supply Agreement.pdf`
- Timestamp: `2026-09-05T23:24:38.094464+00:00`
- Attempt: `1`
- Status: `completed`
- Lifecycle statuses: `approved`
- Trace events: `14`
- Completed page events: `14`
- Failed page events: `0`
- Retrieved profiles: `co-branding-agreement`

### Contract Sample: `AimmuneTherapeuticsInc_20200205_8-K_EX-10.3_11967170_EX-10.3_Development Agreement.pdf`
- Timestamp: `2026-09-06T00:27:32.589080+00:00`
- Attempt: `1`
- Status: `failed`
- Lifecycle statuses: `none`
- Error type: `RuntimeError`
- Error: `LLM extraction unavailable for page 23 after 3 attempts`

### Contract Sample: `AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.19_11788293_EX-10.19_Content License Agreement.pdf`
- Timestamp: `2026-09-06T03:39:36.215996+00:00`
- Attempt: `1`
- Status: `failed`
- Lifecycle statuses: `none`
- Error type: `RuntimeError`
- Error: `LLM extraction unavailable for page 2 after 3 attempts`

### Contract Sample: `AlliedEsportsEntertainmentInc_20190815_8-K_EX-10.34_11788308_EX-10.34_Sponsorship Agreement.pdf`
- Timestamp: `2026-09-06T04:10:15.328413+00:00`
- Attempt: `1`
- Status: `completed`
- Lifecycle statuses: `approved`
- Trace events: `11`
- Completed page events: `11`
- Failed page events: `0`
- Retrieved profiles: `co-branding-agreement`

### Contract Sample: `ArcaUsTreasuryFund_20200207_N-2_EX-99.K5_11971930_EX-99.K5_Development Agreement.pdf`
- Timestamp: `2026-09-06T05:38:26.152811+00:00`
- Attempt: `1`
- Status: `failed`
- Lifecycle statuses: `none`
- Error type: `RuntimeError`
- Error: `LLM extraction unavailable for page 1 after 3 attempts`

### Contract Sample: `ArcGroupInc_20171211_8-K_EX-10.1_10976103_EX-10.1_Sponsorship Agreement.pdf`
- Timestamp: `2026-09-06T14:03:22.611038+00:00`
- Attempt: `1`
- Status: `completed`
- Lifecycle statuses: `approved`
- Trace events: `5`
- Completed page events: `5`
- Failed page events: `0`
- Retrieved profiles: `co-branding-agreement`
