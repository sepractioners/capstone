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
