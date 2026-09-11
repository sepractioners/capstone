# Documentation

Cross-module documentation belongs here. Module-specific documentation remains beside the source it describes.

## Architecture

- [Repository Overview](../README.md) - Quick start and component architecture
- [Isolation Strategy](isolation-strategy.md) - Agent/app boundary enforcement and communication patterns
- [Design Principles](design-principles.md) - Core values guiding architecture
- [Agentic Solution Architecture](agentic-architecture.md) - Three agents, orchestration, memory model, and guardrails
- [Data Lifecycle](data-lifecycle.md) - How contract data flows through the system
- [Memory and Reasoning](memory-and-reasoning.md) - Working, episodic, and semantic memory models
- [System Map Legacy](system-map-legacy.md) - Original combined architecture diagram (historical reference)

## Decisions

- [Architecture Decision Records](adr/README.md) - Significant architectural decisions, their context and consequences
  - [ADR-0001](adr/0001-offline-first-contract-data-and-type-catalog.md) (Proposed) - Offline-first contract data and a single contract-type catalog
  - [ADR-0002](adr/0002-query-agent-evaluation-substrate.md) (Proposed) - Bounded evaluation substrate for the query agent
  - [ADR-0003](adr/0003-query-agent-stress-corpus.md) (Proposed) - Pre-built stress corpus for query-agent validation
  - [ADR-0006](adr/0006-query-agent-routing-retrieval-and-self-correction.md) (Proposed) - Query-agent routing, retrieval, and bounded self-correction - consolidates ADR-0004 and ADR-0005 (both retired, kept for history)

## Query Agent — Routing, Templates, and Validation

- [Prompt Templates](query-agent-prompt-templates.md) - The T1-T12 routing spec each question is matched against
- [Quick Tour](query-agent-quick-tour.md) - One real question per template, run end-to-end through the production CLI, with the literal captured answer
- [Benchmark](query-agent-benchmark.md) · [Benchmark Questions](query-agent-benchmark-questions.md) - The committed question set, expected answers, and scoring
- [Small-Model Analysis](query-agent-small-model-analysis.md) *(historical, superseded by ADR-0006)*

## Domain and Implementation

- [Contract Lifecycle DDD](../app/contract-lifecycle-ddd.md) - Domain model and invariants
- [Application and Domain](../app/README.md) - Application services and infrastructure
- [MCP Servers](../mcp/README.md) - Extraction and Query MCP boundaries
- [Agents Overview](../agents/README.md) - Agent orchestration and implementation

## Module Documentation

- [Extraction Agent Documentation](../agents/extraction_agent/README.md)
- [Query Agent Documentation](../agents/query_agent/README.md)
- [Web Portal Documentation](../web/README.md)
- [Agent CLI](../tools/clm_agent_cli/README.md)
- [Platform Testing Documentation](../platform_testing/README.md)
- [Synthetic Data Loader](../synthetic_data_loader/README.md)
