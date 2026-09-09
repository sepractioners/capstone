# ADR-0001: Offline-first contract data and a single contract-type catalog

- **Status:** Proposed
- **Date:** 2026-09-08
- **Deciders:** Capstone team
- **Supersedes:** —
- **Superseded by:** —

## Context and problem statement

The setup and installation scripts depend on a Kaggle CUAD download for **both**
the RAG knowledge index and the demo/test contract data. This makes a clean
`git clone` → `setup` fail without a Kaggle account and network access to the
dataset, and it couples first-run success to an external service.

Investigating the coupling surfaced a second, deeper problem: contract-type
knowledge is defined in **three places that have drifted apart**, so the app's
seeded contracts and the RAG knowledge base no longer describe the same world.

- `agents/extraction_agent/rag_knowledge.jsonl` — 27 profiles, hyphenated slugs.
- `seed_database.py` → `SAMPLE_RAG_KNOWLEDGE` — 4 profiles, underscored slugs,
  seeded on **every** setup run.
- `synthetic_data_loader/seed_contracts.py` → `_CONTRACT_TYPES` — 10 generator
  types. Only 5 match a RAG profile; 3 are near-misses (`services-agreement` vs
  `service-agreement`, `nda` vs `confidentiality-agreement`,
  `distribution-agreement` vs `distributor-agreement`).

Related defects and debt found along the way:

- **Bug:** 15 of 27 records in `rag_knowledge.jsonl` set `knowledge_type` to the
  contract-type slug instead of `"contract_profile"`.
  `vector_rag.retrieve_vector_profile` filters on
  `knowledge_type == "contract_profile"` to pick the procedural match, so more
  than half the profiles are invisible to vector retrieval.
- **Four setup entry points:** `scripts/setup-windows.ps1`,
  `scripts/setup-linux.sh`, `scripts/setup-mac.sh`, and `tools/setup/main.py`.
  The Python one is stale (references `web.clm_web.db`, `run-mac.sh`, no seeding).
- The vertical scope of the platform and the dataset/licensing strategy were
  never written down.

We need setup to work offline, and we need one authoritative definition of
contract types that both the synthetic generator and the RAG knowledge base
derive from.

## Decision drivers

- A fresh clone must reach a working portal with **no external dataset and no
  account**.
- The app's synthetic contract data and the RAG knowledge base must stay in sync
  by construction, not by manual reconciliation.
- Honesty about coverage: the platform should not imply empirical grounding for
  contract types where none exists.
- Licensing must be unambiguous for anything committed to the repository.
- Keep the repository small; large corpora do not belong in git.
- Public-dataset use should remain **possible** for richer demos, evals, and
  retrieval metrics — just not on the default path.

## Considered options

### Data sourcing

1. **Offline synthetic only.** Ship the generator and catalog; no real contracts
   in the repo at all. Simplest and smallest, zero licensing surface. Weakest
   demo credibility; the extraction eval cannot run without a separate manual
   download.
2. **Bundled curated subset + opt-in dynamic (chosen).** Commit the catalog, the
   generator, and a small curated set of real contract text under CC BY 4.0 with
   attribution. Larger datasets are opt-in downloads. Balances offline-first with
   credibility; adds an attribution file and ~1–2 MB to the repo.
3. **Keep dynamic download, make it non-fatal.** Leave the Kaggle/HF download in
   setup but let it fail gracefully. Least change. Still needs network for a
   complete first run, still couples setup to an external service, does not fix
   the three-way drift.

### Contract-type definition

1. **Reconcile the three sources by hand and add a lint test.** Minimal change.
   Does not prevent the next drift; still three files to edit per type.
2. **Single catalog, everything derives from it (chosen).** One
   `contract_types.toml`; RAG profiles, generator vocabulary, the CUAD picker,
   and eval labels are all generated or validated against it. More upfront work;
   removes the drift class entirely.

### Dynamic dataset host

1. **kagglehub.** Status quo. Can require credentials (the current seed script
   warns about this); downloads the whole ~107 MB unit.
2. **huggingface_hub (chosen).** Canonical host for CUAD, LEDGAR, ACORD,
   ContractNLI, MAUD. No auth for public datasets. `snapshot_download` with
   `allow_patterns` fetches only selected categories.

## Decision outcome

Adopt **option 2 in each dimension**:

- **D1.** Anchor the platform on the **public-company commercial B2B** vertical.
  Other verticals are synthetic-only extensions.
- **D2.** Introduce **one catalog**, `contract_types.toml`, as the single source
  of truth for contract-type knowledge.
- **D3.** Each catalog entry carries `grounding = empirical | synthetic`. This
  flag drives CUAD-picker eligibility, RAG profile disclaimers, and eval scope.
- **D4.** Replace **kagglehub with huggingface_hub** everywhere.
- **D5.** CUAD becomes **opt-in** (`--with-cuad`) with an **interactive category
  picker**, and leaves the automated setup path.
- **D6.** The synthetic generator (`seed_contracts.py`) is the **default** portal
  demo data.
- **D7.** **Exclude** structured procurement data (OCDS / USASpending / EU TED)
  from scope; record it as future work.
- **D8.** Organize data into three tiers: **T0** in-git / offline (default),
  **T1** opt-in CUAD, **T2** opt-in LEDGAR + ACORD.

### Target design

**Catalog** — `contract_types.toml`, one entry per type:

```
slug · display_name · vertical · grounding · cuad_category · hf_datasets
party_roles · required_fields · recommended_fields · sample_clauses · guidance
```

```toml
[software-license-agreement]
display_name       = "Software License Agreement"
vertical           = "b2b-commercial"
grounding          = "empirical"
cuad_category      = "License_Agreements"
hf_datasets        = ["cuad", "ledgar", "acord"]
party_roles        = ["licensor", "licensee"]
required_fields    = ["licensor", "licensee", "software_description", "fees", "license_type"]
recommended_fields = ["usage_restrictions", "update_policy", "support_level", "audit_rights"]
guidance           = "..."

[healthcare-baa]
display_name  = "Business Associate Agreement"
vertical      = "healthcare"
grounding     = "synthetic"
cuad_category = ""
disclaimer    = "No empirically grounded examples; profile is illustrative."
```

**Derives from the catalog:**

- RAG `contract_profile` records — replaces `SAMPLE_RAG_KNOWLEDGE` and the
  hand-maintained profiles in `rag_knowledge.jsonl`.
- `seed_contracts.py` generation vocabulary (types, roles, clauses, field lists).
- The interactive CUAD category picker — offers only `grounding = empirical`
  entries.
- `extraction_eval` type labels.

**Data tiers:**

- **Tier 0 — always in git, zero network (default setup path)**
  - `contract_types.toml` (authored; no license question)
  - synthetic generator (`seed_contracts.py`) — the default portal demo data
  - RAG `contract_profile` records generated from the catalog
  - *(pending open question 1/2)* ~15–25 curated CUAD `full_contract_txt` files,
    2–3 per major type, in `data/contracts_sample/` with `ATTRIBUTION.md`
  - *(pending)* `extraction_eval` ground-truth JSONL covering exactly those files
- **Tier 1 — opt-in, `--with-cuad`, interactive picker**
  - `huggingface_hub.snapshot_download(repo_id="theatticusproject/cuad",
    repo_type="dataset", allow_patterns=[selected categories])`
- **Tier 2 — opt-in, documented, not wired into setup**
  - LEDGAR and/or ACORD from HF `datasets` to enrich the RAG index; ACORD enables
    real retrieval metrics
  - Raw EDGAR fetch for unlabeled stress testing (public domain; User-Agent
    required, 10 req/s)

**Setup flow (all three scripts, non-interactive, no dataset network calls):**

1. Create `.env` from `.env.example` (if missing)
2. Python virtual environment + dependencies
3. HTTPS certificates
4. DB init + seed tenant/admin + **N synthetic contracts** + **RAG profiles from
   the catalog**
5. Build the embedding index (offline; skip cleanly with no embedding provider)
6. Frontend / admin-console dependencies

`--with-cuad` adds the interactive Tier-1 step after step 4.

**Invariants (enforced by tests):**

- Generator types ⊆ catalog types.
- Exactly one `contract_profile` per catalog type after seeding.
- Every profile has `knowledge_type == "contract_profile"`.
- Eval ground-truth types ⊆ catalog types.

## Consequences

### Positive

- A fresh clone reaches a working, populated portal offline.
- One file to edit per contract type; drift between generator and RAG becomes a
  failing test, not a latent inconsistency.
- The `grounding` flag makes coverage claims explicit and auditable.
- Everything committed is CC BY 4.0 or authored in-house, with attribution
  recorded.
- Richer datasets stay one flag away for anyone who wants them.

### Negative / costs

- Upfront work: build the catalog, a catalog→RAG generator, the interactive
  picker, and the invariant tests; rewrite three setup scripts.
- ~1–2 MB and an `ATTRIBUTION.md` enter the repo (if open question 2 keeps the
  curated subset).
- A catalog in TOML needs a build step to produce RAG records (see open
  question 4).
- The RAG knowledge base carries a **US-jurisdiction bias** (EDGAR-sourced); this
  must be stated in the docs.

### Follow-up work

- Fix the `knowledge_type` bug in `rag_knowledge.jsonl`.
- Delete `SAMPLE_RAG_KNOWLEDGE` from `seed_database.py`.
- Reconcile or remove `tools/setup/main.py`.
- Update `README.md`, `SETUP.md`, `synthetic_data_loader/README.md`; rename
  `agents/extraction_agent/docs/kaggle-cuad.md` → `datasets.md`.
- Update `docs/data-lifecycle.md` — its "two sources" section still names Kaggle
  CUAD as a primary source.

## Open questions

*Must be resolved (and this section emptied) before Status moves to Accepted.*

1. Is the extraction **eval** in scope, and must it run offline? If yes, Tier 0
   gains the curated `full_contract_txt` subset + ground truth.
2. Portal demo data: **synthetic-only**, or **synthetic + ~20 real** curated
   contracts?
3. RAG grounding: **catalog-derived profiles only**, or **also vendor a slice of
   ACORD / LEDGAR clauses** as real retrieval examples?
4. Catalog format: **TOML** (readable, needs a build step) vs **JSONL + extra
   keys** (trivial ingest, unpleasant to hand-edit)?
5. Sequencing: **minimal fix first** (bug + slug alignment + delete
   `SAMPLE_RAG_KNOWLEDGE`) vs **full catalog refactor in one change**?
6. `tools/setup/main.py`: fix to match, delete, or promote to the canonical
   orchestrator the shell scripts wrap?
7. Does the generator cover **all catalog types**, or a curated **~12**?
8. Is **B2C / consumer ToS** (CLAUDETTE) in scope? Different contract shape and a
   non-commercial license in some repackagings.
9. State the **US-jurisdiction bias** of the RAG explicitly in the docs?

## Appendix: public contract datasets

All rows below are CC BY 4.0 unless noted. Redistributing a subset requires an
attribution file: dataset name, authors, license link, source URL, and a note of
any modifications.

| Dataset | Task / shape | Vertical | License | Host |
|---|---|---|---|---|
| CUAD v1 | Clause extraction / QA; 510 full contracts, 41 clause labels, ~25 agreement categories | B2B commercial | CC BY 4.0 | HF `theatticusproject/cuad`; GitHub `TheAtticusProject/cuad` |
| LEDGAR (in LexGLUE) | Provision classification; 80k provisions, 100 classes | B2B commercial | CC BY 4.0 | HF `coastalcph/lex_glue` (config `ledgar`) |
| ACORD (ACL 2025) | Clause **retrieval**; 114 queries, 126k ranked query–clause pairs | B2B commercial | CC BY 4.0 | HF `theatticusproject/acord` |
| ContractNLI | NLI (entailment/contradiction); 607 contracts, NDAs only | B2B (NDA) | CC BY 4.0 | Stanford NLP; HF |
| MAUD | Deal-point reading comprehension; merger agreements, 39k examples | M&A | CC BY 4.0 | HF `theatticusproject/maud` |
| LegalBench / LegalBench-RAG | Eval aggregators; many CUAD-derived clause tasks | B2B commercial | per-task; CUAD parts CC BY 4.0 | HF `nguha/legalbench` |
| ContractEval (Aug 2025) | Clause-level **risk** identification | B2B commercial | see paper (arXiv 2508.03080) | arXiv |
| CLAUDETTE / unfair-ToS | Unfair-clause detection; 100+ consumer ToS, ~20k clauses | B2C / consumer | CC BY-NC-SA (varies by repackaging) | LexGLUE `unfair_tos` |
| OCDS Data Registry | Structured tender/award/contract **metadata** (JSON/CSV) | Public procurement | open gov | data.open-contracting.org |
| USASpending / SAM.gov / FPDS | US federal contract awards | GovCon | public domain | usaspending.gov |
| EU TED | EU procurement notices | Public procurement (EU) | open, reusable | ted.europa.eu |

**Verticals with little or no open annotated data** (synthetic-only if in scope):
healthcare (BAAs, payer–provider, clinical trial agreements), construction / real
estate (AIA forms, leases), energy (JOAs, PPAs, PSAs), financial services (ISDA
and LSTA forms are **copyrighted** — cannot be bundled), insurance, grants.

**Concentration:** essentially all open annotated contract data derives from SEC
Exhibit-10 material contracts — public-company B2B commercial agreements. This is
also where the CLM market (Ironclad, Icertis, LinkSquares) competes, which is why
D1 anchors there.

## References

- [Data Lifecycle](../data-lifecycle.md)
- [Seeding Guide](../../SEEDING.md)
- [Synthetic Data Loader](../../synthetic_data_loader/README.md)
- [Kaggle CUAD Scenario](../../agents/extraction_agent/docs/kaggle-cuad.md)
- CUAD — <https://github.com/TheAtticusProject/cuad>, <https://huggingface.co/datasets/theatticusproject/cuad>
- LexGLUE (LEDGAR, unfair-ToS) — <https://huggingface.co/datasets/coastalcph/lex_glue>
- ACORD — <https://aclanthology.org/2025.acl-long.1206/>, <https://huggingface.co/datasets/theatticusproject/acord>
- ContractNLI — <https://stanfordnlp.github.io/contract-nli/>
- LegalBench — <https://huggingface.co/datasets/nguha/legalbench>
- Open Contracting Data Standard — <https://standard.open-contracting.org/>
- MADR template — <https://adr.github.io/madr/>
