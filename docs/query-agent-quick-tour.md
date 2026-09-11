# Query Agent — Quick Tour, One Question Per Template

One real question per prompt template (T1–T12), run end-to-end through the
actual production path — `clm-agent` → authenticated API → orchestrator →
`query_mcp_server` → `query_agent.agent.answer()` — not a direct-call probe.
Each entry's `answer` is the literal captured output, not a hand-written
expectation; this file doubles as a data source (TOML blocks) and a readable
walkthrough (Markdown prose), same convention as
[`query-agent-benchmark-questions.md`](query-agent-benchmark-questions.md).

- Routing spec: [`docs/query-agent-prompt-templates.md`](query-agent-prompt-templates.md) · [ADR-0006](adr/0006-query-agent-routing-retrieval-and-self-correction.md)
- Self-correction loops: [ADR-0006](adr/0006-query-agent-routing-retrieval-and-self-correction.md)
- Referenced from: [README.md § Quick tour with the agent CLI](../README.md#4-quick-tour-with-the-agent-cli)

## Run config

```toml
[run]
date        = "2026-09-11"
cli         = "clm-agent ask <question> --json"
api         = "https://localhost:8443"
model       = "gemma4:latest"
provider    = "ollama"
ollama_host = "http://192.168.1.172:11434"   # remote LAN host - chat calls only
embedding_host = "http://127.0.0.1:11434"    # local - remote host has no nomic-embed-text pulled
env_file    = ".env.remote-gemma4"           # gitignored; QUERY_PLAN_TOOLS=1 (real LLM planner)
portfolio   = "capstone-review-2026 seed, 40 contracts"
```

## Questions

```toml
[[question]]
id       = "t1_portfolio_census"
template = "T1_portfolio_census"
question = "How many contracts do we have, broken down by contract type?"
answer   = "count by contract_type: distribution-agreement: 7, master-services-agreement: 6, services-agreement: 5, amendment: 4, co-branding-agreement: 4, affiliate-agreement: 4, vendor-agreement: 3, reseller-agreement: 3, license-agreement: 3, nda: 1."
confidence = 0.5
notes    = "Verified against the direct-probe test run separately - byte-identical. group_by correctly derived as contract_type (not the lifecycle_status default) from the T1 scaffold's group-by derivation rule."

[[question]]
id       = "t2_filtered_roster"
template = "T2_filtered_roster"
question = "List all active vendor agreements"
answer   = "2 contract(s) match the filter: First Line Media - Consolidated Pharma Vendor Agreement; First Line Health - First Line Foods Vendor Agreement."
confidence = 0.5

[[question]]
id       = "t3_clause_presence"
template = "T3_clause_presence"
question = "Which contracts mention liability insurance?"
answer   = "15 contract(s) mention liability + insurance: Tailspin Energy - Fourth Coffee Financial Amendment; ... , and 3 more. This list is capped - ask for a narrower filter or the full set for every match."
confidence = 0.5
notes    = "Full 15-contract list truncated here for readability; the CLI's raw --json output has all names."

[[question]]
id       = "t4_financial_rollup"
template = "T4_financial_rollup"
question = "What is the total value of our active contracts?"
answer   = "sum_value by contract_type: master-services-agreement: None, services-agreement: None, ... (all None)."
confidence = 0.5
notes    = "Expected, not a defect: the seeded synthetic portfolio does not persist contract_value (see query-agent-benchmark-questions.md substrate.not_persisted) - aggregate_contracts correctly returns None rather than inventing a figure. No benchmark/tour question should depend on this field until the seed data carries it."

[[question]]
id       = "t5_expiring_and_renewals"
template = "T5_expiring_and_renewals"
question = "Which contracts expire in the next quarter?"
answer   = "1 contract(s) match the filter: Blue Yonder Logistics - Southridge Cloud Affiliate Agreement."
confidence = 0.5
notes    = "'next quarter' correctly derived to expiring_within_days=90 per T1/T5's window-derivation rule."

[[question]]
id       = "t6_clause_detail"
template = "T6_clause_detail"
question = "What does the Limitation of Liability clause say in the Wingtip Pharma - Southridge Cloud Services Agreement?"
answer   = "The data provided does not contain the specific contract record for the 'Wingtip Pharma - Southridge Cloud Services Agreement.' ... However, the supplied evidence contains multiple instances of a Limitation of Liability clause, which consistently states: 'Neither party's aggregate liability under this Agreement exceeds the fees paid in the twelve (12) months preceding the claim' ... This limitation does not apply to breaches of confidentiality ... (This summary is based on the recurring clause text found across multiple contracts in the provided evidence.)"
confidence = 0.5
uncertain  = true
notes      = "Partial miss: T6's deduction_procedure says quote only what the NAMED contract's own evidence states, not a cross-contract generalisation - the model correctly flagged it couldn't confirm the named contract specifically, but then answered from evidence across multiple contracts instead of narrowing search_clauses to just that one. Real example of the model not fully executing the deduction_procedure; matches the pattern seen in the T9 A/B tests."

[[question]]
id       = "t7_cross_contract_synthesis"
template = "T7_cross_contract_synthesis"
question = "What payment obligations do we have across all contracts?"
answer   = "0 contract(s) mention payment + obligations."
confidence = 0.5
notes    = "Likely a query-phrasing miss, not a data gap - find_contracts AND-matched both words 'payment' and 'obligations' literally; the seeded clauses are titled 'Payment Terms', so a query of just 'payment' (per T3's key-phrase-extraction guidance, not yet echoed into T7's own scaffold) would likely have matched. Candidate follow-up: tighten T7's query-derivation guidance the same way T3's was."

[[question]]
id       = "t8_comparative_review"
template = "T8_comparative_review"
question = "Are our NDAs consistent?"
answer   = "Based on the supplied evidence, the Non-Disclosure Agreements (NDAs) appear consistent. All reviewed agreements contain the same clause regarding the protection and use of Confidential Information ..."
confidence = 0.5
uncertain  = true

[[question]]
id       = "t9_risk_exposure_review"
template = "T9_risk_exposure_review"
question = "What are the most significant contractual risks across our portfolio?"
answer   = "Reviewed the highest-signal indemnity, liability-cap, and renewal clauses across 40 matching contracts (a sample, not every contract): 1. Indemnification (High Severity) ... 2. Limitation of Liability (High Severity) ... 3. Renewal and Termination (Medium Severity) ... 4. Payment Terms (Medium Severity) ..."
confidence = 0.5
uncertain  = true
notes      = "The best T9 result across every test run this session - four distinct, evidence-cited, severity-tagged findings with correct coverage framing. Contrast with the earlier llama3.2:3b A/B tests, where the same deduction_procedure produced one-point-per-dimension structuring instead of one-per-clause; gemma4:latest did not repeat that failure mode here."

[[question]]
id       = "t10_obligation_tracker"
template = "T10_obligation_tracker"
question = "What do we owe and when?"
answer   = "40 contract(s): Tailspin Energy - Fourth Coffee Financial Amendment; ... , and 28 more. This list is capped - ask for a narrower filter or the full set for every match."
confidence = 0.5
uncertain  = true
notes      = "Listed contracts, not obligation -> party -> due-date rows as T10's scaffold specifies - reads as list_contracts(detail=full) resolved but the draft didn't extract per-obligation due dates from the full records. Candidate follow-up."

[[question]]
id       = "t11_counterparty_profile"
template = "T11_counterparty_profile"
question = "Who have we signed the most deals with?"
answer   = "count by party: Tailspin Energy Systems: 1, Fourth Coffee Financial Ltd.: 1, ... (every party: 1)"
confidence = 0.9
notes    = "Correct aggregate_contracts(group_by=party) call and correct reporting - but the seeded synthetic portfolio generates a unique fictitious company per contract, so there is no real repeat counterparty for 'most deals with' to surface. A data-generation limitation, not a template or guidance defect."

[[question]]
id       = "t12_out_of_scope"
template = "T12_out_of_scope"
question = "Should we renew our contract with Acme?"
answer   = "The supplied data does not contain any information regarding a contract with 'Acme' or advice on whether or when to renew such a contract."
confidence = 0.5
notes      = "UNCONFIRMED routing: this reads like a party-name lookup that found nothing, not T12's specified escalation phrasing ('I can report what your contracts state, not whether you should act...'). Could not confirm the actually-resolved template from available server logs this run - worth a follow-up probe run with full tracing before treating this as validated T12 behaviour."
```
