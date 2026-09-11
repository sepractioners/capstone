# Week 1 Hypothesis → Learnings & Architecture Decisions

## 🔍 Key Insights & Lessons Learned

1. **[Better Data Than Better Models](#insight-1-better-data-than-better-models)** — Training data quality > model size. Gemma4 + CUAD examples > larger models without grounding.

2. **[Structured Reasoning Scaffolds](#insight-2-structured-reasoning-scaffolds)** — System prompts: Goal → Sub-goals → Constraints → Conditions. Reduces hallucination and inconsistency - but live query-agent testing later found this isn't sufficient alone on a small model; see the note in Insight 2 below.

3. **[Agent Grounding: Plan → Prep → Pipeline](#insight-3-agent-grounding-plan--prep--pipeline)** — High-quality training data + semantic retrieval. CUAD dataset was the force multiplier.

4. **[Local-First Architecture](#pivots-made)** — Docling + SQLite + Ollama > AWS Textract + S3. Faster iteration, no API setup, data stays local.

5. **[Observability as Foundation](#pivots-made)** — Execution traces required. Admin Console became core feature.

6. **[Focus on Core Intelligence](#pivots-made)** — Extract + Query first. Deferred calendars/alerts.

---

## 📋 Original Hypothesis (Week 1)

**Problem**: Manual contract analysis across obligations, renewal dates, SLA terms, risks is time-intensive and error-prone.

**Proposed Solution**: 
- 6 parallel agents: extraction, SLA alerts, renewal sync, risk classification, natural language query, calendar events
- Infrastructure: AWS Textract, S3, Outlook MCP, OCR services

---

## 📊 Results vs. Hypothesis

| Goal | Hypothesis | Reality | Status |
|------|-----------|---------|--------|
| Extract obligations | ✅ | ✅ Works with RAG | Validated |
| Query contracts naturally | ✅ | ✅ Works with embeddings + RAG | Validated |
| Identify risks | ✅ | ⚠️ Extracts; no severity calibration | Partial |
| Extract SLA terms | ✅ | ⚠️ Extracts; no alerts | Partial |
| Renewal date sync | ✅ | ❌ Deferred | Deferred |
| Automated alerts | ✅ | ❌ Deferred | Deferred |
| Citation-backed answers | ✅ | ✅ Works | Validated |
| Full lifecycle UI | Not planned | ✅ Built | Exceeded |
| Multi-provider LLM | Not planned | ✅ Built | Exceeded |
| Agent observability | Not planned | ✅ Built | Exceeded |

---

## 🔄 Key Pivots

### Pivot 1: Infrastructure → Local-First
**Was**: AWS Textract + S3 + Outlook
**Now**: Docling + SQLite + Ollama (deferred Outlook)
**Why**: Faster iteration without cloud setup; data private; Docling equals Textract quality

### Pivot 2: 6 Agents → Extract + Query First
**Was**: 6 parallel agents from day 1
**Now**: Focus on extraction + query; defer calendar/alerts
**Why**: Extraction is foundational; query is highest-value. Calendar is infrastructure, not core intelligence.

### Pivot 3: Observability Optional → Foundational
**Was**: Not explicitly planned
**Now**: Full execution traces + Admin Console from day 1
**Why**: Multi-step extraction requires visibility; essential for debugging and validation

### Pivot 4: Portal Afterthought → Early Build
**Was**: CLI primary, UI secondary
**Now**: Portal is primary; CLI for automation
**Why**: Domain experts need UI context; can't validate extraction results without seeing them in contracts

---

## 💡 Insight 1: Better Data Than Better Models

### The Finding

Gemma4 (7B) + CUAD examples > GPT-3.5 without grounding. Quality of training data > model size.

### Why

LLMs require examples to extract consistently. Providing similar clauses improves output reliability more than increasing model capacity.

### Implication for v2

Build better ingestion pipelines. Don't chase larger models.

### Evidence in Capstone

- Extraction agent uses Gemma4
- Query agent retrieves examples before synthesizing
- Setup builds CUAD index during initialization
- Both prioritize: "retrieve examples" over "use rules"

---

## 💡 Insight 2: Structured Reasoning Scaffolds

> **Naming correction, added later.** This was originally called "Structured
> Cognitive Loops." The pattern below is a fixed structure for *one* prompt,
> applied once - not an iterative loop (a real loop would be perceive → act →
> observe → repeat). Renamed to avoid confusing it with the query agent's
> actual loops (a cross-turn clarification loop, and two bounded in-request
> self-correction loops), which are a different, separate concept - see
> [ADR-0006](docs/adr/0006-query-agent-routing-retrieval-and-self-correction.md).
> Also found empirically once this pattern was live-tested on a small model:
> explicit constraints reduce but do not eliminate hallucination on their own
> - see [MCP_HEURISTICS.md Pattern 6](MCP_HEURISTICS.md#pattern-6-structured-reasoning-scaffolds)
> for the concrete evidence and what to pair the scaffold with.

### Current Agent Gaps (That Motivated This)

**Query Agent**:
- Answers outside contract scope (hallucinates)
- Doesn't separate "in contract" vs. "inferred"
- Returns vague sources
- No escalation when evidence weak

**Extraction Agent**:
- Inconsistent across similar clauses
- Doesn't retry on suspicious output (empty on non-empty page)
- Ambiguous extractions not flagged
- No confidence signals

**Root Cause**: System prompts define goals but lack explicit constraints, trade-offs, and failure conditions.

### The Pattern: Goal → Sub-goals → Constraints → Conditions

#### Extraction Agent (Structured)

```
Goal: Extract structured contract data with high accuracy

Sub-goals:
1. Identify clause type
2. Extract parties (who is responsible?)
3. Extract action (what must be done?)
4. Extract deadline/condition
5. Generate confidence score

Constraints:
- Extract only from contract text (no inference)
- All parties must be signatories
- Obligation action must use definitive verbs
- Flag ambiguous deadlines with both interpretations

Trade-offs:
- Prefer accuracy over completeness
- Never guess; flag uncertainty for human review

Retry conditions:
- Empty extraction on non-empty page → retry with 2x chunk
- Ambiguous party → retry with full contract context
- Confidence <70% → retry with RAG examples

Escalate conditions:
- Confidence <50% after 2 retries → flag for human
- Party not in signatories → flag for clarification
- Schema validation fails → return partial with error
```

#### Query Agent (Structured)

*The Week 1 sketch below is the original illustration of the pattern, kept
for history - it predates the actual routing design (a catalogue of twelve
prompt templates, not one generic RAG flow). For what's actually implemented,
see [`docs/query-agent-prompt-templates.md`](docs/query-agent-prompt-templates.md)
and [ADR-0006](docs/adr/0006-query-agent-routing-retrieval-and-self-correction.md).*

```
Goal: Answer questions grounded in contract evidence

Sub-goals:
1. Retrieve relevant clauses via RAG
2. Evaluate relevance of retrieved clauses
3. Synthesize answer from clauses
4. Generate source citations
5. Evaluate confidence

Constraints:
- Answer must cite actual contract text
- Separate facts (in contract) from implications (inferred)
- Every claim must reference source location
- Use exact contract language when quoting

Trade-offs:
- Prefer relevant grounded answers over complete guesses
- "Not in contract" > hallucination

Escalate conditions:
- No relevant clauses found → "Not covered in contract"
- Retrieved clauses match <50% → escalate as "ambiguous question"
- Answer requires inference → flag: "Not stated; inferred from..."
- Multiple contradictory clauses → return all with confidence scores

Scope boundaries:
- IN: Terms, obligations, dates, conditions explicitly stated
- OUT: Industry practices, regulatory requirements, what "should" be there
- Out-of-scope response: "Not addressed. In-scope topics: [list]"
```

### Why This Works

**Without structure**: Hallucination, inconsistency, silent failures
**With structure**: Predictable behavior, explicit failure modes, debuggable decisions

### v2 Blueprint

Same pattern for SLA extraction, risk classification, obligation verification:
1. Define goal → break into sub-goals
2. For each sub-goal: what counts vs. doesn't count (constraints)
3. Define trade-offs: accuracy vs. completeness? speed vs. correctness?
4. Set conditions: when retry? when escalate? when fail gracefully?

---

## 💡 Insight 3: Agent Grounding: Plan → Prep → Pipeline

### Three Pillars

#### 1. Planning: What Examples Does the Agent Need?
- Extraction agent needs: examples of good obligations
- Query agent needs: examples of relevant clauses for different question types
- Without examples, agents don't extract or query reliably

#### 2. Data Preparation: Quality Matters (80% of Grounding)
CUAD preprocessing required:
- Chunk contracts into logical sections
- Generate embeddings for semantic search
- Map obligations to structured JSON as examples
- Filter for quality

Data quality > model size.

#### 3. Ingestion Pipeline: Convert Raw Data to Searchable Training Signal
1. Download contracts (setup-*.sh)
2. Parse and chunk (extraction_agent/import_rag_dataset.py)
3. Generate embeddings (build_rag_index.py)
4. Store in SQLite with vector indices
5. Retrieve during agent runs (<100ms lookup)

### v2 Application: Risk Classification Agent

1. **Plan**: Collect examples of "High risk", "Medium risk", "Low risk" clauses
2. **Prep**: Hand-label 50-100 clauses from CUAD or client contracts
3. **Build**: Index by risk level + industry type
4. **Result**: Agent retrieves risk precedents → consistent scoring

### Architecture: Two SQLite Databases

- **capstone.db**: Domain data (contracts, obligations, metadata)
- **rag_knowledge.sqlite3**: Training signal (embeddings, examples)

Separation intentional: domain data evolves with user work; training data improves agent quality.

---

## 🏗️ Architecture Decisions

### 1. Local-First Default
- Ollama (local LLM) not cloud APIs
- Developers test without API keys; data stays local; fast iteration
- Easy switch to OpenRouter/Claude/GPT-4 via `.env`

### 2. MCP as Domain Boundary
- Agents communicate with domain via strict MCP servers
- Clean separation: agents (intelligence) vs. domain (contracts)
- Structure:
  - `extraction_mcp_server` (write): agents → domain
  - `query_mcp_server` (read): agents ← contract evidence
  - `clm_mcp_server` (admin): system → domain

### 3. RAG Pipeline for Consistency
- Provide LLM with similar examples during extraction
- Build Nomic embeddings index during setup
- During extraction: retrieve similar clauses + pass as context
- Result: Extraction quality improves; faster convergence

### 4. SQLite + Vector Search
- Self-contained; no external database
- Vector search built-in; easy to backup/reset
- Limitation: not for 100M+ contracts (MVP sufficient)
- Path: migrate to Postgres + pgvector later

### 5. Multi-Provider LLM Support
- Support Ollama, OpenRouter, Anthropic, OpenAI from day 1
- Single `.env` config switches providers
- Result: Team uses local dev, cloud testing, CLI uses configured provider

### 6. Per-Page Extraction with Memory
- Split PDF into pages
- Extract per page with accumulated facts
- Retry if extraction looks suspicious
- Handles 100+ page contracts; prevents context loss

### 7. Retrieval-Augmented Generation (Query)
- User question → convert to embeddings
- SQLite search → top 5 relevant clauses
- LLM synthesizes from clauses
- Include source references
- Result: Trustworthy answers; users can verify

---

## ⏸️ Deferred (And Why)

| Feature | Status | Reason | When |
|---------|--------|--------|------|
| Calendar sync | Deferred | Infrastructure dependency; low MVP ROI | v2 |
| SLA alerts | Deferred | Extraction works; alert logic separate concern | v2 |
| Risk severity feedback | Deferred | Requires human-in-loop calibration | v2 |
| AWS Textract | Not pursued | Docling sufficient | Later |
| S3 storage | Not pursued | SQLite sufficient; local-first | Migration path exists |
| Outlook MCP | Not pursued | Calendar sync deferred | v2 |
| Portal: Contract-scoped queries | Known issue | Needs UI redesign; CLI workaround exists (`--contract-id`) | Next UI iteration |

---

## 🎯 Validation & Next Steps

### What Was Right (70%)
- Core hypothesis: Extract + Query with RAG works
- Agent logic: Structured prompts + examples + escalation
- Domain model: Clear contracts/obligations enables reasoning
- Local-first approach: Faster than cloud-first

### What Was Wrong (30%)
- Thought infrastructure mattered early; it doesn't
- Underestimated observability importance
- Underestimated UI importance (built late)
- Overestimated calendar sync urgency

### v2 Roadmap (Using Learnings)

1. **Build next agent using cognitive loop structure** (Goal → Sub-goals → Constraints → Conditions)
2. **Invest in training data quality** (Plan → Prep → Pipeline)
3. **Use RAG to provide examples** (improve agent consistency)
4. **Structure system prompts explicitly** (prevent hallucination, enable debugging)
5. **Build observability in from day 1** (traces, reasoning, escalation)

Result: Predictable, debuggable, trustworthy agents.
