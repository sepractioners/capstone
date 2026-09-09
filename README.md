# AI-Powered Contract Intelligence

Upload contracts. Get instant insights.

An intelligent contract platform that uses AI agents to automatically **extract obligations**, **identify risks**, and **answer questions** about your contracts. No manual review. No spreadsheets.

**What you can do:**
- 📄 **Extract automatically**: Upload PDFs → AI extracts clauses, obligations, dates, renewal deadlines
- 💬 **Query with AI**: Ask "Which contracts expire this quarter?" → get instant answers
- 🔍 **Semantic search**: Find similar clauses across your entire contract library
- 📊 **Track obligations**: Automatically capture what each party owes, payment terms, renewal dates
- 🛡️ **Identify risks**: Flag missing terms, unusual provisions, compliance gaps

**How it works:** AI agents read contracts using Gemma4 (local LLM), retrieve similar examples from a CUAD knowledge base via semantic search, and store results in SQLite. Access via web portal, CLI, or REST API. Local-first by default (Ollama); switch to cloud LLMs (Claude, GPT-4) anytime.

---

## 🎓 Key Learnings

**Why this architecture?** See [HYPOTHESIS_AND_LEARNINGS.md](HYPOTHESIS_AND_LEARNINGS.md) for the full story. Key insights:

1. **Data quality > model size** — Gemma4 + CUAD examples > larger models without grounding
2. **Structured prompts prevent hallucination** — Goal → Sub-goals → Constraints → Escalate conditions
3. **Grounding requires: Plan → Prep → Pipeline** — Examples → structured data → fast retrieval
4. **Local-first wins** — Docling + SQLite + Ollama > AWS infrastructure (simpler, faster, private)
5. **Observability is foundational** — Execution traces essential for debugging agents

**Detailed MCP heuristics & prompt patterns:** [MCP_HEURISTICS.md](MCP_HEURISTICS.md)

**How agents evolve:** [AGENT_HYPOTHESES.md](AGENT_HYPOTHESES.md) — track hypotheses from test → validated heuristic → embedded in code

---

## 🚀 Quick Start

### 1. Setup (One Step)
The setup script handles everything: Python env, dependencies, HTTPS certs, database, .env config, sample data, and RAG index.

**macOS:** `bash scripts/setup-mac.sh`  
**Linux:** `bash scripts/setup-linux.sh`  
**Windows:** `.\scripts\setup-windows.ps1`

See `--help` for options (e.g., `--no-sample-data` to skip contracts).

### 2. Start Services
```bash
bash scripts/run-all.sh              # Start everything
bash scripts/run-all.sh --bootstrap  # First run: create admin account
bash scripts/run-all.sh --stop       # Stop everything
```

Logs in `.run/`. Syncs Python and Node dependencies by default.

### 3. Access the Platform

**Web Interfaces:**
- **Portal** (https://localhost:5173) — Upload contracts, chat with query agent, track obligations
- **Admin Console** (https://localhost:5174) — View agent execution traces, debug reasoning (admin only)
- **API** (https://localhost:8443) — Programmatic access, OpenAPI docs at `/docs`

**Login:** `admin@capstone.local` / `CapstoneAdmin!2026`

**CLI Tool:**
```bash
bash scripts/agent.sh ask "Which contracts expire this quarter?"
bash scripts/agent.sh task "Extract obligations" --file ./contract.pdf
bash scripts/agent.sh ask "Show clauses" --contract-id <uuid>  # Scope to one contract
bash scripts/agent.sh chat                                      # Interactive mode
```

---

## 🧠 The AI Agents

| Agent | Input | Process | Output | MCP |
|-------|-------|---------|--------|-----|
| **Extraction** | PDF file | Per-page LLM extraction + RAG examples | Clauses, obligations, dates, parties, risks | `extraction_mcp_server` (write) |
| **Query** | Question + history | Semantic search → LLM synthesis | Grounded answer + sources | `query_mcp_server` (read) |

**Extraction workflow:**
1. Split PDF into pages
2. Retrieve similar obligations from RAG index (CUAD examples)
3. LLM extracts using examples for consistency
4. Validate (retry if confidence <70%; escalate if <50% after retry)
5. Persist via MCP server

**Query workflow:**
1. Convert question to embeddings
2. Semantic search SQLite for relevant clauses
3. LLM synthesizes answer grounded in results
4. Return with source citations

---

## ⚙️ Configuration

**LLM Providers** (edit `.env`):

| Provider | Default | Setup |
|----------|---------|-------|
| **Ollama** (local) | ✅ Gemma4 | `ollama serve` then `ollama pull gemma4:latest` |
| **OpenRouter** | — | Set `LLM_PROVIDER=openrouter` + `OPENROUTER_API_KEY` |
| **Claude (Anthropic)** | — | Set `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` |
| **GPT-4 (OpenAI)** | — | Set `LLM_PROVIDER=openai` + `OPENAI_API_KEY` |

**Agent Configuration** (in `.env`):
```bash
EXTRACTION_RAG_ENABLED=1              # Enable RAG for extraction
QUERY_PLAN_TOOLS=1                    # Enable query planning
PLANNER_MAX_STEPS=3                   # Max planning iterations
```

See [.env.example](.env.example) for all options.

---

## 📊 How It Works: Extraction & Query Pipelines

**Extraction Pipeline (Extract obligations, dates, parties):**
```
User uploads PDF
  → Gemma4 reads each page
  → Nomic embeddings search RAG: "Find similar obligations"
  → Gemma4 extracts using examples for consistency
  → Results stored in clm.sqlite3
```

**Query Pipeline (Answer questions about contracts):**
```
User asks: "Which contracts expire this quarter?"
  → Nomic embeddings convert question to vector
  → SQLite semantic search finds relevant clauses
  → Gemma4 synthesizes answer from retrieved clauses
  → Return with source citations
```

**Why this design:**
- Gemma4: Reasoning + extraction logic
- Nomic embeddings: Semantic search over contract text
- SQLite: Fast local storage with vector search
- RAG: Provides examples → extraction consistency
- Result: Answers grounded in actual contracts (no hallucination)

---

## 🗄️ Two SQLite Databases

- **clm.sqlite3** — Domain data (contracts, obligations, users, organizations)
- **rag_knowledge.sqlite3** — Training signal (embeddings of CUAD clauses for semantic search)

Separation intentional: domain data evolves with user work; training data improves agent quality.

---

## 📁 Project Structure

**Core Systems:**
- [app/](app/) — Contract domain, application services, SQLite infrastructure
- [mcp/](mcp/) — Write-capable Extraction MCP + read-only Query MCP (strict isolation boundary)
- [agents/](agents/) — Extraction and query agents
- [web/](web/) — FastAPI backend, React portal, admin console

**User Interfaces:**
- [tools/clm_agent_cli/](tools/clm_agent_cli/) — CLI tool for agents

**Utilities:**
- [tools/contract_calc/](tools/contract_calc/) — Date and money calculations
- [platform_testing/](platform_testing/) — Deterministic scenarios + evaluation
- [synthetic_data_loader/](synthetic_data_loader/) — CUAD dataset download + RAG indexing

**Documentation:**
- [docs/](docs/) — Architecture, design principles, memory model, data lifecycle

See individual READMEs in each module for details.

---

## 🔧 Testing

```bash
# Run deterministic platform scenarios
uv run python -m platform_testing.runner platform_testing/scenarios/clause_template_workflow.yaml

# Run all tests
uv run pytest

# Evaluate extraction accuracy
uv run python -m platform_testing.extraction_eval --limit 8
```

See [SETUP.md](SETUP.md) for troubleshooting.

---

## ⚠️ Known Issues

**Query agent scope in Portal**: When opened while viewing a contract, searches all tenant contracts instead of scoping to that contract.
- **Workaround (CLI)**: `bash scripts/agent.sh ask "Show clauses" --contract-id <uuid>` (works perfectly)
- **Workaround (Portal)**: Mention contract explicitly in query: "In contract ABC, show me..."

---

## 📚 Component Architecture

```mermaid
graph TB
    UI["🖥️ Portal, Admin Console, CLI"]
    API["🌐 FastAPI + Auth + Tenant Scoping"]
    Agents["🤖 Extraction & Query Agents"]
    MCP["🔒 MCP Boundary<br/>(Isolation Barrier)"]
    Domain["🏗️ Domain Model<br/>(Contracts, Obligations)"]
    RAG["🗄️ RAG Index<br/>(CUAD Embeddings)"]
    DB["🏛️ SQLite Databases<br/>(clm.sqlite3, rag_knowledge.sqlite3)"]
    
    UI → API
    API → Agents
    Agents →|only via MCP| Domain
    Agents →|retrieval| RAG
    Domain → DB
    RAG → DB
    
    style Agents fill:#fff3e0,stroke:#ff9800,stroke-width:3px
    style MCP fill:#ffcdd2,stroke:#d32f2f,stroke-width:3px
    style Domain fill:#f1f8e9,stroke:#388e3c,stroke-width:3px
```

**Key principle**: Agents communicate with domain only through MCP servers (strict isolation). This enables independent evolution and prevents architectural coupling.

**Architecture documentation:** [docs/](docs/) — isolation strategy, design principles, agentic architecture, data lifecycle, memory & reasoning.

---

## 📖 Full Documentation

- **[HYPOTHESIS_AND_LEARNINGS.md](HYPOTHESIS_AND_LEARNINGS.md)** — Week 1 learnings, pivots, architecture decisions
- **[MCP_HEURISTICS.md](MCP_HEURISTICS.md)** — MCP server specifications, heuristics, prompt patterns
- **[AGENT_HYPOTHESES.md](AGENT_HYPOTHESES.md)** — R&D roadmap: active hypotheses, validated heuristics, testing cadence
- **[DEMO.md](DEMO.md)** — Platform walkthrough with screenshots
- **[SETUP.md](SETUP.md)** — Detailed setup, troubleshooting, testing
- **[docs/](docs/)** — Architecture, design principles, memory model, data lifecycle

## Resources

- **Module READMEs**: [app/](app/README.md), [mcp/](mcp/README.md), [agents/](agents/README.md), [web/](web/README.md), [CLI](tools/clm_agent_cli/README.md)
- **Agent Architecture**: [Extraction](agents/extraction_agent/docs/architecture.md), [Query](agents/query_agent/docs/architecture.md)
- **Extraction Agent**: [README](agents/extraction_agent/README.md), [CUAD Scenario](agents/extraction_agent/docs/kaggle-cuad.md)
- **Domain Model**: [Contract Lifecycle DDD](app/contract-lifecycle-ddd.md)
