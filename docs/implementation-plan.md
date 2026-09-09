# Implementation Plan — ADR-0001 / 0002 / 0003

Tracks the work to move all three ADRs from **Proposed** to **Accepted** and
shipped. Source of truth for scope is each ADR; this file is the sequencing and
the issue/label map.

- [ADR-0001](adr/0001-offline-first-contract-data-and-type-catalog.md) — offline-first data + one contract-type catalog
- [ADR-0002](adr/0002-query-agent-evaluation-substrate.md) — bounded query-agent review substrate
- [ADR-0003](adr/0003-query-agent-stress-corpus.md) — pre-built query-agent stress corpus

## Milestones

| # | Milestone | Exit criteria |
|---|---|---|
| **M0** | Decisions | Issues #1, #13, #19 resolved; ADR open-question sections updated |
| **M1** | Catalog core | One catalog drives RAG profiles + the generator; invariants green |
| **M2** | Offline setup | `setup-*` completes with zero dataset network calls; `--with-cuad` is the only path that touches a dataset host → **ADR-0001 Accepted** |
| **M3** | Review substrate | Pinned snapshot + `query-agent-review-scope.md` published → **ADR-0002 Accepted** |
| **M4** | Stress corpus | `data/stress_corpus/` builds, bulk-loads as a separate tenant, attributed → **ADR-0003 Accepted** |
| **M5** | Eval depth (optional) | ACORD retrieval harness + query-agent scenarios |

## Dependency graph

```
#1 decision ─┬─> #2 catalog ─┬─> #3 rag-gen ──┐
             │               ├─> #5 generator ─┼─> #10 invariants ─> #12 ADR-0001 Accepted
             │               └─> #4 drop SAMPLE_RAG_KNOWLEDGE
             └─> (format/sequencing feeds all of M1)

#6 hf_hub ─> #7 picker ─> #8 setup-scripts ─> #12
#9 tools/setup reconcile ─> #12
#11 docs ─> #12

#13 decision ─> #14 snapshot-script ─> #15 review-doc ─> #18 ADR-0002 Accepted
#16 facet-edge test ─> #18

#19 decision ─> #20 schema+synthesis ─> #21 build-script ─> #23 bulk-load ─> #26 ADR-0003 Accepted
#22 attribution ─> #26

#17, #24, #25 optional (M5)
```

## Labels

Created by `scripts/gh-bootstrap-tracking-issues.sh`.

| Label | Hex | Meaning |
|---|---|---|
| `epic` | `3E4B9E` | Tracking issue spanning an ADR |
| `adr-0001` | `0E8A16` | Offline-first data + catalog |
| `adr-0002` | `1D76DB` | Query-agent review substrate |
| `adr-0003` | `5319E7` | Query-agent stress corpus |
| `decision` | `D93F0B` | Resolves an ADR open question; gates a status change |
| `setup` | `FBCA04` | Setup / install scripts |
| `rag` | `0052CC` | RAG knowledge base / index |
| `query-agent` | `006B75` | Query-agent behaviour / evaluation |
| `synthetic-data` | `BFD4F4` | Generator / `seed_contracts.py` |
| `datasets` | `C2E0C6` | Public-dataset ingestion / licensing |
| `eval` | `FEF2C0` | Test harnesses / accuracy metrics |
| `docs` | `0075CA` | Documentation |
| `tests` | `BFDADC` | Automated tests / invariants |
| `blocked` | `B60205` | Waiting on a decision or another issue |

## Issues

Epics first, then tasks. "Blocked by" = hard dependency.

### Epics

- **#E1 [Epic] ADR-0001: offline-first contract data + single type catalog**
  — `epic, adr-0001`. DoD: `setup-*` completes offline with no dataset network
  call; catalog drives generator + RAG; invariants green; ADR-0001 → Accepted.
- **#E2 [Epic] ADR-0002: bounded query-agent review substrate**
  — `epic, adr-0002`. DoD: pinned snapshot regenerable from clean clone;
  `docs/query-agent-review-scope.md` published; ADR-0002 → Accepted.
- **#E3 [Epic] ADR-0003: pre-built query-agent stress corpus**
  — `epic, adr-0003`. DoD: `data/stress_corpus/` artifact + embeddings build via
  script, bulk-load as separate tenant, per-source attribution; ADR-0003 → Accepted.

### ADR-0001 tasks

| # | Title | Labels | Blocked by |
|---|---|---|---|
| 1 | Decide catalog format (TOML vs JSONL) and sequencing (minimal fix vs full refactor) | `decision, adr-0001` | — |
| 2 | Create `contract_types.toml` — schema + initial entries with `grounding` flags | `adr-0001, datasets` | 1 |
| 3 | Catalog → RAG `contract_profile` generator; set `knowledge_type` correctly for all profiles | `adr-0001, rag` | 2 |
| 4 | Delete `SAMPLE_RAG_KNOWLEDGE` from `seed_database.py`; single RAG-seed path | `adr-0001, rag` | 3 |
| 5 | Refactor `seed_contracts.py` to derive types / clauses / field lists from the catalog | `adr-0001, synthetic-data` | 2 |
| 6 | Switch `download_cuad_subset.py` from `kagglehub` to `huggingface_hub.snapshot_download` (`allow_patterns`) | `adr-0001, datasets` | — |
| 7 | Make CUAD opt-in (`--with-cuad`) with interactive category picker + non-interactive fallback | `adr-0001, datasets, setup` | 6 |
| 8 | Rewrite `setup-windows.ps1` / `setup-linux.sh` / `setup-mac.sh`: no default dataset network; add synthetic-seed step; wire `--with-cuad` | `adr-0001, setup` | 5, 7 |
| 9 | Reconcile or remove `tools/setup/main.py` | `adr-0001, setup` | 8 |
| 10 | Invariant tests: generator ⊆ catalog; exactly one profile per type; `knowledge_type == "contract_profile"`; eval truth ⊆ catalog | `adr-0001, tests` | 3, 5 |
| 11 | Docs: `README.md`, `SETUP.md`, `synthetic_data_loader/README.md`, rename `kaggle-cuad.md` → `datasets.md`, update `data-lifecycle.md` | `adr-0001, docs` | 8 |
| 12 | Clear ADR-0001 open questions; flip Status to Accepted | `decision, adr-0001` | 4, 8, 9, 10, 11 |

### ADR-0002 tasks

| # | Title | Labels | Blocked by |
|---|---|---|---|
| 13 | Pin review snapshot parameters (seed string + contract count) | `decision, adr-0002` | — |
| 14 | Snapshot regeneration script → emits contract-type/lifecycle distribution table + sample-question answers | `adr-0002, query-agent, eval` | 13 |
| 15 | Write `docs/query-agent-review-scope.md` — claims, reproduce recipe, in/out scope, glossary, sample Q&A | `adr-0002, docs` | 14 |
| 16 | Test: planner emits a `contract_type` string that misses the facet value (deterministic guard must catch it) | `adr-0002, query-agent, tests` | — |
| 17 | *(optional)* Query-agent scenario set in `platform_testing/` | `adr-0002, query-agent, eval` | 13 |
| 18 | Clear ADR-0002 open questions; flip Status to Accepted | `decision, adr-0002` | 15, 16 |

### ADR-0003 tasks

| # | Title | Labels | Blocked by |
|---|---|---|---|
| 19 | Resolve ADR-0003 open questions (corpus size, CUAD categories, embedding model + commit-vs-rebuild vectors, LEDGAR in/out, repo size budget, eval timing, procurement add-on) | `decision, adr-0003` | — |
| 20 | Define `data/stress_corpus/` schema + deterministic synthesis rules for `lifecycle_status` and `contract_value` / currency | `adr-0003, datasets` | 19 |
| 21 | Maintainer build script: CUAD `master_clauses.csv` + ACORD → normalized JSONL + pre-computed embeddings | `adr-0003, datasets` | 20 |
| 22 | `data/stress_corpus/ATTRIBUTION.md` + `CHANGES` per source; add entry to the app licenses page | `adr-0003, docs, datasets` | 21 |
| 23 | Bulk-load step in setup — load the stress corpus as a separate organization/tenant | `adr-0003, setup` | 21 |
| 24 | *(optional)* ACORD retrieval eval harness (NDCG / recall@k) over `search_clauses` | `adr-0003, eval, query-agent` | 23 |
| 25 | *(optional)* Bounded USASpending / OCDS slice for deterministic-tool scale stress (no clause text) | `adr-0003, datasets, eval` | 23 |
| 26 | Clear ADR-0003 open questions; flip Status to Accepted | `decision, adr-0003` | 22, 23 |

## Branch strategy

The three ADR branches are stacked: `offline-setup-data-strategy` →
`query-agent-review-scope-adr` → `query-agent-stress-corpus-adr`. Merge ADRs to
`master` in order (0001, 0002, 0003) before starting implementation PRs, or keep
each epic's implementation on a branch off the corresponding ADR branch.
