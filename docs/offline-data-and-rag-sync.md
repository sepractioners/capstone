# Offline Data and RAG Sync — Decision Brief

Status: **draft for review**. This document captures the shared understanding
behind removing the Kaggle dependency from setup, keeping the app's synthetic
data in sync with the RAG knowledge base, and choosing which public datasets to
rely on. It is a decision brief, not an implementation — open questions are
listed at the end.

## 1. Problem

The setup and installation scripts currently depend on a Kaggle CUAD download for
**both** the RAG knowledge index and the demo/test contract data. The goal is:

- **Setup completes fully offline** — no Kaggle account, no dataset download on
  the default path.
- Any public-dataset use is **opt-in and interactive**.

Investigating this surfaced deeper issues:

- **Three divergent definitions** of contract-type knowledge, none aligned:
  - `agents/extraction_agent/rag_knowledge.jsonl` — 27 profiles, hyphenated slugs
  - `seed_database.py` → `SAMPLE_RAG_KNOWLEDGE` — 4 profiles, underscored slugs,
    seeded on every setup run
  - `synthetic_data_loader/seed_contracts.py` → `_CONTRACT_TYPES` — 10 generator
    types; only 5 match a RAG profile, 3 are near-misses
    (`services-agreement` vs `service-agreement`, `nda` vs
    `confidentiality-agreement`, `distribution-agreement` vs
    `distributor-agreement`)
- **Bug:** 15 of 27 records in `rag_knowledge.jsonl` have `knowledge_type` set to
  the contract-type slug instead of `"contract_profile"`. `vector_rag.retrieve_vector_profile`
  filters on `knowledge_type == "contract_profile"` to pick the procedural match,
  so more than half the profiles are invisible to vector retrieval.
- **Four setup entry points**: `scripts/setup-windows.ps1`, `scripts/setup-linux.sh`,
  `scripts/setup-mac.sh`, and `tools/setup/main.py`. The Python one is stale
  (references `web.clm_web.db`, `run-mac.sh`, no seeding).
- The app's synthetic contract data and the RAG knowledge base **must be kept in
  sync** — same contract-type vocabulary, field profiles, and clause set.
- Vertical scope and dataset/licensing strategy were undecided.

## 2. What we know

### Code

- `synthetic_data_loader/seed_contracts.py` already generates 120 varied,
  valid contracts **fully offline** (no LLM, no network), idempotent per
  `--seed`, and binds them to an organization so they show in the portal. It is a
  ready replacement for the demo portfolio.
- `agents/extraction_agent/build_rag_index.py` works offline from the bundled
  `rag_knowledge.jsonl` (27 records). Its only external need is an Ollama
  embedding endpoint (`nomic-embed-text`).
- `platform_testing/extraction_eval.py` genuinely needs real contract documents
  plus a ground-truth JSONL. Current ground truth is 8 records, covering only
  `co-branding-agreement` and `affiliate-agreement`.
- `synthetic_data_loader/download_cuad_subset.py` is the **only** module that
  actually calls Kaggle (`kagglehub`).

### Datasets

- Every major annotated contract dataset is **CC BY 4.0**: CUAD, LEDGAR, ACORD,
  ContractNLI, MAUD. Redistributing a subset in git is permitted; the obligation
  is an attribution file (dataset name, authors, license link, source URL, and a
  note of any modifications).
- **HuggingFace** is the canonical host for all of them and needs **no
  authentication** for public datasets — strictly better than kagglehub, which
  the current seed script already warns can require credentials.
- CLAUDETTE / unfair-ToS: some repackagings are **non-commercial** — handle with
  care.
- Public procurement data (OCDS, USASpending, EU TED) is large and free but is
  **structured metadata**, not contract prose — a different ingestion path and
  arguably a different product.
- **Concentration:** essentially all open annotated contract data is built from
  SEC Exhibit-10 material contracts — **public-company B2B commercial**
  agreements (~20 CUAD categories: affiliate, co-branding, distributor, franchise,
  IP, JV, license, maintenance, marketing, non-compete, outsourcing, promotion,
  reseller, service, sponsorship, strategic-alliance, supply, transportation,
  endorsement, hosting, agency, development). Healthcare, construction, energy,
  and financial services (ISDA/LSTA forms are copyrighted) have essentially no
  open corpus.

### Dataset reference

| Dataset | Task / shape | Vertical | License | Host |
|---|---|---|---|---|
| CUAD v1 | Clause extraction / QA; 510 full contracts, 41 clause labels | B2B commercial | CC BY 4.0 | HF `theatticusproject/cuad` |
| LEDGAR (in LexGLUE) | Provision classification; 80k provisions, 100 classes | B2B commercial | CC BY 4.0 | HF `coastalcph/lex_glue` |
| ACORD (ACL 2025) | Clause **retrieval**; 114 queries, 126k ranked pairs | B2B commercial | CC BY 4.0 | HF `theatticusproject/acord` |
| ContractNLI | NLI; 607 contracts, NDAs only | B2B (NDA) | CC BY 4.0 | Stanford NLP / HF |
| MAUD | Deal-point reading comprehension; merger agreements | M&A | CC BY 4.0 | HF `theatticusproject/maud` |
| LegalBench / LegalBench-RAG | Eval aggregators (many CUAD-derived tasks) | B2B commercial | per-task; CUAD parts CC BY 4.0 | HF `nguha/legalbench` |
| ContractEval (Aug 2025) | Clause-level **risk** identification | B2B commercial | see paper | arXiv 2508.03080 |
| CLAUDETTE / unfair-ToS | Unfair-clause detection; 100+ consumer ToS | B2C / consumer | CC BY-NC-SA (varies) | LexGLUE `unfair_tos` |
| OCDS / USASpending / TED | Structured tender/award metadata | Public procurement | open gov | data.open-contracting.org, etc. |

## 3. Decisions

### Proposed (pending confirmation)

| # | Decision |
|---|---|
| D1 | Anchor vertical = **public-company commercial B2B**. Other verticals are synthetic-only extensions. |
| D2 | **One catalog** (`contract_types.toml`) as the single source of truth for contract-type knowledge. |
| D3 | Per-type `grounding = empirical \| synthetic` flag drives picker eligibility, RAG disclaimers, and eval scope. |
| D4 | **kagglehub → huggingface_hub** everywhere. |
| D5 | CUAD becomes **opt-in** (`--with-cuad`) with an **interactive category picker**; it leaves the automated setup path. |
| D6 | The synthetic generator is the **default** portal demo data. |
| D7 | **Exclude** structured procurement data (OCDS / USASpending / TED) — note as future scope. |
| D8 | Three data tiers: **T0** in-git / offline (default) · **T1** opt-in CUAD · **T2** opt-in LEDGAR + ACORD. |

### Still open

1. Is the **eval** in scope and offline-runnable? If yes, commit ~15–25 curated
   CUAD `full_contract_txt` files plus matching ground truth (~1–2 MB) with an
   `ATTRIBUTION.md`.
2. Portal demo data: **synthetic-only**, or **synthetic + ~20 real** curated
   contracts?
3. RAG grounding: **catalog-derived profiles only**, or **also vendor a slice of
   ACORD / LEDGAR clauses** as real retrieval examples?
4. Catalog format: **TOML** (readable, needs a build step to feed RAG) vs
   **JSONL + extra keys** (trivial ingest, unpleasant to hand-edit)?
5. Sequencing: **minimal fix first** (fix the `knowledge_type` bug, align the 10
   generator slugs to existing RAG slugs, delete `SAMPLE_RAG_KNOWLEDGE`) vs
   **full catalog refactor now**?
6. `tools/setup/main.py`: fix to match the shell scripts, delete, or make it the
   canonical orchestrator the shell scripts wrap?
7. Does the generator cover **all catalog types**, or a curated **~12**?
8. Is **B2C / consumer ToS** (CLAUDETTE) in scope at all? Different contract
   shape and a non-commercial license.
9. State the **US-jurisdiction bias** of the RAG openly in the docs?

## 4. Target design (refined)

### Catalog

`contract_types.toml`, one entry per type:

```
slug · display_name · vertical · grounding · cuad_category · hf_datasets
party_roles · required_fields · recommended_fields · sample_clauses · guidance
```

Example:

```toml
[software-license-agreement]
display_name       = "Software License Agreement"
vertical           = "b2b-commercial"
grounding          = "empirical"          # has real open data
cuad_category      = "License_Agreements"
hf_datasets        = ["cuad", "ledgar", "acord"]
party_roles        = ["licensor", "licensee"]
required_fields    = ["licensor", "licensee", "software_description", "fees", "license_type"]
recommended_fields = ["usage_restrictions", "update_policy", "support_level", "audit_rights"]
guidance           = "..."

[healthcare-baa]
display_name  = "Business Associate Agreement"
vertical      = "healthcare"
grounding     = "synthetic"               # generator only, no open corpus
cuad_category = ""
disclaimer    = "No empirically grounded examples; profile is illustrative."
```

### Everything derives from the catalog

- RAG `contract_profile` records — replaces `SAMPLE_RAG_KNOWLEDGE` and the
  hand-maintained profiles in `rag_knowledge.jsonl`.
- `seed_contracts.py` generation vocabulary (types, party roles, clause set,
  field lists).
- The interactive CUAD category picker — offers only entries where
  `grounding = empirical`.
- `extraction_eval` type labels.

### Data tiers

- **Tier 0 — always in git, zero network (the default setup path)**
  - `contract_types.toml` catalog (authored — no license question)
  - synthetic generator (`seed_contracts.py`) — the default portal demo data
  - RAG `contract_profile` records generated from the catalog
  - *(optional)* ~15–25 curated CUAD `full_contract_txt` files, 2–3 per major
    type, in `data/contracts_sample/` with `ATTRIBUTION.md`
  - *(optional)* `extraction_eval` ground-truth JSONL covering exactly those
    curated contracts → eval runs offline
- **Tier 1 — opt-in, one flag (`--with-cuad`), interactive picker**
  - Full CUAD via `huggingface_hub.snapshot_download(repo_id="theatticusproject/cuad",
    repo_type="dataset", allow_patterns=[selected categories])`
- **Tier 2 — opt-in, documented, not wired into setup**
  - LEDGAR and/or ACORD from HF `datasets` to enrich the RAG index with real
    labeled / ranked clauses; ACORD enables real retrieval metrics
  - Raw EDGAR fetch for unlabeled stress testing (public domain; set a
    User-Agent, 10 req/s limit)

### Setup flow (all three scripts, non-interactive, no dataset network calls)

1. Create `.env` from `.env.example` (if missing)
2. Python virtual environment + dependencies
3. HTTPS certificates
4. DB init + seed tenant/admin + **N synthetic contracts** + **RAG profiles from
   the catalog**
5. Build the embedding index (offline; skip cleanly if no embedding provider is
   configured)
6. Frontend / admin-console dependencies

`--with-cuad` adds the interactive Tier-1 step after step 4.

### Invariants (enforced by tests)

- Generator types are a subset of catalog types.
- Exactly one `contract_profile` per catalog type after seeding.
- Every profile has `knowledge_type == "contract_profile"`.
- Eval ground-truth types are a subset of catalog types.

### Cleanup bundled into the change

- Fix the `knowledge_type` bug in `rag_knowledge.jsonl`.
- Delete `SAMPLE_RAG_KNOWLEDGE` from `seed_database.py`.
- Reconcile or remove `tools/setup/main.py`.
- Update `README.md`, `SETUP.md`, `synthetic_data_loader/README.md`, and rename
  `agents/extraction_agent/docs/kaggle-cuad.md` → `datasets.md`.
- Update `docs/data-lifecycle.md` — the "two sources" section still names Kaggle
  CUAD as a primary source.

## References

- [Data Lifecycle](data-lifecycle.md) — current contract data flow
- [Seeding Guide](../SEEDING.md)
- [Synthetic Data Loader](../synthetic_data_loader/README.md)
- [Kaggle CUAD Scenario](../agents/extraction_agent/docs/kaggle-cuad.md)
- CUAD — <https://github.com/TheAtticusProject/cuad>, <https://huggingface.co/datasets/theatticusproject/cuad>
- LexGLUE (LEDGAR, unfair-ToS) — <https://huggingface.co/datasets/coastalcph/lex_glue>
- ACORD — <https://aclanthology.org/2025.acl-long.1206/>, <https://huggingface.co/datasets/theatticusproject/acord>
- ContractNLI — <https://stanfordnlp.github.io/contract-nli/>
- LegalBench — <https://huggingface.co/datasets/nguha/legalbench>
- Open Contracting Data Standard — <https://standard.open-contracting.org/>
