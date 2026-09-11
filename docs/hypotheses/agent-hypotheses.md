# Agent Hypotheses & Experiments

Track hypotheses about agent architecture, prompts, and MCP usage. Proven hypotheses graduate to permanent heuristics in MCP_HEURISTICS.md.

---

## Active Hypotheses (Testing)

### H1: RAG Examples Improve Extraction Confidence

**Hypothesis**: If extraction agent retrieves CUAD examples before extracting obligations, confidence score increases by ≥15%.

**Rationale**: Extraction agents require examples to extract consistently. Providing similar clauses during extraction should improve output reliability more than increasing model size (validated in Week 1 learnings).

**Test Design**:
- Sample: 50 random contracts from ingestion pipeline
- Baseline: Extract without RAG examples (record confidence_score)
- Treatment: Extract with top-3 RAG examples retrieved first (record confidence_score)
- Metric: Mean confidence delta, % extraction errors (field_conflicts > 0)

**Current Status**: **IN PROGRESS**
- Extraction agent already retrieves examples on low confidence (<70%) retry
- Need systematic benchmark: baseline vs. retrieval-first approach
- Next step: Instrument extraction_agent/main.py to log with/without RAG

**Heuristic Candidate** (if validated): "Always retrieve RAG examples before extraction attempt 1 (not just on retry)"

---

### H2: Query History Improves Multi-turn Accuracy

**Hypothesis**: If query agent receives conversation history (prior turns), multi-turn question accuracy improves by ≥20%.

**Rationale**: "Tell me more" and follow-up questions require context. Passing prior exchange prevents re-answering the same question in different words.

**Test Design**:
- Sample: 30 multi-turn conversation sequences (3+ turns each)
- Baseline: Each turn treats question in isolation (no history)
- Treatment: Each turn receives full conversation history
- Metric: Accuracy (relevance of answer to context), token efficiency, hallucination rate

**Current Status**: **READY TO TEST**
- Query MCP already accepts `history: list[ConversationTurn]`
- Portal already sends history to query agent
- Need benchmark: evaluate 30 conversation chains with/without history
- Routing home: the *multi-turn follow-up* handling in the prompt-template
  catalogue (`agents/query_agent/README.md` → Original hypothesis → template mapping)

**Heuristic Candidate** (if validated): "Always pass history for conversational queries; omit only for one-shot questions"

---

### H3: Embedded Tool Descriptions Improve Parameter Mapping

**Hypothesis**: If MCP tool descriptions include prompt examples and routing heuristics, LLM parameter mapping accuracy improves by ≥25%.

**Rationale**: LLMs need explicit mappings (natural language → tool parameters). Embedding few-shot examples in tool descriptions prevents parameter guessing.

**Test Design**:
- Sample: 50 natural language queries (pre-categorized to expected tool + parameters)
- Baseline: Generic tool descriptions (current MCP descriptions pre-enhancement)
- Treatment: Rich tool descriptions with prompt examples + routing heuristics (current state post-enhancement)
- Metric: % correct tool chosen, % correct parameters, % parameter ambiguity/hallucination

**Current Status**: **DEPLOYED (Post-Enhancement)**
- Tool descriptions now include routing examples, prompt patterns, anti-patterns
- Query agent: superseded by the prompt-template catalogue - the planner names a
  template (an embedded description = tool allowlist + cues + scaffold) rather
  than picking raw tools. See `agents/query_agent/prompts/templates.yaml` and the
  hypothesis → template mapping in `agents/query_agent/README.md`. ADR-0006.
- Next step: `platform_testing/probe/query_agent_probe.py` scores the resolved
  plan against `expect_plan` per question - that is the H3 eval suite for the
  query agent.

**Heuristic Candidate** (if validated): "Always embed routing examples and anti-patterns in tool descriptions; update when adding new capabilities"

---

### H4: Retry Logic Reduces Extraction QA Findings

**Hypothesis**: If extraction agent implements confidence-based retry (confidence <70% → retrieve RAG examples + retry), % extractions with review_findings decreases by ≥30%.

**Rationale**: Retry with context improves output without requiring manual escalation.

**Test Design**:
- Sample: 100 contracts, split 50/50
- Baseline: Single-pass extraction (no retry logic)
- Treatment: Extraction with retry on confidence <70%
- Metric: % extractions with review_findings.severity="error", mean field_conflicts per contract, confidence score distribution

**Current Status**: **PARTIALLY IMPLEMENTED**
- Extraction agent logs `confidence_score` in metadata
- Retry logic exists but not systematic (triggered only on specific failures)
- Need to make retry automatic when confidence <70%

**Heuristic Candidate** (if validated): "Implement confidence-based retry as default; escalate only if confidence <50% after 2 retries"

---

### H5: Structured System Prompts Reduce Hallucination

**Hypothesis**: If agent system prompts include explicit Goal → Sub-goals → Constraints → Escalate conditions (as documented in HYPOTHESIS_AND_LEARNINGS.md Insight 2), hallucination rate decreases by ≥40%.

**Rationale**: LLMs without explicit constraints + escalation rules tend to hallucinate missing data rather than say "unknown".

**Test Design**:
- Sample: 100 queries (mix of answerable + unanswerable)
- Baseline: Standard system prompt (implicit constraints)
- Treatment: Structured system prompt (explicit Goal/Constraints/Escalate)
- Metric: Hallucination rate (incorrect claims not in contract), escalation rate (correct "not covered"), false positives

**Current Status**: **PARTIALLY IMPLEMENTED (query agent)**
- Each prompt template (`agents/query_agent/prompts/templates.yaml`) carries a
  goal + constraints scaffold; the `coverage` rule is the "don't overclaim"
  constraint; `T12_out_of_scope` is the explicit escalate path. Mapped in
  `agents/query_agent/README.md` → Original hypothesis → template mapping.
- Extraction agent system prompt needs similar audit.
- Eval: run `platform_testing/probe/query_agent_probe.py` on answerable +
  unanswerable questions; score hallucination / escalation rate.
- **Live A/B evidence this session** (see
  [MCP_HEURISTICS.md Pattern 6](MCP_HEURISTICS.md#pattern-6-structured-reasoning-scaffolds)
  for detail): explicit constraints reduced but did not eliminate
  hallucination - example categories placed next to a "don't invent"
  constraint got copied in regardless of evidence until the examples
  themselves were removed; a structural constraint reworded twice was still
  not followed by `llama3.2:3b`. The hypothesis's ≥40% hallucination-rate
  target has not been formally scored against the probe yet - the evidence so
  far is qualitative (single A/B comparisons, not the 100-query sample this
  hypothesis specifies) and should not be read as the hypothesis being fully
  validated, only partially supported with an important caveat attached.

**Heuristic Candidate** (if validated): "Always structure system prompts: Goal → Sub-goals → Constraints → Trade-offs → Escalate conditions"

---

### H6: Admin Console Observability Improves Debug Speed

**Hypothesis**: If extraction traces include step-by-step decisions (model, action, confidence, retry count), debug time for failed extractions decreases by ≥50%.

**Rationale**: Without visibility, debugging requires re-running extraction. Traces surface decisions immediately.

**Test Design**:
- Sample: 20 failed/problematic extractions
- Baseline: Debug without extraction_trace (re-run extraction + inspect code)
- Treatment: Debug with extraction_trace from Admin Console
- Metric: Time to diagnosis, debug success rate, confidence in fix

**Current Status**: **PARTIALLY IMPLEMENTED**
- ContractCandidate.extraction_trace field exists
- IngestResult.extraction_trace also exists
- Need Admin Console UI to display traces in debug view

**Heuristic Candidate** (if validated): "Always populate extraction_trace with decision breadcrumbs; Admin Console displays traces for debugging"

---

## Validated Hypotheses (Graduated to Heuristics)

### VH1: Training Data Quality > Model Size ✅

**Original Hypothesis**: Gemma4 (7B) + CUAD examples > GPT-3.5 without grounding. Quality of training data > model size.

**Validation**: Week 1 capstone development. Extraction agent achieves consistent results with small local model + good examples vs. larger cloud model without examples.

**Promoted Heuristic**: [MCP_HEURISTICS.md Pattern 5](MCP_HEURISTICS.md#pattern-5-better-data-than-bigger-models)
- Always provide examples during extraction
- Build better training data; don't chase larger models
- Applied to: Extraction RAG index, Query agent examples
- **Newer evidence** (query agent, live-tested): the same pattern one level
  down from model choice - an explicit decision spec inside one template's
  scaffold (T1's group-by derivation table) fixed a real planning judgment
  call on the first live run, same principle as CUAD examples. See Pattern 5.

---

### VH2: Structured Reasoning Scaffolds Prevent Hallucination ✅

*(Renamed from "Structured Cognitive Loops" - the shape is a fixed structure
for one prompt, not an iterative loop; the name was misleading. See
[MCP_HEURISTICS.md Pattern 6](MCP_HEURISTICS.md#pattern-6-structured-reasoning-scaffolds)
for the full correction and the query agent's actual loops - which are a
separate concept documented in
[ADR-0006](docs/adr/0006-query-agent-routing-retrieval-and-self-correction.md)
(the clarification loop is D3; the two in-request self-correction loops are
D9-D10).)*

**Original Hypothesis**: System prompts with Goal → Sub-goals → Constraints → Conditions prevent hallucination and inconsistency.

**Validation**: Week 1 capstone. Extraction agent structure (extract only text, no inference) + Query agent structure (escalate on weak evidence) both empirically prevent errors without requiring model size increase.

**Promoted Heuristic**: [MCP_HEURISTICS.md Pattern 6](MCP_HEURISTICS.md#pattern-6-structured-reasoning-scaffolds)
- Use structured system prompts for all agent capabilities
- Define explicit constraints, trade-offs, escalation conditions
- **Important refinement, found empirically this session**: a clearly-stated
  constraint is necessary but not sufficient on a small model. Two concrete
  findings, both in Pattern 6: (1) example categories sitting next to a
  constraint got copied into output regardless of evidence - fixed by
  removing the examples, not by restating the constraint; (2) a
  structural instruction ("one point per clause, not per dimension") was
  ignored by `llama3.2:3b` twice in a row despite being reworded and
  reinforced - evidence that some instructions are past what a given model
  size will execute, not a wording problem. The mitigation is bounding the
  blast radius (independent verification, bounded self-correction, a safe
  deterministic fallback), not a fourth rewording attempt.
- Applied to: Extraction agent (Goal → Sub-goals → Constraints → Retry/Escalate), Query agent (Goal → Sub-goals → Constraints → Escalate)

---

### VH3: Extraction Grounding via Plan → Prep → Pipeline ✅

**Original Hypothesis**: Agent grounding requires: (1) Planning what examples are needed, (2) Data Preparation (CUAD preprocessing), (3) Ingestion Pipeline (embeddings → SQLite → retrieval).

**Validation**: Week 1 capstone. CUAD dataset ingestion → embeddings → retrieval during extraction improves consistency and prevents hallucination.

**Promoted Heuristic**: [MCP_HEURISTICS.md Insight 3](MCP_HEURISTICS.md#insight-3-agent-grounding-plan--prep--pipeline)
- All new agents require: examples (Plan) + training data (Prep) + retrieval pipeline (Pipeline)
- Applied to: Extraction agent RAG index, Query agent examples, roadmap for SLA/risk agents

---

## Hypothesis Backlog (Future Testing)

| ID | Hypothesis | Priority | Est. Effort | Metric |
|---|-----------|----------|-------------|--------|
| H7 | Obligation retry on empty output improves completeness by ≥20% | High | 2d | % obligations found vs. baseline |
| H8 | Per-page extraction with memory prevents context loss on 100+ page contracts | High | 3d | Obligation count consistency across pages |
| H9 | Risk severity auto-calibration (trained on examples) > manual assignment | Medium | 1w | QA review time, severity accuracy |
| H10 | Contract lifecycle status prediction (active/expiring/renewal) improves accuracy with confirmation loop | Medium | 1w | Precision, recall, false positives |
| H11 | Multi-provider LLM fallback (Ollama → OpenRouter → Claude) improves uptime by ≥30% | Low | 3d | Successful query rate, fallback frequency |

---

## Running Experiments

### Template: Testing a Hypothesis

**Name**: H# — [Title]
**Hypothesis**: If [condition], [metric] improves by ≥[target]%.
**Test Design**:
- Sample size & composition
- Baseline procedure
- Treatment procedure
- Metric definition & measurement

**Execution Checklist**:
- [ ] Instrument code to collect metric
- [ ] Run baseline cohort (N=?)
- [ ] Run treatment cohort (N=?)
- [ ] Calculate delta + confidence interval
- [ ] Document result + recommendation

**Result**: [Validated | Rejected | Inconclusive]
**Next Step**: [Promote to heuristic | Iterate hypothesis | Archive]

---

## Integration: Hypotheses → Heuristics → Code

When a hypothesis validates:

1. **Document** in this file under "Validated Hypotheses"
2. **Add heuristic** to MCP_HEURISTICS.md with rule, why, example, anti-pattern
3. **Update tools** in mcp/*/server.py to embed heuristic in tool descriptions
4. **Update system prompts** in agents/*/prompts.py to enforce heuristic
5. **Mark in code** with comment: `# Heuristic H#: [description]` for traceability

Example:
```python
# Heuristic H1: RAG examples improve confidence
# Retrieving examples before extraction → confidence ≥15% higher
if confidence_score < 0.70:
    examples = retrieve_rag_examples(contract_type, chunk_type)
    result = llm.extract_with_examples(chunk, examples)
    confidence_score = evaluate_confidence(result)
```

---

## Cadence

- **Weekly**: Check progress on active hypotheses, collect metrics
- **Bi-weekly**: Evaluate if hypothesis ready to graduate (confidence ≥95%, sample size ≥30)
- **Monthly**: Promote validated hypotheses to heuristics, update MCP_HEURISTICS.md
- **Quarterly**: Design new hypotheses based on production observations + agent failure analysis
