# Isolation Strategy

The platform enforces strict architectural boundaries to ensure the **agentic system** and **domain system** operate independently.

## One-Way Boundary

```
Agents (LangGraph + Knowledge)
    ↓ can ONLY call
MCP Boundary (strict enforcement)
    ↓ can ONLY write/read
App Stack (Domain-Driven Design)
    ↓ owns
SQLite Database
```

The MCP boundary is a one-way valve: agents can invoke MCP tools, but the app stack has no knowledge agents exist and cannot call back into the agentic system.

## Isolation Rules

### 1. No Circular Dependencies
- `agents/` directory **never** imports from `app/`
- App stack is completely unaware the agentic system exists
- This allows independent testing and deployment

### 2. MCP-Only Communication
- Agents invoke **only** LLM tools implemented through MCP servers
- MCP servers (`mcp/extraction_mcp/`, `mcp/query_mcp/`) enforce domain invariants
- MCP enforces schema constraints and tenant isolation before any data reaches the app

### 3. Agent Stack Owns Its Abstractions
- `agent_llm` (provider abstraction: Anthropic, Ollama, etc.) is part of the agent stack
- `agent_trace` (step-by-step LLM call logging) is part of the agent stack
- Neither is shared with or depends on the app stack
- Agents can evolve LLM providers independently

### 4. Truly Shared Libraries Only
- Both stacks can use `tools/contract_calc` (deterministic date/money math, no domain logic)
- Any shared tool must be:
  - Purely deterministic (no I/O, no state)
  - Domain-neutral (no contract concepts)
  - Independently testable

### 5. Independent Testing
- **Domain logic**: tested without any agent code, without LangGraph, without MCP
- **Agents**: tested with mock MCP servers (no real app/database)
- **Integration**: tested end-to-end with running services
- Both can fail independently without cascading

### 6. Tenant Isolation Enforced at MCP
- Every MCP tool checks `contract_tenants` foreign key before allowing operation
- App stack never sees cross-tenant data
- A malicious agent cannot bypass tenant scoping via MCP

## Communication Pattern

### Extraction Flow

```
Web Portal / CLI
    ↓ (HTTP to Agent Orchestrator)
Agent Orchestrator
    ↓ (LangGraph state machine)
Extraction Agent
    ↓ (tool calls via MCP)
Extraction MCP Server
    ↓ (validates tenant, enforces schema)
Application Services
    ↓ (domain logic, cascades)
SQLite Database (Domain Store)
```

### Query Flow

```
Web Portal / CLI
    ↓ (HTTP to Agent Orchestrator)
Agent Orchestrator
    ↓ (LangGraph state machine)
Query Agent
    ↓ (tool calls via MCP)
Query MCP Server
    ↓ (enforces tenant read scope, validates authorization)
Application Services (read-only queries)
    ↓
SQLite Database (reads only authorized tenant data)
    ↓
Query Agent (interprets results)
    ↓
Portal
```

## Why This Matters

### Fault Isolation
- A broken extraction agent doesn't corrupt the domain database
- An LLM provider outage doesn't crash the app stack
- A bug in agent orchestration doesn't affect contract queries

### Security
- Agents cannot directly access database; must go through MCP
- MCP validates every operation against authorization rules
- Tenant boundaries are enforced at the data layer, not just the API layer

### Maintainability
- Agent logic can be refactored without touching domain code
- Domain invariants are enforced in one place (MCP + application services)
- Changes to LLM provider, tracing, or memory don't affect the app

### Testing
- Unit tests of domain logic run in milliseconds (no agent code)
- Agent tests use mock MCP and don't depend on app implementation
- Integration tests verify MCP contract and tenant enforcement

## References

- [Component Architecture](../README.md#component-architecture) - Structural overview
- [Agentic Solution Architecture](agentic-architecture.md) - How agents use this boundary
- [Design Principles](design-principles.md) - Core values behind the isolation
