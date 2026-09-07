# Design Principles

Core values guiding the architecture and implementation.

| Principle | Implementation | Consequence |
|-----------|-----------------|-------------|
| **Strict Boundaries** | Agents → MCP → App is a one-way valve. Never App → Agents. MCP servers enforce domain invariants and tenant authorization before any write. | Faults isolate (broken agent doesn't corrupt data). Security is layered (database boundaries + MCP validation). Evolution is independent (each stack can change without breaking the other). |
| **Deterministic Control** | Python owns orchestration: state management, retry logic, auth. Every LLM call is schema-constrained, timeboxed (5 min default), and logged with full fidelity for debugging. | No magical LLM behavior (predictable, repeatable runs). Failures are auditable (you see exactly what the agent tried and why). Humans remain in control (long-running extraction can be interrupted). |
| **Local-First** | SQLite + blob store for all state. Optional LLM providers (Ollama local, Anthropic cloud, OpenRouter with API key). No external dependencies for control flow (scheduling, state, orchestration). | Works offline or in restricted networks. Debugging is transparent (data is always locally inspectable). Deployment doesn't require additional infrastructure. |
| **Per-Document Isolation** | Working memory is local to one extraction run. Never shared between documents or tenants. Discarded after completion. | No data leakage between documents. No accumulating context bloat. Each run is a clean slate (predictable cost and behavior). |
| **Graceful Degradation** | Failed LLM steps don't block pipeline. Review failures still ingest. Query planning failures still answer. Fallback to prior behavior. | Partial data is better than no data (incomplete extraction still helps). System stays responsive (one LLM failure doesn't hang). Human reviewers see what went wrong. |

## Why These Principles

### Strict Boundaries
Contract data is sensitive. Tenants expect absolute isolation. A one-way dependency prevents accidental data leakage and makes security auditable. MCP servers are the enforcement gate: they know the auth context and can reject invalid operations before they reach the app.

### Deterministic Control
LLMs are probabilistic. But contract extraction must be repeatable and auditable. Python orchestration lets us retry failed steps, thread state across pages, and log every decision. A team can replay an extraction run and understand exactly what happened.

### Local-First
Cloud dependencies introduce latency and outages. SQLite is ACID, queryable, and backupable. Embedding LLM provider choice means agents can swap between Ollama (local), Anthropic (cloud), or OpenRouter (cloud with API key) without rewriting code. Debugging offline is critical for security-sensitive work.

### Per-Document Isolation
Working memory (extracted fields, reasoning threads, obligation notes) is transient. It's not meant to last beyond one document. Keeping it local to a run means:
- No cross-document context pollution (contract A's facts don't bias contract B)
- Predictable performance (memory doesn't grow unbounded)
- Clean audit trails (each document's reasoning is separate)

### Graceful Degradation
Contracts are high-stakes. A single LLM failure should not halt the entire pipeline. Incomplete extraction (some fields missing) is better than no extraction (document never ingested). Query planning failures should still return partial results. This design treats LLM reliability as inherently partial and builds a system that tolerates it.

## How This Shapes Code

- **No global state** — agent working memory is passed as LangGraph state, never stored in a module variable
- **Schema validation** — every MCP tool returns typed Pydantic models; LLM output is parsed and validated
- **Timeboxes** — LLM calls have hard timeouts; if a step hangs, it fails gracefully with fallback
- **Explicit tenant context** — every query carries the tenant ID; queries cannot leak across organizations
- **Separate test harnesses** — agent tests mock MCP; domain tests use real SQLite; no cross-stack mocking

## References

- [Isolation Strategy](isolation-strategy.md) - How boundaries are enforced
- [Component Architecture](../README.md#component-architecture) - What modules embody these principles
- [Memory and Reasoning](memory-and-reasoning.md) - How working memory reflects per-document isolation
