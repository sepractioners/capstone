# Architecture Decision Records

An ADR captures one significant architectural decision: the context that forced
it, the options considered, the choice made, and the consequences that follow.
ADRs are immutable once **Accepted** — a later decision that changes course gets
its own ADR and supersedes the earlier one.

## Format

We use [MADR](https://adr.github.io/madr/) (lightweight). Each record has:

- **Status** — Proposed · Accepted · Rejected · Superseded by [ADR-NNNN]
- **Context and problem statement**
- **Decision drivers**
- **Considered options**
- **Decision outcome** — the chosen option and why
- **Consequences** — good, bad, and follow-up work
- **Open questions** — only while Status is Proposed; must be empty before Accepted

## Naming

`NNNN-short-kebab-title.md`, zero-padded, sequential. Never renumber.

## Index

| ADR | Status | Title |
|---|---|---|
| [0001](0001-offline-first-contract-data-and-type-catalog.md) | Proposed | Offline-first contract data and a single contract-type catalog |
| [0002](0002-query-agent-evaluation-substrate.md) | Proposed | Bounded evaluation substrate for the query agent |
| [0003](0003-query-agent-stress-corpus.md) | Proposed | Pre-built stress corpus for query-agent validation |
| [0004](0004-query-agent-routing-and-retrieval.md) | Rejected → [0006](0006-query-agent-routing-retrieval-and-self-correction.md) | Spec-driven query-agent routing; retrieval stays in-process |
| [0005](0005-query-agent-self-correction-loops.md) | Rejected → [0006](0006-query-agent-routing-retrieval-and-self-correction.md) | Bounded in-request self-correction (replan-on-thin-gather, redraft-on-unsupported) |
| [0006](0006-query-agent-routing-retrieval-and-self-correction.md) | Proposed | Query-agent routing, retrieval, and bounded self-correction (consolidates 0004 + 0005) |
