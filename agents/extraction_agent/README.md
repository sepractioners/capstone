# Capstone - Contract Extraction Agent

The extraction agent turns contract source files into validated contract candidates and submits them to the Contract Lifecycle Management domain through the MCP server.

## Supported Inputs

- **PDF**: page-by-page LLM extraction (with per-page chain-of-thought and
  cross-page working memory), then merge, then a document-level review pass.
- **JSON**: one candidate or one candidate per list item.
- **CSV**: one candidate per row, including numbered party columns such as `party_1_name` and `party_1_role`.

## Reasoning and Memory

The pipeline is `load → extract → review → ingest`.

- **Per page**: `extract_page()` fills a `reasoning` field first (logged to the
  trace, dropped from the candidate), then the typed fields. Each obligation
  carries its `trigger_event` and `consequence_of_failure`; the page also
  captures `renewal_terms` and `termination_terms` when stated. Working memory
  (`title`, `contract_type`, `parties`, `defined_terms`, `last_heading`,
  `renewal_terms`, `termination_terms`) is threaded page to page - a local for
  one run, never shared across documents.
- **Smarter retry**: a page is re-read when it comes back empty, or when a long
  page produced none of the RAG profile's `required_fields`.
- **Document review** (`review_node.py`, `EXTRACTION_REVIEW_ENABLED=1`): one call
  over the assembled candidate + full text does the final `contract_type`
  classification, an independent read of parties/dates/value voted against the
  page-merge result, and consistency checks. It raises `ReviewFinding`s; a
  `blocker` (or a directive that disagrees with the document) returns
  `requires_human_confirmation` and skips the write.
- **Obligation analysis** (`obligation_analysis` trace stage): the review call
  also reads each material commitment/right as `{trigger, consequence, deadline
  basis, materiality}` and folds a "what matters" list into `review_summary`.
  Deterministic checks flag silent auto-renewal, an unbounded
  termination-for-convenience right, and high-materiality obligations with no
  stated consequence - all informational, never blockers.
- **Date math** (via the shared `contract_calc`): the review pass computes the
  auto-renewal opt-out deadline (expiration minus the notice window), flags an
  obligation due after the contract expires, and flags a term of under a week -
  the same helpers the query agent's portfolio tools use.
- **Persistence**: triggers/consequences and renewal/termination terms are
  written onto the contract during drafting via
  `Contract.record_extracted_terms` (`Obligation.consequence_of_failure` /
  `evidence_requirements` / grace period, `RenewalTerms`, `TerminationTerms`,
  `KeyDates.renewal_deadline` / `termination_notice_deadline`), so the query
  agent and the portal see them on the stored contract.

Full detail: [Memory and Reasoning](../../docs/architecture/memory-and-reasoning.md).

## Documentation

- [Architecture](docs/architecture.md): end-to-end flow across the extraction agent, MCP client, MCP server, application services, domain, and SQLite storage.
- [Agent Internals](docs/agent-internals.md): LangGraph state, PDF and structured-input branches, prompt execution, merging, mapping, and MCP handoff.
- [Kaggle CUAD Scenario](docs/kaggle-cuad.md): dataset source, download steps, subset selection, and complete PDF pipeline test.
- [Usage](docs/usage.md): installation, Python API, model configuration, MCP tools, and tests.
- [Extraction Improvement Test Log](docs/improvement-test-log.md): hypotheses, local-model experiments, validation commands, and observed field coverage.
- [Troubleshooting and Lessons Learned](docs/troubleshooting.md): async LLM behavior, local-model extraction quality, prompt tuning, and known limitations.
- [Contract Profiles](profiles): reference profiles retained for comparison/fallback; enabled RAG uses the hybrid text/vector knowledge index.
- `rag_knowledge.jsonl`: procedural contract-type knowledge embedded into the vector index; runtime extraction does not depend on the YAML profile files.

## Hybrid RAG

The runtime RAG store (`hybrid_rag.py`, wrapped by `vector_rag.py`) merges two
retrieval signals over local procedural knowledge and Kaggle CUAD examples:

- **Lexical**: a SQLite FTS5 index (`rag_text`) preserves exact legal terms,
  headings, and entities.
- **Semantic**: per-record embeddings from the local Ollama model
  `nomic-embed-text:latest`. By default the cosine search runs over vectors
  serialized in SQLite; an optional FAISS backend can replace it.

RAG informs what fields to look for and how to validate them. The source PDF
remains the authority; retrieval never overrides visible evidence.

### Build The Index

The generated hybrid database contains procedural knowledge plus Kaggle CUAD
examples. It is built locally and ignored by Git:

```powershell
uv run python -m extraction_agent.build_rag_index
```

`build_rag_index` reads `EXTRACTION_RAG_DATA_DIR`
(default `synthetic_data_loader/data/cuad_subset`) and
`EXTRACTION_RAG_KNOWLEDGE_PATH` (default the packaged `rag_knowledge.jsonl`),
writes the JSON vector index at `EXTRACTION_RAG_INDEX`
(default `synthetic_data_loader/data/cuad_vector_index.json`), and upserts the
same records into the hybrid SQLite store at `EXTRACTION_RAG_DB`
(default `synthetic_data_loader/rag_knowledge.sqlite3`).

Additional datasets can be normalized into JSONL records with
`python -m extraction_agent.import_rag_dataset <input> <output> --dataset <name>`
and pointed at through `EXTRACTION_RAG_KNOWLEDGE_PATH`. Each record should
contain `id`, `text`, `dataset`, `knowledge_type`, `contract_type`, and
optional field guidance. This supports curated exports from datasets such as
LEDGAR or ContractNLI without embedding their original storage format into the
extraction code.

### Enable Retrieval During Extraction

```powershell
$env:EXTRACTION_RAG_ENABLED = "1"
$env:EXTRACTION_RAG_DB = "synthetic_data_loader/rag_knowledge.sqlite3"
```

When `EXTRACTION_RAG_ENABLED` is not `1`, the PDF path skips retrieval and
records `retrieval_mode: rag_unavailable` in the extraction trace.

### Semantic Backend Options

The local hybrid store uses SQLite FTS5 for lexical retrieval. FAISS can be
enabled as the semantic backend without running Elasticsearch:

```powershell
uv sync --all-packages --extra rag
$env:EXTRACTION_RAG_BUILD_FAISS = "1"
python -m extraction_agent.build_rag_index
$env:EXTRACTION_RAG_VECTOR_BACKEND = "faiss"
```

The current environment must use a FAISS build compatible with its NumPy
version; the optional extra pins `numpy<2` for the common Windows wheel case.
If FAISS is unavailable, the SQLite-serialized vectors remain the fallback. A
true Lucene backend requires a Java/PyLucene or service runtime; SQLite FTS5 is
the local lexical substitute, while Elasticsearch remains a containerized
production option.

## Quick Start

From the repository root:

```powershell
uv sync --all-packages
```

For the complete Kaggle-backed scenario, follow [Kaggle CUAD Scenario](docs/kaggle-cuad.md). For a direct API example, see [Usage](docs/usage.md).
