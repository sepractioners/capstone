# ADR-0002: Bounded evaluation substrate for the query agent

- **Status:** Proposed
- **Date:** 2026-09-08
- **Deciders:** Capstone team
- **Relates to:** [ADR-0001](0001-offline-first-contract-data-and-type-catalog.md)
- **Supersedes:** —
- **Superseded by:** —

## Context and problem statement

The capstone thesis concerns **agent reasoning quality** — planning, tool
selection, cross-contract enumeration, aggregation discipline, citation. Project
reviewers need to evaluate the query agent against that thesis.

Reasoning quality can only be assessed fairly if the data substrate is
controlled. If the portfolio the agent queries is arbitrary, live, or
non-reproducible, a wrong answer cannot be attributed to the agent versus the
data, and one reviewer's run cannot be compared to another's.

Today there is no stated evaluation boundary for the query agent:

- No pinned dataset. `seed_contracts.py` defaults to `--seed capstone-2026
  --count 120`, but nothing records that as *the* review snapshot, and nothing
  regenerates it verifiably.
- The isolation guarantees exist in code and in `docs/isolation-strategy.md`
  but are not collected into a claim a reviewer can check.
- "Synthetic data" refers to three different things (the app portfolio, the RAG
  contract profiles, the opt-in CUAD examples); reviewers will conflate them.
- Grounding provenance and the US-jurisdiction bias (see ADR-0001) are not
  disclosed to reviewers.

We need a defined, pinned, reproducible substrate for query-agent review, and a
reviewer-facing document that presents it.

## Decision drivers

- A reviewer must reproduce the exact portfolio from a clean clone, offline.
- Errors must be attributable to the agent, not to data variance.
- The closed-world guarantees (MCP-only, read-only, tenant-scoped, tool-computed
  arithmetic, no fabrication on provider failure) must be stated and checkable.
- No binary blobs in git; no licensing or privacy exposure.
- Keep the reviewer's path short — minutes to a working, populated portal.
- Set up a later automated query-agent eval without blocking on it now.

## Considered options

1. **No formal substrate.** Reviewers evaluate against whatever setup seeds.
   Zero work. Non-reproducible; cross-run comparison impossible; errors not
   attributable. Rejected.
2. **Commit a pre-built `clm.sqlite3` snapshot.** Fastest for reviewers.
   Introduces a binary blob that drifts from the code, and it does not exercise
   (or prove) the offline-first setup path. Rejected as the primary mechanism;
   may be offered later as an optional convenience.
3. **Pin a seed; regenerate from a clean clone (chosen).** The review snapshot
   is `seed_contracts.py --seed <pinned> --count <pinned>`, run by the standard
   offline setup. Reproducible, proves offline-first, no binary. Cost: the
   resulting distribution becomes a maintained fact that generator changes must
   update.
4. **Anonymised real contracts.** Highest realism. Licensing burden,
   non-reproducible, privacy risk, and it reintroduces the coupling ADR-0001
   removes. Rejected.

## Decision outcome

Adopt option 3 and publish a reviewer-facing document.

- **E1.** Query-agent review runs against the **deterministic synthetic
  portfolio only** — a pinned seed and count — never live or tenant data.
- **E2.** State the closed-world guarantees explicitly and cite where each is
  enforced:
  - reads only via the read-only `query_mcp_server`, which re-checks
    organization membership (`docs/isolation-strategy.md` §Query Flow)
  - the LLM cannot retrieve outside what the Query MCP supplies
    (`agents/query_agent/README.md`)
  - counts, sums, and date arithmetic are computed by deterministic tools
    (`count_contracts`, `aggregate_contracts`), never by the model
    (`agents/query_agent/README.md` steps 2–6)
  - `contract_type` / `lifecycle_status` filters are matched against
    **facet values derived from the stored data itself**
    (`query_agent/portfolio.py` `facets()` + `_infer_where`), so filter values
    are self-consistent with the portfolio by construction
  - a provider failure returns a terminal run failure, not a fabricated answer
- **E3.** Record the **pinned snapshot definition** in the repo — seed value,
  count, and the resulting contract-type and lifecycle-status distribution —
  regenerable from a clean clone by the documented recipe.
- **E4.** Publish **`docs/query-agent-review-scope.md`**: the E2 claims
  condensed, the E3 snapshot table, the reproduce-it recipe, an explicit
  in-scope / out-of-scope list, a three-term glossary, and sample review
  questions with expected answers.
- **E5.** Out of scope for query-agent review, stated plainly: extraction
  accuracy (covered by `platform_testing/extraction_eval.py`), real-contract
  linguistic nuance, and multi-jurisdiction coverage.
- **E6.** Disclose grounding provenance per ADR-0001: the contract-type catalog
  and RAG profiles are curated / CC BY-licensed, with a US-jurisdiction bias.

### Glossary to include (E4)

| Term | What it is | Source |
|---|---|---|
| **Synthetic portfolio** | The contracts the query agent answers over | `synthetic_data_loader/seed_contracts.py` (offline, deterministic) |
| **RAG seed knowledge** | Contract-type profiles guiding *extraction* | catalog → `rag_knowledge` (ADR-0001) |
| **CUAD examples** | Real contracts for richer demos / eval | opt-in `--with-cuad` (ADR-0001) |

## Consequences

### Positive

- Reviewers reproduce the substrate exactly; agent errors are attributable.
- The isolation and determinism claims become a checkable list, not folklore.
- Establishes the fixture for a later automated query-agent eval harness.
- No binary blobs, no licensing or privacy surface.

### Negative / costs

- The pinned distribution is a maintained fact: any change to `seed_contracts.py`
  or the seed/count must update `docs/query-agent-review-scope.md`.
- Sample Q&A expected answers must be recomputed on those changes — mitigated by
  generating them with a script rather than by hand.
- The LLM planner path can still emit a `contract_type` string that misses the
  facet value; this is guarded by deterministic keyword inference but is a known
  edge worth a test.

### Follow-up work

- Add a regeneration recipe (script or Make/PowerShell target) that seeds the
  pinned snapshot and emits the distribution table + sample-answer table.
- Add a test for the planner-vs-facet `contract_type` edge (E2).
- Consider a `platform_testing` query-agent scenario set analogous to
  `extraction_eval` once the substrate is pinned.

## Open questions

*Must be resolved (and this section emptied) before Status moves to Accepted.*

1. Official snapshot parameters — proposed `--seed capstone-2026 --count 60`.
   Confirm the seed string and count.
2. Does `docs/query-agent-review-scope.md` include **sample Q&A with computed
   expected answers** (recommended; ~half a day to compute and verify), or only
   the scope boundary?
3. Script-generate the snapshot distribution + sample answers, or maintain them
   by hand for this milestone?
4. Build a query-agent eval harness now, or is the reviewer doc plus manual
   sample Q&A sufficient for this review?
5. Offer an optional pre-built DB snapshot (option 2) as a convenience alongside
   the regenerate path, or not?

## Appendix: reproduce-it recipe (draft)

From a clean clone, offline:

```
# 1. Setup (no dataset download on the default path — see ADR-0001)
scripts/setup-windows.ps1        # or setup-linux.sh / setup-mac.sh

# 2. Bootstrap the org and seed the pinned portfolio
scripts/run-all.ps1 -Bootstrap
uv run python synthetic_data_loader/seed_contracts.py --seed capstone-2026 --count 60

# 3. Ask the query agent
scripts/agent.ps1 ask "How many active vendor agreements do we have?"
```

Expected snapshot distribution and sample answers: **TBD pending open question 1**.

Sample review questions (answers filled once the snapshot is pinned):

| Question | Exercises |
|---|---|
| How many contracts are in the portfolio, by lifecycle status? | `count_contracts` + `group_by` |
| How many active vendor agreements? | filter + count |
| Which contracts expire in the next 90 days? | relative-date filter, complete enumeration |
| Total value of active contracts? | `aggregate_contracts` sum, tool-computed |
| Average contract value by contract type? | `aggregate_contracts` + `group_by` |
| Which contracts require liability insurance? | `find_contracts` full-text enumeration |
| What are our payment obligations across all contracts? | `find_contracts` + interpret |
| Show the termination clause for the largest contract by value | `search_clauses`, single-contract detail |

## References

- [ADR-0001](0001-offline-first-contract-data-and-type-catalog.md)
- [Isolation Strategy](../isolation-strategy.md)
- [Query Agent](../../agents/query_agent/README.md)
- [Platform Testing](../../platform_testing/README.md)
- [Memory and Reasoning](../memory-and-reasoning.md)
