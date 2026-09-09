# ADR-0003: Pre-built stress corpus for query-agent validation

- **Status:** Proposed
- **Date:** 2026-09-08
- **Deciders:** Capstone team
- **Relates to:** [ADR-0001](0001-offline-first-contract-data-and-type-catalog.md), [ADR-0002](0002-query-agent-evaluation-substrate.md)
- **Supersedes:** —
- **Superseded by:** —

## Context and problem statement

[ADR-0002](0002-query-agent-evaluation-substrate.md) pins a **deterministic
synthetic portfolio** as the query-agent review substrate. That substrate is
reproducible and licensing-clean, but it is generated from our own templates: a
fixed clause set, fixed party-name patterns, fixed value/date distributions. It
cannot exercise the query agent on the things that actually break portfolio
analytics and clause retrieval in the wild:

- **Clause paraphrase variance** — `find_contracts` is literal phrase
  containment; `search_clauses` embedding ranking degrades under rewording.
- **Real party-name messiness** — "Acme Inc." / "Acme, Incorporated" / "Acme"
  across contracts; `where: party` is a normalized substring match.
- **Multi-currency, wide-magnitude values** — does `aggregate_contracts` sum
  USD + EUR + GBP blindly?
- **Contract-type breadth and near-synonyms** — services vs MSA vs SOW;
  distribution vs reseller vs supply.
- **Enumeration completeness at scale** — does `find_contracts` return *every*
  match across a large, heterogeneous set?

We need a **real-contract-derived corpus** to give validation depth (stress
testing), chosen for the category that stresses the agent most, and included in
a form that does **not** re-run extraction, embedding, or downloads on every
`setup`.

## Decision drivers

- Depth on the query agent's weakest paths: retrieval recall under paraphrase,
  aggregation correctness, enumeration completeness, party resolution.
- Reproducible and offline — consistent with ADR-0001 and ADR-0002.
- Licensing must permit bundling a transformed derivative in the repository.
- Small repository footprint; no binary blobs that drift from the schema.
- No per-setup extraction, embedding compute, or network calls.
- Must not weaken ADR-0002's guarantee that the *synthetic* substrate stays the
  reproducible baseline.

## Considered options

### Which contract category

1. **Single-type corpora** — ContractNLI (NDAs), MAUD (merger agreements).
   Deep on one type; `contract_type` filtering and `group_by` are barely
   exercised. Rejected.
2. **Consumer ToS** — CLAUDETTE. No value / date / party / lifecycle structure;
   wrong shape for a portfolio-analytics agent. Also non-commercial in some
   repackagings. Rejected.
3. **Public procurement metadata** — OCDS / USASpending / EU TED. Extreme scale
   and breadth for the deterministic tools (`count` / `aggregate` / `group_by` /
   date filters / party resolution), but **no clause text** — exercises none of
   `find_contracts` / `search_clauses` / `interpret`. Useful only as a
   scale-only add-on. Not the primary corpus.
4. **Complex commercial B2B + M&A deal-point clauses (chosen)** — SaaS /
   licensing / distribution / services agreements plus the hard M&A clauses.
   Highest clause-type density and drafting variation, genuine multi-currency
   and wide value ranges, intricate renewal/termination/notice structures.
   CUAD, ACORD, and LEDGAR all concentrate here, so real ground truth exists.
   Matches ADR-0001's anchor vertical.
5. **Raw EDGAR dump** — reintroduces the extraction confounder with no ground
   truth. Rejected.

### How to include it

1. **Seed from raw datasets on every setup** — re-download, re-extract,
   re-embed each time. Slow, network-dependent, the problem ADR-0001 removes.
   Rejected.
2. **Dynamic opt-in download** — fine for the Tier-1 CUAD path (ADR-0001), but
   the stress corpus should be present by default for reviewers. Not primary.
3. **Pre-built compact normalized artifact committed to the repo (chosen)** —
   `data/stress_corpus/*.jsonl` (~1–2 MB) plus pre-computed embeddings, loaded
   by one bulk insert at setup. Git-diffable, rebuildable, no per-setup compute.
4. **Pre-built SQLite blob** — zero build step, but a binary that drifts from
   the schema and needs Git LFS past a few MB. Rejected as primary; may be an
   optional convenience artifact.

## Decision outcome

- **C1.** The stress corpus category is **complex commercial B2B**
  (SaaS / licensing / distribution / services) **+ M&A deal-point clauses**.
- **C2.** Sources: **CUAD** (structured records derived from its
  `master_clauses.csv` per-contract annotations) and **ACORD** (graded
  clause-retrieval query/clause pairs). **LEDGAR** is an optional Tier-2 add-on
  for labeled-provision recall testing.
- **C3.** Included **pre-built**: a committed normalized artifact under
  `data/stress_corpus/` (JSONL for records + clauses, plus pre-computed
  embedding vectors), loaded at setup by a single bulk insert. No extraction,
  no embedding compute, no network on the default path.
- **C4.** Fields CUAD does not provide — `lifecycle_status` and
  `contract_value` (with currency, deliberately mixed USD/EUR/GBP) — are
  **synthesized deterministically** from a fixed seed; the synthesis rules are
  documented in `data/stress_corpus/README.md`.
- **C5.** Verbatim text is **bounded**: CUAD clause excerpts capped (target
  ≤ ~500 characters each); ACORD clause text is bundled in full because it *is*
  the dataset.
- **C6.** Attribution: `data/stress_corpus/ATTRIBUTION.md` per source (citation,
  license notice + link, warranty disclaimer, source URL) and a `CHANGES`
  section recording the transformations (subset, schema normalization,
  synthesized fields, dropped annotation spans). Surface the same on the app's
  licenses page.
- **C7.** The stress corpus loads as a **separate organization/tenant**, distinct
  from ADR-0002's synthetic portfolio. Query-agent review can target either;
  ADR-0002's synthetic baseline and its reproducibility guarantee are unchanged.

### Licensing scope (why C3/C5/C6 are permitted)

CUAD, ACORD, and LEDGAR are all **CC BY 4.0** (verified against dataset cards
and repo LICENSE files; LEDGAR's code repo is additionally MIT). CC BY 4.0
grants — for any purpose including commercial — the rights to reproduce,
**remix / transform / build upon**, and redistribute derivatives. None carry
NonCommercial, ShareAlike, or NoDerivatives terms.

Obligations, all met by C6:

1. Attribution — creator, title, citation as specified by each dataset.
2. Retain the copyright notice, license notice, and warranty disclaimer.
3. Link to `https://creativecommons.org/licenses/by/4.0/` and to each source.
4. **Indicate that changes were made** — the `CHANGES` section.

Residual risk: CUAD disclaims warranty on the *underlying* contracts (EDGAR
filings). SEC filings are public records and routinely redistributed; bundling
only derived structured metadata and short excerpts (not full PDFs) keeps this
low. Noted in `ATTRIBUTION.md`.

## Consequences

### Positive

- Real drafting variation, party-name messiness, multi-currency values, and
  clause-type breadth — the query agent's failure surface is actually exercised.
- ACORD's graded relevance judgments enable real retrieval metrics
  (NDCG / recall@k) on hard clauses, not just eyeballed answers.
- Present by default for reviewers, offline, with no per-setup compute.
- Licensing is unambiguous and documented.

### Negative / costs

- A build step (run by maintainers, not at setup) to regenerate the normalized
  artifact + embeddings when the source datasets or our schema change.
- Pre-computed embeddings are tied to one embedding model; changing the model
  invalidates them (mitigate: record the model + dimension in the artifact
  header; rebuild is a maintainer task).
- ~1–2 MB plus embedding vectors enter the repo; needs a size budget
  (open question 5).
- Synthesized `lifecycle_status` / `contract_value` are fabrications layered on
  real contracts — must be clearly labelled so no reviewer mistakes them for
  real deal terms.

### Follow-up work

- Define the `data/stress_corpus/` schema and the deterministic synthesis rules.
- Maintainer build script: CUAD `master_clauses.csv` + ACORD → normalized JSONL
  + embeddings.
- Bulk-load step in the setup scripts (separate org/tenant).
- Optional: an ACORD-based retrieval eval harness in `platform_testing/`.
- Optional scale-only add-on: a bounded USASpending / OCDS slice for
  deterministic-tool stress (no clause text).

## Open questions

*Must be resolved (and this section emptied) before Status moves to Accepted.*

1. Target corpus size — how many contracts from CUAD (all ~510, or a curated
   subset), and how many ACORD queries/pairs?
2. Which CUAD agreement categories are in scope for C1 (the full commercial
   set, or a named subset)?
3. Embedding model for the pre-computed vectors — reuse the app default
   (`nomic-embed-text`), and do we commit vectors or rebuild once at setup?
4. Is **LEDGAR** in for the first version, or deferred?
5. Repository size budget for `data/stress_corpus/` (artifact + vectors).
6. Does the ACORD retrieval eval harness land in this change or a later one?
7. Include the scale-only USASpending / OCDS add-on now, or note as future work?

## References

- [ADR-0001](0001-offline-first-contract-data-and-type-catalog.md) — dataset strategy and licensing framework
- [ADR-0002](0002-query-agent-evaluation-substrate.md) — the synthetic review substrate this corpus complements
- [Query Agent](../../agents/query_agent/README.md)
- [Platform Testing](../../platform_testing/README.md)
- CUAD — <https://huggingface.co/datasets/theatticusproject/cuad>, <https://github.com/TheAtticusProject/cuad>
- ACORD — <https://huggingface.co/datasets/theatticusproject/acord>, <https://aclanthology.org/2025.acl-long.1206/>
- LEDGAR — <https://github.com/dtuggener/LEDGAR_provision_classification>, <https://huggingface.co/datasets/coastalcph/lex_glue>
- CC BY 4.0 — <https://creativecommons.org/licenses/by/4.0/>
