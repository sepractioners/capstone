# MCP Heuristics & Prompt Examples

Document the reasoning patterns, constraints, and prompt templates for each MCP capability.

---

## 1. Extraction MCP Server (`extraction_mcp_server`)

**Purpose**: Write-capable boundary for ingesting extracted contract data. Agents persist structured extractions through domain invariants.

**Architecture Role**: Write boundary. Extraction Agent → Extraction MCP → Domain (SQLite).

### Capabilities

#### Tool: `ingest_contract(candidate: ContractCandidate)`

Persist a structured contract extraction.

**Input Schema** (ContractCandidate):
```python
# Document identity & metadata
source_document_hash: str              # SHA256 of original (idempotency key)
source_uri: str                        # Upload URI or file path
source_media_type: str                 # "application/pdf" etc.
source_content_base64: str             # Full document bytes
source_original_filename: str | None   # e.g., "NDA_2024.pdf"
title: str                             # Extracted title/name
contract_type: str                     # e.g., "NDA", "Service Agreement"

# Structured extractions
parties: list[ExtractedParty]          # Signatories with metadata
  - legal_name: str
  - party_type: str = "organization"
  - country_code: str = "US"
  - roles: list[str] = ["other"]       # e.g., ["service_provider"]
  - registration_id: str | None        # Tax ID, company number, etc.

clauses: list[ExtractedClause]         # Identified contract sections
  - heading: str
  - clause_type: str = "general_provision"
  - page_location: str                 # e.g., "page 2"
  - text: str

obligations: list[ExtractedObligation] # Commitments, deadlines, consequences
  - description: str
  - responsible_party_legal_name: str  # Must match a party
  - due_date: date | None
  - recurrence_frequency: str | None   # e.g., "monthly", "quarterly"
  - trigger_event: str                 # e.g., "upon termination"
  - consequence_of_failure: str        # e.g., "breach"
  - grace_period_days: int = 0
  - evidence_requirements: list[str]   # e.g., ["written notice"]

signers: list[ExtractedSigner]         # Who signed (not just parties)
  - party_legal_name: str
  - signer_role: str                   # e.g., "CEO", "Legal"
  - signed_at: date | None

key_dates: ExtractedKeyDates           # Critical dates
  - effective_date: date | None
  - execution_date: date | None
  - expiration_date: date | None
  - renewal_deadline: date | None
  - termination_notice_deadline: date | None

commercial_terms: ExtractedCommercialTerms
  - total_value_amount: Decimal | None
  - total_value_currency: str | None   # e.g., "USD"
  - payment_terms: str | None

renewal_terms: ExtractedRenewalTerms
  - auto_renew: bool = False
  - renewal_notice_days: int | None
  - renewal_term_length_months: int | None

termination_terms: ExtractedTerminationTerms
  - notice_period_days: int | None
  - cure_period_days: int = 0
  - termination_for_convenience: bool = False

# QA & debugging
field_conflicts: list[FieldConflict]   # Ambiguous/contradictory extractions
  - field: str                         # e.g., "effective_date"
  - candidate_values: list[str]        # Both interpretations

review_findings: list[ReviewFinding]   # Extraction issues or anomalies
  - field: str
  - issue: str                         # e.g., "Party not in signers"
  - severity: str = "warning"          # "info", "warning", "error"
  - suggestion: str

review_summary: str                    # Human-readable extraction QA
extraction_trace: list[dict]           # Debug logs (for Admin Console)
```

**Output Schema** (IngestResult):
```python
contract_id: str                       # UUID for future retrieval
contract_number: str                   # Normalized internal ID
lifecycle_status: str                  # "draft", "active", "archived"
already_ingested: bool                 # True if same source_document_hash
skipped_stages: list[SkippedStage]     # What wasn't extracted
  - stage: str                         # e.g., "obligations"
  - reason: str                        # e.g., "no obligations found"
field_conflicts: list[FieldConflict]   # Conflicts from ingestion logic
review_findings: list[ReviewFinding]   # Findings from domain validation
review_summary: str                    # Summary of validation results
extraction_trace: list[dict]           # Ingestion decision log
```

**Idempotency**: Re-ingesting same `source_document_hash` updates existing contract, not duplicate.

### Heuristics

#### 1. Parties vs. Signers: Keep Them Separate
**Rule**: `parties` = all entities mentioned; `signers` = those who signed.
**Why**: Obligations bind signers, not all mentioned parties. Admin Console distinguishes.
**Example (✅)**:
```python
parties=[
    ExtractedParty(legal_name="Acme Corp", roles=["service_customer"]),
    ExtractedParty(legal_name="Vendor Inc", roles=["service_provider"])
]
signers=[
    ExtractedSigner(party_legal_name="Acme Corp", signer_role="CEO"),
    ExtractedSigner(party_legal_name="Vendor Inc", signer_role="Legal Counsel")
]
# Insurance Co mentioned in Section 5 but didn't sign → not in signers
```

#### 2. Obligation's Responsible Party Must Match a Signer
**Rule**: `ExtractedObligation.responsible_party_legal_name` must exist in `signers`.
**Why**: Prevents obligations attributed to non-parties (creates orphaned commitments).
**Example (✅)**:
```python
obligations=[
    ExtractedObligation(
        description="shall provide 24/7 support",
        responsible_party_legal_name="Vendor Inc",  # ← Matches a signer
        due_date=None,
        trigger_event="upon contract execution"
    )
]
```
**Example (❌)**:
```python
obligations=[
    ExtractedObligation(
        description="...",
        responsible_party_legal_name="Insurance Co",  # ← Not a signer!
        ...
    )
]
```

#### 3. Dates: Use Date Objects, Not Strings
**Rule**: All date fields use `date` type (ISO 8601). Null if unknown.
**Why**: Domain validates & normalizes; string ambiguity (12/5 = Dec 5 or May 12?) prevented.
**Example (✅)**:
```python
from datetime import date
key_dates = ExtractedKeyDates(
    effective_date=date(2024, 1, 15),     # ✅
    expiration_date=date(2026, 1, 14),
    renewal_deadline=None                 # ✅ Unknown is fine
)
```
**Example (❌)**:
```python
key_dates = ExtractedKeyDates(
    effective_date="2024-01-15",          # ❌ String, not date
    renewal_deadline="Q1 2025"            # ❌ Ambiguous
)
```

#### 4. Obligations: Describe the Commitment, Not the Trigger
**Rule**: `description` is the commitment ("pay $50k monthly"); `trigger_event` is when it kicks in.
**Why**: Distinguishes contract mechanics from obligations.
**Example (✅)**:
```python
ExtractedObligation(
    description="shall pay service fees",
    trigger_event="upon invoice receipt",
    grace_period_days=30,
    consequence_of_failure="suspension of services"
)
```
**Example (❌)**:
```python
ExtractedObligation(
    description="upon invoice receipt shall pay service fees",  # ← Mixed
    trigger_event="",
    ...
)
```

#### 5. Commercial Terms: Include Currency
**Rule**: If `total_value_amount` is set, include `total_value_currency`.
**Why**: Prevents currency ambiguity (contract value assumes USD? EUR?).
**Example (✅)**:
```python
commercial_terms = ExtractedCommercialTerms(
    total_value_amount=Decimal("500000"),
    total_value_currency="USD",
    payment_terms="50% upon execution, 50% upon delivery"
)
```
**Example (❌)**:
```python
commercial_terms = ExtractedCommercialTerms(
    total_value_amount=Decimal("500000"),
    total_value_currency=None,  # ← Currency missing; domain rejects
    ...
)
```

#### 6. Flag Conflicts Early: Use field_conflicts
**Rule**: If two interpretations of a field exist, add both to `field_conflicts`.
**Why**: Admin Console shows user both interpretations; prevents silent wrong guess.
**Example (✅)**:
```python
# Expiration date says both "Jan 1, 2025" and "Dec 31, 2024" in different sections
field_conflicts=[
    FieldConflict(
        field="expiration_date",
        candidate_values=["2025-01-01", "2024-12-31"]
    )
]
# Don't guess; let domain/human decide
```

#### 7. review_findings: Surface QA Issues Before Ingestion
**Rule**: Extract adds review_findings; domain validation may add more.
**Why**: Admin Console shows all findings; prevents surprises.
**Severity Levels**:
- `"info"`: FYI (e.g., "all parties are US-based")
- `"warning"`: Anomaly but not blocking (e.g., "renewal notice period unusual: 180 days")
- `"error"`: Blocking extraction (e.g., "no signers found")

**Example**:
```python
review_findings=[
    ReviewFinding(
        field="termination_terms",
        issue="Notice period (180 days) is >90th percentile for this contract type",
        severity="warning",
        suggestion="Verify this is intentional; typical is 30-60 days"
    ),
    ReviewFinding(
        field="obligations",
        issue="3 obligations reference undefined party 'subsidiary'",
        severity="error",
        suggestion="Add 'subsidiary' to parties list or rephrase obligations"
    )
]
```

#### 8. extraction_trace: Leave Breadcrumbs for Debugging
**Rule**: Include extraction_trace dict(s) with model version, step, decision.
**Why**: Admin Console displays trace; helps debug why extraction failed.
**Example**:
```python
extraction_trace=[
    {"step": "parse_pdf", "result": "12 pages, 47 sections"},
    {"step": "extract_parties", "model": "gemma4:latest", "count": 2, "confidence": 0.94},
    {"step": "extract_obligations", "rag_examples_used": 3, "count": 8, "confidence": 0.82},
    {"step": "detect_conflicts", "conflicts_found": 1, "resolution": "manual"}
]
```

### Prompt Example: Extraction Agent → Ingestion

**System Prompt Fragment**:
```
You are the Extraction Agent. Goal: extract structured contract data into ContractCandidate.

Input: PDF or text document
Output: ContractCandidate with parties, clauses, obligations, dates, commercial terms, etc.

Process:
1. Read document end-to-end; identify: preamble, definitions, obligations, termination, signature block
2. Extract into schema fields:
   - parties: all mentioned entities (legal_name, roles, country_code)
   - signers: only those who signed (party_legal_name, signer_role)
   - key_dates: separate effective_date, expiration_date, renewal_deadline, etc.
   - obligations: each with responsible_party_legal_name (must match a signer), trigger_event, consequence_of_failure
   - commercial_terms: include currency
   - field_conflicts: if two interpretations exist (e.g., conflicting expiration dates)
   - review_findings: anomalies (severity: "info", "warning", "error")

Constraints:
- Extract only from contract text; do not infer missing data
- Responsible party in obligation must be a signer
- All dates as ISO date objects or null (no string approximations like "Q1")
- If conflicted, don't guess: add both candidates to field_conflicts
- Confidence <70%: retrieve RAG examples and retry

Escalation:
- Confidence <50% after 2 retries → add ReviewFinding with severity="error"
- Missing critical data (no signers, no parties): add ReviewFinding, severity="error"
- Unusual terms (renewal notice >90 days): add ReviewFinding, severity="warning"

After extraction, ingest via extraction_mcp_server.ingest_contract(candidate)
- Input: ContractCandidate object
- Output: IngestResult with contract_id, lifecycle_status, review_findings
- Check already_ingested flag: True means same source_document_hash already stored
```

### Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| No multi-currency support | USD assumed; EUR, GBP rejected | Normalize to USD or add currency field to metadata |
| No timezone handling | Dates treated as UTC | Store with explicit timezone in metadata |
| Party name variations | "ACME Inc" ≠ "Acme Incorporated" | Normalize names before ingestion or handle in Portal UI |
| Obligation cross-refs | "See Section 3" not resolved | Extract full text, not just reference |

---

## 2. Query MCP Server (`query_mcp_server`)

**Purpose**: Read-only boundary for analyzing contracts via natural language. Validates organization context (multi-tenant).

**Architecture Role**: Read boundary. Query Agent → Query MCP → domain + RAG index.

### Capabilities

#### Tool: `analyze_contracts(request: ContractQueryRequest)`

Answer a question over one or all contracts owned by an organization.

**Input** (ContractQueryRequest):
```python
question: str                         # Natural language (3-1000 chars)
organization_id: str                  # Tenant context (enforced)
contract_id: str | None               # Scope to single contract or None for portfolio
history: list[ConversationTurn]       # Prior turns (max 20)
  - role: str                         # "user" or "assistant"
  - text: str                         # Message text (max 4000 chars)
```

**Output**:
```python
{
    "question": str,
    "answer": str,                    # Grounded answer or "Not found in contracts"
    "sources": [                      # Evidence locations
        {"contract_id": str, "clause": str, "page": int, "confidence": float}
    ],
    "grounded": bool,                 # True if answer supported by evidence
    "debug_trace": dict               # Reasoning steps (for Admin Console)
}
```

**Scope**: Only contracts owned by `organization_id`. Enforced at tool boundary.

#### Tool: `find_contracts(organization_id, query, filters...)`

Deterministic full-text search. No ranking, no LLM.

**Input**:
```
query: str                            # "liability insurance", "30 days notice"
lifecycle_status: str | None          # "active", "archived", "pending"
contract_type: str | None             # "NDA", "Service Agreement"
party: str | None                     # Signatory name
effective_year: int | None            # 2024, 2025, etc.
expiring_within_days: int | None      # e.g., 90 (expiring within 90 days)
min_value, max_value: float | None    # Value range (in base currency)
```

**Output**:
```python
{
    "query": str,
    "filters": dict,
    "total_matches": int,
    "contracts": [
        {"id": str, "type": str, "parties": [str], ...}
    ]
}
```

**Deterministic**: Same query always returns same contracts. No ranking.

### Heuristics

#### 1. Question Scope Matters
**Rule**: If `contract_id` provided, answer must reference only that contract.
**Why**: Portfolio questions ("Do we have...") vs. specific-contract questions behave differently.

**Example (Portfolio)**:
```python
request = ContractQueryRequest(
    organization_id="org-123",
    contract_id=None,          # ← All contracts
    question="Which contracts have non-compete clauses?"
)
```
**Example (Specific)**:
```python
request = ContractQueryRequest(
    organization_id="org-123",
    contract_id="contract-uuid",  # ← This contract only
    question="What is the renewal date?"
)
```

**Agent Guidance**: 
- Portfolio → phrase as "Do we have...", "List all...", "Which contracts..."
- Specific → phrase as "In this contract, ...", "What is...", "Explain the..."

#### 2. Escalate When Evidence Weak
**Rule**: If RAG retrieval matches <50%, return "Not covered in contracts" instead of hallucinating.
**Why**: False positives worse than missing answers.

**Prompt Pattern**:
```
Goal: Answer question grounded in contract evidence

Constraints:
- Every claim must cite source location (page, clause)
- If <50% of retrieved clauses are relevant, return "Not covered in contracts"
- Distinguish facts (stated) vs. inferences (implied):
  "Inferred: If termination requires 30 days notice and contract ends in Q2..."

Escalate Conditions:
- No relevant clauses found → "Not addressed in contract"
- Multiple contradictory clauses → return all with confidence scores
- Question requires interpretation → flag: "Interpretation (not stated): ..."
```

#### 3. find_contracts: Exact Match, No Ranking
**Rule**: Use `find_contracts()` for deterministic searches; use `analyze_contracts()` for reasoning.
**Why**: Product/admin differ in expectations. Filtering ≠ reasoning.

**Example (✅ find_contracts)**:
```python
# "Show contracts expiring in next 90 days"
find_contracts(
    organization_id="org-123",
    query="expiring",  # Ignored; filters do the work
    expiring_within_days=90
)
```

**Example (❌ analyze_contracts for filtering)**:
```python
# DON'T: "Find contracts expiring in 90 days" via analyze_contracts
# Use find_contracts with filter instead
```

#### 4. History for Follow-ups
**Rule**: Pass `history` for multi-turn conversations; omit for one-off queries.
**Why**: Enables context carryover ("Tell me more") without rephrasing.

**Example**:
```python
# Turn 1: "What are the renewal terms?"
result1 = await analyze_contracts(ContractQueryRequest(..., history=None))

# Turn 2: "And what about penalties?"
result2 = await analyze_contracts(ContractQueryRequest(
    ...,
    history=[
        {"role": "user", "content": "What are the renewal terms?"},
        {"role": "assistant", "content": result1["answer"]}
    ]
))
```

### Prompt Example: Query Agent

**System Prompt**:
```
You are the Query Agent. Your goal: answer questions grounded in contract evidence.

Process:
1. Convert question to embeddings
2. Retrieve top 5 relevant clauses via RAG index
3. Evaluate relevance (>50% match = proceed; <50% = escalate)
4. Synthesize answer from clauses
5. Generate source citations (contract_id, page, excerpt)
6. Rate confidence (high/medium/low)

Constraints:
- Answer must cite exact text or clause location
- Separate facts (stated) from implications (inferred)
- Never hallucinate contract terms
- If evidence weak, return: "Not covered in contract"

Escalate Conditions:
- No relevant clauses found
- Clauses contradict each other
- Question ambiguous (e.g., "key dates" could mean effective, renewal, expiration)
  → ask: "Did you mean renewal date or expiration date?"

Scope Boundaries:
IN: Terms, obligations, dates, conditions explicitly stated
OUT: Industry practices, regulatory requirements, "should be there"
Example out-of-scope: "Is this SLA reasonable?" → "Not addressed. In-scope topics: [list]"
```

### Known Limitations

| Limitation | Impact | Workaround |
|-----------|--------|-----------|
| Single contract vs. portfolio confusion | Portal scopes to contract but CLI doesn't | Use `--contract-id` flag in CLI |
| Ambiguous multi-word queries | "renewal terms" ≠ "renewal dates" | Rephrase as "What is the renewal date?" |
| No real-time data | Pre-indexed; new extractions take seconds to searchable | Reasonable for CLM; not for live pricing |
| No cross-contract reasoning | Can't compare obligations across 2 contracts | Use portfolio queries + manual comparison |

---

## 3. CLM MCP Server (`clm_mcp_server`)

**Purpose**: Legacy compatibility server. Combines extraction ingestion + query tools.

**Status**: Maintained for backwards compatibility. New agents use `extraction_mcp_server` + `query_mcp_server`.

### Capabilities

Same as extraction_mcp_server + query_mcp_server combined.

- `ingest_contract(candidate)` — Persist extraction
- `get_contract(contract_id)` — Retrieve stored contract
- `get_source_document(contract_id)` — Fetch original PDF bytes
- (Query tools inherited from query_mcp_server)

### Heuristics

Use extraction_mcp_server + query_mcp_server directly. This server is for backward compatibility only.

---

## 4. Cross-MCP Patterns

### Pattern 1: Extract → Ingest → Query Loop

**Typical agent flow**:
1. Extraction Agent parses PDF → builds ContractCandidate
2. Calls `extraction_mcp_server.ingest_contract()` → returns contract_id
3. Query Agent later calls `query_mcp_server.analyze_contracts(contract_id=...)` to answer questions

**Prompt Pattern**:
```
After successfully extracting and ingesting a contract, remember its contract_id.
Later questions about the same contract should reference that ID:
  analyze_contracts(..., contract_id=contract_id_from_ingestion)
```

### Pattern 2: Portfolio vs. Specific Contract Queries

**Portfolio Query (explore)**:
```python
# "Do we have any non-competes?"
find_contracts(
    organization_id=org_id,
    query="non-compete"  # Full-text search
)
```

**Specific Query (verify)**:
```python
# "Is there a non-compete in this contract?"
analyze_contracts(ContractQueryRequest(
    organization_id=org_id,
    contract_id="contract-uuid",  # Scoped
    question="Is there a non-compete clause?"
))
```

### Pattern 3: Extraction Confidence & Retry

**Heuristic**: If extraction confidence <70%, retrieve RAG examples before retry.

**System Prompt Fragment**:
```
Extraction Confidence Retry:
- Confidence 90-100%: Ingest immediately
- Confidence 70-89%: Proceed with metadata flag
- Confidence <70%: Retrieve CUAD examples of similar clauses, retry with context
- Confidence <50% after retry: Escalate for human review
```

### Pattern 4: Admin Console Observability

**Metadata for debugging**:
```python
metadata={
    "extraction_model": str,          # Model used
    "rag_examples_retrieved": int,    # How many examples provided
    "retry_count": int,               # Iterations to get confidence
    "confidence_score": float,        # Final confidence 0-1
    "pages_processed": [int],         # Which pages had data
    "validation_errors": [str],       # Schema issues (if any)
    "error_recovery": str             # "retry", "human_escalate", "none"
}
```

Admin Console displays this for debugging failed extractions.

### Pattern 5: Better Data Than Bigger Models

**Heuristic**: a well-specified example set or decision spec substitutes for
raw model scale more reliably than switching to a larger model.

**Original evidence** (Week 1 capstone): the extraction agent with a small
local model + CUAD-grounded RAG examples produced more consistent results than
a larger cloud model with no grounding examples.

**Newer evidence** (query agent, this session): the same pattern shows up one
level down, at the *planning* decision inside a single template, not just at
the model-selection level. T1's original scaffold told the planner "call
`aggregate_contracts` for a grouped breakdown" with no rule for *which*
`group_by` value to pick - a genuine judgment call every time. Adding an
explicit decision table directly to the scaffold ("'by status' -> lifecycle_status,
'by type' -> contract_type...") fixed it on the very first live run against a
real model (`gemma4:latest`) - the resolved plan's own `reasoning` field
echoed the rule back verbatim. Same principle as CUAD examples: a concrete
spec the model can pattern-match against beats hoping a bigger model infers
the right default. See `agents/query_agent/prompts/templates.yaml` (T1, T2,
T4, T10, T11 scaffolds) and [ADR-0006](docs/adr/0006-query-agent-routing-retrieval-and-self-correction.md).

### Pattern 6: Structured Reasoning Scaffolds

**Heuristic**: give every agent capability an explicit Goal → Sub-goals →
Constraints → Escalate shape, so hallucination and inconsistency have a named
place to be caught.

Note on naming: this used to be called "Structured Cognitive Loops" in
`AGENT_HYPOTHESES.md` (VH2). That name is corrected here - the shape is a
**fixed structure for one prompt**, applied once, not an iterative loop. A
real loop (perceive → act → observe → repeat) is a different, separate
concept; the query agent's actual loops - the cross-turn clarification loop
and the two in-request self-correction loops - are documented in
[ADR-0006 D3](docs/adr/0006-query-agent-routing-retrieval-and-self-correction.md) and
[ADR-0006](docs/adr/0006-query-agent-routing-retrieval-and-self-correction.md), and don't
share a name with this pattern to avoid exactly this confusion.

**Worked example** - `T9_risk_exposure_review`
(`agents/query_agent/prompts/templates.yaml`):
- 🎯 **Goal**: "what should I worry about" - an open-ended risk/exposure question.
- **Sub-goals**: decompose into concrete probes, one find_contracts + search_clauses
  pair per named risk topic.
- 🚧 **Constraints**: "never assert a risk without a cited clause"; the
  `deduction_procedure` field further constrains *how* a retrieved clause
  becomes a severity judgment (four named dimensions, `why` must quote the
  triggering text).
- 🛑 **Escalate**: `T12_out_of_scope`, or the clarification loop when the
  question projects onto no template at all.

**Important caveat, found empirically this session - constraints stated
clearly are necessary but not sufficient on a small model:**

1. The interpret stage's own prompt said, in the same breath, "do not invent
   terms the evidence does not contain" *and* listed example risk categories
   ("uncapped liability, penalties") as illustrations of the field's purpose.
   The model copied the named examples into its output regardless of whether
   the evidence supported them - not because the constraint was missing, but
   because of *where* the examples sat relative to it. Removing the concrete
   examples (keeping only the constraint) fixed this specific failure.
2. A later, more demanding instruction - "produce exactly ONE `what_matters`
   point per clause, never one per dimension" - was given to `llama3.2:3b`
   twice, worded as clearly as it could be, reinforced the second time. The
   model organised its output by dimension both times anyway. This is
   evidence that some structural instructions are past what a given model
   size will reliably execute, no matter how the prompt is worded - not
   something that gets fixed by rewording a third time.

**Practical implication**: a structured scaffold reduces hallucination but
cannot be the *only* defence - pair it with an independent check that doesn't
share the drafting model's blind spots (`_verify` re-reading the draft against
deterministic data, ADR-0006's bounded self-correction loops as a second
attempt, and a safe deterministic fallback for when synthesis isn't
well-evidenced enough to attempt). See
[ADR-0006](docs/adr/0006-query-agent-routing-retrieval-and-self-correction.md) and
[ADR-0006](docs/adr/0006-query-agent-routing-retrieval-and-self-correction.md).

---

## 5. Implementation Checklist for New MCPs

When adding a new capability (e.g., SLA extraction, risk classification):

- [ ] Define input schema (required fields, types, constraints)
- [ ] Define output schema (include success/error cases)
- [ ] List heuristics (what works, what fails, why)
- [ ] Provide system prompt template for calling agent
- [ ] Document constraints (idempotency, scope, validation)
- [ ] Note known limitations & workarounds
- [ ] Add metadata fields for observability

Example template:

```markdown
### Tool: `new_capability(...)`

**Input**: ...
**Output**: ...

### Heuristics

#### 1. Core Rule
**Rule**: ...
**Why**: ...
**Example (✅)**: ...
**Example (❌)**: ...

### Prompt Example

**System Prompt Fragment**: ...

### Known Limitations

| ... | ... | ... |
```

---

## 6. Testing & Validation

### For Extraction Heuristics

Test these scenarios:
```bash
# 1. Verify parties are signatories
./scripts/agent.sh extract "test_nda.pdf" --validate-parties

# 2. Check date format validation
./scripts/agent.sh extract "test_agreement.pdf" --check-dates

# 3. Confirm obligations use definitive verbs
./scripts/agent.sh extract "test_contract.pdf" --validate-obligations
```

### For Query Heuristics

Test these scenarios:
```bash
# 1. Portfolio vs. specific scope
./scripts/agent.sh ask "Any non-competes?" --contract-id all
./scripts/agent.sh ask "Non-compete in this one?" --contract-id <uuid>

# 2. Escalation on weak evidence
./scripts/agent.sh ask "What is the CEO's favorite color?" --debug

# 3. Multi-turn history
./scripts/agent.sh chat  # Enable history mode
```

---

## 7. Embedded Tool Descriptions (LLM-Facing)

MCP tool descriptions are enriched with routing heuristics and prompt examples so that LLMs calling these tools understand the patterns. These are embedded in the MCP server code:

### extraction_mcp_server/server.py
- **ingest_contract**: Includes idempotency rules, party validation, field_conflicts pattern, extraction_trace pattern
- **get_contract**: Includes verification pattern, Admin Console use case
- **get_source_document**: Includes quality verification, side-by-side comparison use case
- Server-level instructions cover: Workflow, quality heuristics, idempotency, constraints

### query_mcp_server/server.py
- **analyze_contracts**: Includes routing (portfolio vs. specific), prompt examples (3 scenarios), escalation rules, scope boundaries
- **find_contracts**: Includes find vs. analyze distinction, prompt examples, query syntax rules (AND matching)
- **search_clauses**: Includes deterministic keyword ranking, agent internal use, direct search use case, limit management
- Server-level instructions cover: 4-tool routing guide, key heuristics, portfolio vs. specific patterns

---

## Summary

Each MCP capability has:
- **Purpose**: What it does in the architecture
- **Input/Output**: Strict schemas for validation
- **Heuristics**: Rules (with why & examples) that prevent common failures
- **Prompts**: System prompt templates for calling agents
- **Embedded Tool Descriptions**: Routing hints and examples in MCP server code (LLM-facing)
- **Limitations**: Known constraints & workarounds

Update this document when:
- Adding new heuristics (discovered through agent failures)
- Changing MCP input/output schemas
- Documenting new patterns or anti-patterns
- Adding new agents that call MCPs
- Updating tool descriptions in MCP server code (keep this document in sync)
