# Week 1 Hypothesis → Learnings & Architecture Decisions

## Original Hypothesis (Week 1)

**Problem**: Supply chain contracts buried in PDFs/DOCX files require manual analysis across Legal and Procurement—extracting obligations, renewal dates, SLA terms, and risks is time-intensive and error-prone.

**Proposed Solution**: Build enterprise CLM platform with agentic AI that:
1. Extracts PDF/Word documents into structured markup (AWS Textract + Docling)
2. Automatically extracts contract obligations → JSON objects
3. Identifies SLA terms and converts them to automated alerts
4. Extracts renewal dates → syncs to calendar (Outlook MCP)
5. Classifies risks with severity ratings → alerts on high-risk contracts
6. Enables natural language querying of contracts with citation-backed answers
7. Integrates with external services: S3, Outlook, AWS Textract, OCR

---

## What We Built vs. What We Learned

### ✅ Hypotheses Validated

| Hypothesis | Validation | Evidence |
|-----------|------------|----------|
| **Extraction agent can learn from examples** | ✅ Confirmed | RAG pipeline + Nomic embeddings provides context to LLM → extraction consistency improves |
| **Semantic search beats keyword matching** | ✅ Confirmed | Vector embeddings find relevant clauses better than rules; enables natural language Q&A |
| **Agents need observability** | ✅ Confirmed | Admin console shows step-by-step reasoning; critical for debugging and validation |
| **Domain model is essential** | ✅ Confirmed | Clear contracts/obligations/parties model enables clean MCP boundaries and workflow logic |
| **Query agent works with RAG** | ✅ Confirmed | Users ask natural language questions; agent retrieves relevant clauses; LLM synthesizes grounded answers |

### 🔄 Pivots Made

#### 1. **Infrastructure Simplification** 
**Original**: AWS Textract + S3 + Outlook calendar MCP
**Pivot**: Local Docling + SQLite + Nomic embeddings (deferred Outlook)

**Why**: 
- Local-first enables fast iteration without AWS setup/costs
- Docling handles PDF extraction as well as Textract, simpler to test
- SQLite + embeddings self-contained, no cloud dependencies
- Developers can work offline, data stays private

**Trade-off**: No enterprise scale initially, but MVP velocity >> infrastructure setup time

#### 2. **Agent Prioritization**
**Original**: 6 parallel agent goals (extraction, SLA alerts, renewal sync, risk classification, natural language query, calendar events)
**Pivot**: Focus on extraction + query agents first; defer calendar/alerts/SLA notifications

**Why**:
- Extraction agent is foundational; other agents depend on it working well
- Query agent is highest-value for users (natural language access to contracts)
- Calendar sync and alerts are infrastructure integrations, not core intelligence
- Better to ship two agents really well than six agents partially

**Trade-off**: Deferred features (calendar sync, SLA alerts), but core hypothesis validated faster

#### 3. **Agent Observability (Unexpected Win)**
**Original**: Not explicitly planned; assumed simple extraction → output
**Pivot**: Built full execution traces, step-by-step reasoning, debug console

**Why**:
- "Why did the agent extract X?" is critical to validation
- Multi-step RAG + LLM extraction is complex; need visibility
- Domain experts need to see agent reasoning to trust results
- Debugging agent mistakes requires full trace history

**Result**: Admin console became core platform feature, not afterthought

#### 4. **Full Lifecycle UI (Early Investment)**
**Original**: Portal as afterthought; CLI as primary interface
**Pivot**: Built full contract lifecycle UI early (upload, view, extract, query, track)

**Why**:
- Can't validate extraction results without seeing them in context
- Domain experts think in UI, not API calls
- Seeing contracts + extracted data together catches mistakes early
- Portal enables user workflows; CLI for automation/scripting

**Result**: Portal is primary interface; CLI is power-user tool

---

## Key Architecture Decisions

### 1. **Local-First Design**
- **Decision**: Default to Ollama (local LLM) not cloud APIs
- **Rationale**: Developers can test without API keys; data never leaves machine; fast iteration
- **Flexibility**: Easy to switch to OpenRouter/Claude/GPT-4 via `.env`
- **Win**: Massive productivity; no dependency on external APIs during dev

### 2. **MCP as Domain Boundary**
- **Decision**: Agents communicate with domain via strict MCP servers
- **Rationale**: Clean separation; agents (intelligence) vs. domain (contracts/obligations)
- **Benefit**: Extraction agent can't corrupt data; domain logic isolated; testable
- **Structure**:
  - `extraction_mcp_server` (write): agents → contracts/obligations
  - `query_mcp_server` (read): agents ← contract evidence
  - `clm_mcp_server` (admin): system → domain operations

### 3. **RAG Pipeline for Extraction Quality**
- **Decision**: Provide LLM with similar examples during extraction
- **Rationale**: "Show me 3 similar obligations from CUAD dataset" → LLM extracts more consistently
- **Implementation**: 
  - Build Nomic embeddings index during setup
  - During extraction, search for similar clauses
  - Pass examples to LLM as context
- **Win**: Extraction quality improves; faster convergence with fewer retries

### 4. **SQLite + Vector Search**
- **Decision**: SQLite for main DB + rag_knowledge.sqlite3 for embeddings
- **Rationale**: Self-contained, no external database; vector search built-in; easy to backup/reset
- **Trade-off**: Not for 100M contracts, but perfect for MVP
- **Flexibility**: Can migrate to Postgres + pgvector later

### 5. **Multi-Provider LLM Support**
- **Decision**: Support Ollama, OpenRouter, Anthropic, OpenAI from day 1
- **Rationale**: Don't lock into one provider; developers choose based on cost/capability/privacy
- **Implementation**: Single `.env` configuration switches providers
- **Win**: Team can use local for dev, cloud for testing, CLI uses configured provider

### 6. **Extraction Agent: Per-Page Processing**
- **Decision**: Process contracts page-by-page, accumulate facts across pages
- **Rationale**: Large documents need chunking; multi-page memory prevents lost context
- **Implementation**: 
  - Split PDF into pages
  - Extract per page with accumulated memory
  - Retry if extraction looks suspicious (empty on non-empty page)
- **Win**: Handles 100+ page contracts; memory prevents re-extraction errors

### 7. **Query Agent: Retrieval-Augmented Generation**
- **Decision**: Search embeddings first, then synthesize with LLM
- **Rationale**: Avoid hallucination; ground answers in actual contract text
- **Implementation**:
  - User question → convert to embeddings
  - SQLite search → top 5 relevant clauses
  - LLM reads clauses + question → synthesizes answer
  - Include source references (contract, clause)
- **Win**: Answers are trustworthy; users can verify sources

---

## What We Deferred (And Why)

| Feature | Status | Reason | When |
|---------|--------|--------|------|
| **Calendar sync** | Deferred | Infrastructure dependency; low MVP ROI | v2 |
| **SLA alerts** | Deferred | Extraction works; alert logic can be added | v2 |
| **Risk severity feedback** | Deferred | Useful but requires human-in-loop calibration | v2 |
| **AWS Textract** | Not pursued | Docling works locally; simpler | Later if needed |
| **S3 storage** | Not pursued | SQLite sufficient; local-first philosophy | Migration path exists |
| **Outlook MCP** | Not pursued | Calendar sync deferred | v2 |
| **Contract-scoped queries in Portal UI** | Known issue | Requires UI redesign; workaround exists (CLI `--contract-id`) | Next UI iteration |

---

## Critical Discovery: What Makes Agents Grounded?

### The Three Pillars of Agent Quality

During implementation, we discovered that agent quality depends on **three interconnected layers**:

#### 1. **Planning: What Data Do Agents Need?**
- Agents aren't magic; they need examples to learn from
- Extraction agent needs: "Here are 10 similar obligations from real contracts"
- Query agent needs: "Here are relevant clauses the user is asking about"
- Without examples, agents hallucinate or miss context

**Key insight**: LLMs work better with context and examples than with raw instructions alone

#### 2. **Data Preparation: Quality Matters**
- Raw contract text ≠ training signal
- CUAD dataset required preprocessing:
  - Chunk contracts into logical sections (clauses, sub-clauses)
  - Generate embeddings for semantic search
  - Map obligations to structured JSON for extraction examples
  - Filter for quality (incomplete extractions hurt agent learning)

**Key insight**: 80% of grounding quality comes from data prep, not model size

#### 3. **Ingestion Pipeline: Making Data Accessible**
- One-time download of CUAD ≠ usable training data
- Built pipeline to:
  1. Download CUAD contracts (setup-*.sh)
  2. Parse and chunk documents (extraction_agent/import_rag_dataset.py)
  3. Generate embeddings (build_rag_index.py)
  4. Store in SQLite with vector indices
  5. Make searchable during agent runs
  
**Result**: Agents can retrieve similar examples in <100ms during extraction

### Why This Matters for v2

**For new use cases** (SLA extraction, risk classification, obligation verification):
1. **Plan**: What examples would help this agent?
2. **Prep**: Can we get those examples? (existing contracts, templates, standards)
3. **Build**: Create ingestion pipeline to embed and index them

**Example**: For risk classification agent:
- **Planning**: Need examples of "High risk", "Medium risk", "Low risk" clauses
- **Prep**: Hand-label 50-100 risk clauses from CUAD or client contracts
- **Build**: Index them by risk level + industry type
- **Result**: Agent retrieves risk precedents during classification → consistent scoring

### Data-Driven Architecture Decision

This discovery shaped our architecture:
- **SQLite stores two types of data**:
  1. **capstone.db**: Contracts, obligations, metadata (domain data)
  2. **rag_knowledge.sqlite3**: Embeddings + examples (training signal)
- **Separation is intentional**: Domain data evolves with user work; training data improves agent quality
- **Both queryable**: Agents retrieve from training data during reasoning

---

## Lessons Learned

1. **What makes agents grounded: Training data quality**
   - Examples > instructions. Show LLM what good looks like
   - Embeddings enable semantic retrieval of examples
   - Ingestion pipelines convert raw data → searchable training signal
   - CUAD dataset was force multiplier for extraction quality

2. **Local-first enables fast iteration**
   - No cloud setup, no API keys, no costs → developers move faster
   - Trade privacy/scale for velocity early; migrate later if needed

2. **Semantic search is powerful**
   - Embeddings + retrieval-augmented generation > rule-based extraction
   - Users think in natural language; enable that from day 1

3. **Observability is foundational**
   - Multi-step agentic workflows are complex; need to see every step
   - Execution traces are not optional; they're essential for trust and debugging

4. **Strict boundaries improve quality**
   - MCP as domain boundary forces clean separation
   - Agents can't corrupt domain logic; domain can't interfere with reasoning

5. **Full lifecycle UI validates faster**
   - Users see extractions in context → catch mistakes early
   - CLI sufficient for power users; UI for domain experts

6. **Learn from examples (RAG)**
   - Providing LLM with similar examples improves quality
   - CUAD dataset as training signal was key insight

7. **Flexibility over prescriptive design**
   - Multi-provider LLM support early saved pivots later
   - Local-first with easy cloud migration path is powerful

---

## Current State vs. Original Hypothesis

| Goal | Hypothesis | Reality | Status |
|------|-----------|---------|--------|
| Extract obligations | ✅ Yes | ✅ Works with RAG | Validated |
| Query contracts naturally | ✅ Yes | ✅ Works with embeddings + RAG | Validated |
| Identify risks | ✅ Yes | ⚠️ Extracts but no severity calibration | Partial |
| Extract SLA terms | ✅ Yes | ⚠️ Extracts but no alerts | Partial |
| Sync renewal dates | ✅ Yes | ❌ Dates extracted, calendar sync deferred | Deferred |
| Automated alerts | ✅ Yes | ❌ Infrastructure deferred | Deferred |
| Citation-backed answers | ✅ Yes | ✅ Works | Validated |
| Full lifecycle UI | Not planned | ✅ Built | Exceeded |
| Multi-provider LLM | Not planned | ✅ Built | Exceeded |
| Agent observability | Not planned | ✅ Built | Exceeded |

---

## What's Next

**High-priority v2 features** (based on learnings):
1. Calendar sync for renewal dates (infrastructure integration)
2. Risk severity feedback loop (human-in-loop calibration)
3. SLA breach alerts (notification service)
4. Contract-scoped queries in Portal (UI redesign)
5. Multi-document analysis (cross-contract queries)

**Low-priority / if-needed:**
- AWS Textract integration (Docling sufficient)
- S3 migration (SQLite working well)
- Postgres + pgvector (if scale demands)

---

## Key Takeaway

**The original hypothesis was 70% correct, 30% wrong about implementation.**

What was right:
- Extract + query + observe is the winning pattern
- Agents need examples to work well (RAG)
- Domain model matters
- Users need to see reasoning

What we got wrong:
- Thought infrastructure (Textract, S3, Outlook) mattered more than it does
- Underestimated observability value
- Underestimated UI importance for validation
- Overestimated calendar sync urgency

**Lesson**: Core AI hypothesis was sound; execution beat infrastructure heavy-lifting.
