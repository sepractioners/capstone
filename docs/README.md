# Documentation Index

Cross-module documentation is organized here by purpose. Module-specific documentation remains beside the source code it describes (e.g., `agents/query_agent/docs/`, `agents/extraction_agent/docs/`).

## Architecture & Design

**Core System Design**
- [Repository Overview](../README.md) - Quick start, key learnings, and component architecture
- [Isolation Strategy](architecture/isolation-strategy.md) - Agent/app boundary enforcement and communication patterns
- [Design Principles](architecture/design-principles.md) - Core values guiding architecture
- [Agentic Solution Architecture](architecture/agentic-architecture.md) - Three agents, orchestration, memory model, and guardrails
- [Data Lifecycle](architecture/data-lifecycle.md) - How contract data flows through the system
- [Memory and Reasoning](architecture/memory-and-reasoning.md) - Working, episodic, and semantic memory models
- [System Map Legacy](architecture/system-map-legacy.md) - Original combined architecture diagram (historical reference)

## Decision Records (ADR)

- [Architecture Decision Records Index](adr/README.md) - Significant architectural decisions, their context and consequences
- [ADR-0001](adr/0001-offline-first-contract-data-and-type-catalog.md) — Offline-first contract data and a single contract-type catalog
- [ADR-0002](adr/0002-query-agent-evaluation-substrate.md) — Bounded evaluation substrate for the query agent
- [ADR-0003](adr/0003-query-agent-stress-corpus.md) — Pre-built stress corpus for query-agent validation
- [ADR-0006](adr/0006-query-agent-routing-retrieval-and-self-correction.md) — Query-agent routing, retrieval, and bounded self-correction (supersedes ADR-0004 and ADR-0005)
- [Implementation Plan](adr/implementation-plan.md) — Phased rollout of query-agent routing overhaul

## Research & Hypotheses

- [Hypothesis and Learnings](hypotheses/hypothesis-and-learnings.md) — Week 1 pivots, architecture decisions, and validated insights
- [MCP Heuristics & Patterns](hypotheses/mcp-heuristics.md) — MCP server specifications, prompt patterns, and evidence-backed design patterns
- [Agent Hypotheses](hypotheses/agent-hypotheses.md) — Active hypotheses, validated heuristics, and testing cadence

## Query Agent — Routing, Templates, and Validation

**Specification & Design**
- [Prompt Templates](../agents/query_agent/docs/prompt-templates.md) — The T1-T12 routing spec each question is matched against
- [Quick Tour](../agents/query_agent/docs/quick-tour.md) — One real question per template, run end-to-end through the production CLI with literal captured output

**Validation & Analysis**
- [Benchmark](../agents/query_agent/docs/benchmark.md) · [Benchmark Questions](../agents/query_agent/docs/benchmark-questions.md) — The committed question set, expected answers, and scoring
- [Small-Model Analysis](../agents/query_agent/docs/small-model-analysis.md) — Historical analysis (superseded by ADR-0006)

## Setup & Operations

- [Setup & Installation](setup/setup.md) — Detailed setup instructions and troubleshooting
- [Seeding & Validation Data](setup/seeding.md) — How to populate the database with sample contracts
- [Demo & Walkthrough](setup/demo.md) — Platform walkthrough with screenshots
- [Dependency Analysis](setup/dependency-analysis.md) — Project dependency audit and graphs
- [Dependency Management](setup/dependency-management.md) — Strategies and tooling for managing dependencies

## Domain and Implementation

- [Contract Lifecycle DDD](../app/contract-lifecycle-ddd.md) - Domain model and invariants
- [Application and Domain](../app/README.md) - Application services and infrastructure
- [MCP Servers](../mcp/README.md) - Extraction and Query MCP boundaries
- [Agents Overview](../agents/README.md) - Agent orchestration and implementation

## Module Documentation

- [Extraction Agent](../agents/extraction_agent/README.md)
- [Query Agent](../agents/query_agent/README.md)
- [Web Portal](../web/README.md)
- [Agent CLI](../tools/clm_agent_cli/README.md)
- [Platform Testing](../platform_testing/README.md)
- [Synthetic Data Loader](../synthetic_data_loader/README.md)
