# ADR-0007: Query Agent Template Response Formats and Agent Response Clarity

**Status:** Proposed

**Date:** 2026-09-11

## Context

The query agent's 12 prompt templates (T1–T12) define the planner's tool routing and decision logic, but lack explicit specification of:

1. **Response data fields** — which contract fields must be included in the answer (e.g., expiration_date, title, parties, contract_type)
2. **Response formatting rules** — how to structure and present the matched results
3. **Detail level guidance** — when to use `detail="full"` vs `detail="summary"` in list_contracts calls
4. **Example answers** — concrete before/after examples showing the expected response shape for each template

### Evidence

**Example query failure:** "What is the contract expiry date of Blue Yonder Logistics in the next 90 days which is an affiliate agreement?"

Expected response should include:
- Contract title/name
- Expiration date
- Party names
- Contract type

But **T5_expiring_and_renewals** template scaffold only says "Convey the matched count" — leaving the agent to guess which fields matter and how to format them.

**T2_filtered_roster** is clearer (mentions `detail=full` and `detail=summary` rules), but T3, T5, T9, and others are vague about:
- What fields to include per template
- When to show full vs. summary detail
- How to format dates, values, and party lists
- What constitutes a complete answer

### Problems This Creates

1. **Agent variance** — same question asked twice may produce differently-formatted answers (field order, precision, completeness)
2. **Coverage gaps** — agent omits relevant fields (e.g., expiration_date for T5, obligation due dates for T10)
3. **Ambiguous instructions** — scaffold says "report the total and the breakdown" (T1) but doesn't specify field names or ordering
4. **Hard to validate** — no clear "correct answer" format to measure against in tests
5. **Poor user experience** — inconsistent, incomplete responses for similar question types

### Template-Specific Issues

| Template | Issue |
|----------|-------|
| **T1** (portfolio_census) | Doesn't specify breakdown ordering or field precision |
| **T2** (filtered_roster) | Good guidance on detail levels but no field list |
| **T3** (clause_presence) | No guidance on whether to list contract names, just counts |
| **T4** (financial_rollup) | Doesn't specify currency formatting or decimal precision |
| **T5** (expiring_and_renewals) | ⚠️ Critical: No specification of which date fields to return |
| **T6** (clause_detail) | No guidance on quote formatting or evidence sourcing |
| **T7** (cross_contract_synthesis) | No coverage statement format defined |
| **T8** (comparative_review) | Doesn't specify how to present outliers vs. majority |
| **T9** (risk_exposure_review) | Missing expected fields: severity, why, contract_id format |
| **T10** (obligation_tracker) | No guidance on date format or sorting |
| **T11** (counterparty_profile) | No field ordering or grouping rules |
| **T12** (out_of_scope) | N/A — no tools used |

## Decision

Enhance each template to include four new sections:

### 1. **Response Fields (Required)**
```yaml
response_fields:
  - name: contract_id
    type: UUID
    always: true
    description: "Contract identifier"
  - name: title
    type: string
    always: true
    description: "Contract name or title"
  - name: expiration_date
    type: ISO date
    always: true (for T5 only)
    description: "Contract expiration date in YYYY-MM-DD"
```

### 2. **Detail Level Rules**
```yaml
detail_level:
  default: "summary"
  use_full_when:
    - "filtered set is small (< 5 contracts)"
    - "question asks for 'show me details' or 'full records'"
    - "the template requires access to nested fields (obligations, clauses)"
  fields_in_summary:
    - id, title, parties, contract_type, lifecycle_status, key_dates.expiration_date
  fields_in_full:
    - All fields including clauses, obligations, termination_terms, etc.
```

### 3. **Example Answers**
```yaml
examples:
  - question: "Which contracts expire in the next 90 days?"
    answer: |
      2 contracts expire within the next 90 days:
      1. "Contoso Logistics - Blue Yonder Affiliate Agreement"
         - Expiry: 2026-11-15
         - Parties: Blue Yonder (affiliate), Contoso Logistics (company)
         - Status: active
      2. "Fourth Coffee - Graphic Design Co-Branding Agreement"
         - Expiry: 2026-10-20
         - Parties: Fourth Coffee (partner), Graphic Design Inc. (partner)
         - Status: active
```

### 4. **Formatting Rules**
```yaml
formatting:
  dates: "ISO 8601 (YYYY-MM-DD)"
  currency: "Amount Currency (e.g., $1,200,000 USD)"
  party_names: "Legal name [role]"
  contract_list: "Numbered list with mandatory fields per template"
  confidence_note: "Always state if answer is partial/sampled"
```

## Implementation

### Phase 1: Audit & Document (Sprint N)
1. Read actual `list_contracts(detail=full)` response for each contract type
2. Document **minimum required fields** per template (user's pain points first)
3. Create example answers for each template using real seeded data
4. Update `agents/query_agent/prompts/templates.yaml` with the four sections above

### Phase 2: LLM Instruction Sync (Sprint N+1)
1. Rewrite `_PLAN_PROMPT` to include response field requirements
2. Update `contract_query.yaml` examples to match the new response formats
3. Add response format rules to `_DRAFT_ANSWER` scaffold (enforce field presence)
4. Add assertion in `_verify` to check for required fields

### Phase 3: Test & Validate (Sprint N+2)
1. Add test cases for each template with **expected response shape**
2. Measure agent variance across 5 runs of the same question (same model/temp)
3. Validate all required fields are present in 95%+ of answers
4. Update docs + ADR status to Accepted

## Consequences

### Positive
- ✅ **Predictable responses** — users know what fields to expect for each question type
- ✅ **Easier to test** — can validate response structure, not just content
- ✅ **Better coverage** — ensures expiration_date, obligations, severity fields are always included
- ✅ **Reduced variance** — same question produces consistent output across runs

### Negative
- ⚠️ **Longer responses** — requiring more fields may increase token usage (~5-10%)
- ⚠️ **More rigid structure** — less flexibility for the agent to summarize creatively
- ⚠️ **Example maintenance** — examples must be kept in sync as synthetic data changes

### Neutral
- 🔄 **Documentation burden** — ADR-0007 becomes a reference for all future template changes
- 🔄 **Backwards compatibility** — existing scripts using agent responses may need updates

## Open Questions

1. **Nested fields in responses?** Should T6/T7/T9 include full clause text, or just excerpts + contract_id?
2. **Pagination?** When matched > 10 contracts, should we offer "show more" or truncate?
3. **Sorting order?** For T5 (expiring), should we sort by expiration_date ascending?
4. **Confidence thresholds?** Should every answer include a confidence score, or only for synthesis templates?

## References

- [`agents/query_agent/prompts/templates.yaml`](../../agents/query_agent/prompts/templates.yaml)
- [`docs/query-agent-prompt-templates.md`](../../docs/query-agent-prompt-templates.md)
- ADR-0004: Query Agent Routing and Retrieval
- ADR-0006: Query Agent Routing, Retrieval, and Self-Correction

## Related Issues

- T5 expiry queries return empty (lack of expiration_date field in response)
- Inconsistent field ordering across templates
- No guidance on date/currency formatting
- Missing obligation due dates in T10 responses
