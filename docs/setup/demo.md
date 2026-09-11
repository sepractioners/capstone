# Capstone CLM Platform Demo

Interactive walkthrough of the Contract Lifecycle Management platform, showing key features and agent interactions.

## 1. Login Portal

**URL:** https://localhost:5173

The login page presents the CLM branding and tenant-scoped access:

```
┌─────────────────────────────────────────────────┐
│                                                 │
│  CONTRACT OPERATIONS                            │
│                                                 │
│  Make every agreement                           │
│  easier to move forward.                        │
│                                                 │
│  Review extracted facts, create governed        │
│  drafts, and keep lifecycle decisions visible.  │
│                                                 │
│  ☑ Tenant-scoped access with bearer tokens     │
│                                                 │
│                    ┌─────────────────────┐     │
│                    │ CLM                 │     │
│                    │                     │     │
│                    │ Welcome back        │     │
│                    │                     │     │
│                    │ Email:              │     │
│                    │ [admin@capstone...] │     │
│                    │                     │     │
│                    │ Password:           │     │
│                    │ [***************]   │     │
│                    │                     │     │
│                    │  → Sign in          │     │
│                    └─────────────────────┘     │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Credentials:**
- Email: `admin@capstone.local`
- Password: `CapstoneAdmin!2026`

---

## 2. Portal Dashboard

**URL:** https://localhost:5173 (after login)

The contract workspace dashboard provides at-a-glance visibility into the contract portfolio:

```
┌─────────────────────────────────────────────────────────────┐
│ CLM                                                         │
│ Agent  Clause library  org_clm58a96655d380ca3cdb2c15c00  ⟶ │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ CONTRACT WORKSPACE                                          │
│                                                             │
│ Agreements, in motion.                   ┌─ Open agent     │
│                                           │ ┌─ Create draft │
│ Create governed drafts, upload            │ └─ Upload ⬇     │
│ extractions, and move agreements          │                 │
│ through review.                           └─────────────────┘
│                                                             │
│ ┌──────────────┬─────────────┬──────────────┐             │
│ │ 120          │ 9           │ 94           │             │
│ │ Visible      │ Needs       │ Active       │             │
│ │ contracts    │ review      │ contracts    │             │
│ └──────────────┴─────────────┴──────────────┘             │
│                                                             │
│ ─────────────────────────────────────────────────────      │
│                                                             │
│ Recent agreements                                           │
│ Select a contract to read clauses and manage workflow      │
│                                                             │
│ □ Coho Financial - First Line Retail Reseller Agreement   │
│                                                     Active ▶ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Metrics:**
- **120 visible contracts** - Total portfolio searchable and analyzable
- **9 needing review** - Contracts in draft or review status
- **94 active** - Signed contracts under management

**Actions Available:**
- 📤 **Upload contract** - Add PDFs for extraction and analysis
- ✏️ **Create draft** - Start a new governed contract template
- 🤖 **Open agent** - Launch the contract analysis agent

---

## 3. Contract Agent Workspace

**Location:** Modal panel in the portal (click "Open agent" button)

The agent workspace enables multi-turn conversations about contracts:

```
┌─────────────────────────────────────────────────┐
│ AGENT WORKSPACE                                 │
│                                                 │
│ Contract agent              [Thinking]  [New..] │
│                                                 │
│ Ask about your contracts or describe a task -  │
│ the agent plans and runs the steps.             │
│                                                 │
│ ────────────────────────────────────────────── │
│                                                 │
│ ┌─────────────────────────────────────────────┐│
│ │ ✓ Thinking                                  ││
│ │                                              ││
│ │ [User]: Which contracts need review and     ││
│ │         what are their key terms?            ││
│ │                                              ││
│ │ [Agent]: Processing query...                ││
│ │ - Retrieving contracts with review status   ││
│ │ - Analyzing key terms using RAG guidance    ││
│ │ - Synthesizing response...                  ││
│ │                                              ││
│ └─────────────────────────────────────────────┘│
│                                                 │
│ ┌──────────────────────────────────────────┐  │
│ │ Ask about your contracts, or describe... │ ⤴ │
│ └──────────────────────────────────────────┘  │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Agent Capabilities

The contract agent can:

1. **Answer Portfolio Questions**
   - "Which contracts need review?"
   - "What are the payment terms across all agreements?"
   - "Which contracts expire this quarter?"

2. **Analyze Contracts**
   - Extract key clauses, dates, and obligations
   - Identify unusual or missing terms
   - Compare contracts side-by-side

3. **Risk Assessment**
   - Flag contracts missing standard clauses
   - Identify unusual liability or indemnification terms
   - Highlight ambiguous language

4. **Multi-step Tasks**
   - Upload a contract → Extract clauses → Compare to templates
   - Identify all vendor agreements → Extract payment terms → Generate summary

### Agent Architecture

The agent uses:

- **Hybrid RAG**: CUAD contract examples + semantic vector search
- **LangGraph**: Multi-step reasoning with state machine orchestration
- **MCP Boundaries**: Safe, audited access to contract data via MCP servers
- **SSE Streaming**: Real-time response streaming to the browser
- **Knowledge Store**: Procedural templates and contract guidance

---

## 4. Admin Console

**URL:** https://localhost:5174

The admin observability console shows full traces of agent reasoning:

```
┌──────────────────────────────────────────────┐
│ CLM Admin Console                            │
├──────────────────────────────────────────────┤
│                                              │
│ Agent Traces                                 │
│                                              │
│ Task: "Which contracts need review?"         │
│ Status: ✓ Complete                          │
│ Duration: 2.3s                              │
│                                              │
│ Steps executed:                              │
│  1. Query parsing & intent detection        │
│  2. RAG retrieval (CUAD guidance)           │
│  3. Contract status query (database)        │
│  4. Response synthesis                      │
│                                              │
│ Memory snapshots:                            │
│  - Working memory (current task state)      │
│  - Episodic memory (query history)          │
│  - Semantic memory (learned patterns)       │
│                                              │
└──────────────────────────────────────────────┘
```

**Features:**
- Full execution traces of agent reasoning
- Memory snapshots at each step
- Performance metrics and latency breakdown
- Audit log for compliance

---

## 5. Workflow Example: Contract Upload & Extraction

### Step 1: Upload Contract
1. Click **"Upload contract"** button
2. Select PDF file (e.g., vendor agreement)
3. Portal sends to extraction agent via FastAPI

### Step 2: Agent Extraction
The extraction agent:
1. Receives PDF from web API
2. Calls **Extraction MCP** (write-capable boundary)
3. Extracts clauses using LLM + RAG guidance
4. Stores results in domain database

### Step 3: Query & Analysis
1. Ask agent: "What are the payment terms in this contract?"
2. Agent calls **Query MCP** (read-only boundary)
3. Retrieves extracted data from database
4. Synthesizes analysis with contract context
5. Returns cited response with evidence

### Step 4: Review & Action
1. User reviews extracted clauses
2. Creates draft amendments if needed
3. Routes contract to stakeholders for approval
4. Agent tracks status and sends reminders

---

## 6. Technical Stack Visible to User

When using the platform, you interact with:

| Component | What You See |
|-----------|--------------|
| **Frontend** | React portal at https://localhost:5173 |
| **API** | FastAPI backend (HTTPS at port 8443) |
| **Agent** | Chat interface with streaming responses |
| **Database** | Transparent - contracts and analysis results |
| **LLM** | Responses with reasoning (Ollama or cloud) |
| **RAG** | Context-aware answers from CUAD examples |

---

## 7. Running Your Own Workflows

### Example 1: Portfolio Analysis
```
User: "Summarize payment terms across our top 10 vendors"

Agent:
  1. Retrieves vendor contracts from database
  2. Extracts payment terms using NLP
  3. Groups by term type (Net 30, Net 60, etc.)
  4. Returns summary with outliers flagged
```

### Example 2: Clause Extraction
```
User: "Extract all indemnification clauses"

Agent:
  1. Queries contracts in database
  2. Applies extraction model with RAG guidance
  3. Returns structured clauses with sources
  4. Ready for review or import to templates
```

### Example 3: Compliance Check
```
User: "Do we have confidentiality clauses in all NDAs?"

Agent:
  1. Finds all NDA contracts
  2. Checks for confidentiality sections
  3. Reports missing or weak clauses
  4. Suggests standard language
```

---

## 8. Key Features Summary

✅ **Multi-tenant portal** - Tenant-scoped access with RBAC  
✅ **Real-time agent** - Streaming responses via SSE  
✅ **Local-first** - All processing stays on your infrastructure  
✅ **Hybrid RAG** - Knowledge from CUAD + semantic search  
✅ **Audit trail** - Full traces in admin console  
✅ **MCP boundaries** - Safe, controlled agent access  
✅ **HTTPS by default** - Self-signed certs for local dev  
✅ **Domain-driven** - Clean separation of concerns  

---

## Next Steps

1. **Setup**: Follow [SETUP.md](setup.md) to run locally
2. **Seed data**: Use [SEEDING.md](SEEDING.md) to download sample contracts
3. **Explore**: Login and ask the agent about your contracts
4. **Customize**: Modify RAG knowledge or contract templates
5. **Integrate**: Use the API or CLI for automation

See [README.md](README.md) for full architecture and documentation links.
