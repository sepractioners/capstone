# Contract Lifecycle Management: Domain-Driven Design

This document defines an independent domain model for contract lifecycle management (CLM). It is intentionally independent of any UI, persistence technology, workflow engine, AI system, ERP, CRM, or e-signature provider.

## Domain Vision

CLM manages the controlled progression of a contractual relationship from intake through drafting, approval, signature, execution, obligation management, renewal or termination, and archival. The domain protects the legal meaning of an agreement while making responsibilities, dates, risks, and decisions visible to authorized participants.

## Bounded Contexts

### Contract Authoring

Owns contract requests, templates, clauses, drafts, redlines, negotiations, and the creation of a proposed agreement.

It owns the legal wording and structure of a contract. A clause may define a right, obligation, condition, remedy, definition, or general provision. Clause management is concerned with wording, reuse, versions, negotiation, and approval of legal text.

### Contract Governance

Owns approval policies, legal and business review, delegated authority, exceptions, approvals, and audit decisions.

Governance may classify clauses, require standard or fallback wording, and assess deviations from the clause library.

### Signature and Execution

Owns signature packages, signatory authority, signature completion, effective execution, and executed contract versions.

### Obligation Management

Owns obligations, milestones, notices, deliverables, renewals, compliance evidence, breaches, and remediation.

It operationalizes commitments after they have been identified in an agreement. It owns assignments, schedules, occurrences, evidence, reminders, escalation, and breach handling, but does not own the legal wording that created the commitment.

### Contract Repository

Owns the authoritative record of executed agreements, versions, metadata, documents, relationships, retention, and controlled access.

### Third-Party and Reference Data

Owns party identities, organizational units, currencies, jurisdictions, policies, clause libraries, and integration mappings. Other contexts consume this data through published contracts rather than sharing their models directly.

### Reporting and Insight

Owns read-optimized views, portfolio metrics, alerts, and search projections. It does not change contract state.

Clause and obligation views are projections and may be combined for reporting, but their source models remain separate.

## Core Domain Model

### Aggregate: Contract

`Contract` is the primary aggregate root. It represents one contractual relationship and controls all state transitions that affect its lifecycle.

Key attributes:

- `ContractId`
- `ContractNumber`
- `ContractType`
- `LifecycleStatus`
- `Title`
- `Parties`
- `ContractVersions`
- `KeyDates`
- `CommercialTerms`
- `Obligations`
- `RenewalTerms`
- `TerminationTerms`
- `RiskProfile`
- `AccessPolicy`
- `AuditMetadata`

The aggregate should contain only data needed to enforce its invariants. Large document binaries, search indexes, activity feeds, and reporting projections belong outside the aggregate.

### Clause and Obligation Relationship

A clause is a legal provision in a contract version. An obligation is an actionable commitment derived from a clause, including who must act, what must be done, by when, how often, and what evidence demonstrates completion.

The relationship is explicit:

`Clause` -> `ClauseReference` -> `Obligation` -> `ObligationOccurrence`

One clause may produce several obligations, and not every clause produces an obligation. Clauses may instead express rights, conditions, definitions, remedies, or background terms. An obligation may also be created from a negotiated business term or policy, but it must retain its originating source when one exists.

The contract model owns the legally relevant obligation definition and its source clause reference. Obligation Management owns the operational schedule and occurrences. This keeps legal text immutable and reviewable while allowing day-to-day completion updates without rewriting the contract.

### Contract Lifecycle Status

Recommended states:

`Intake` -> `Drafting` -> `InReview` -> `Approved` -> `PendingSignature` -> `Executed` -> `Active` -> `Expired`

Alternative terminal or exceptional paths:

- `InReview` -> `Rejected`
- `Drafting` -> `Cancelled`
- `PendingSignature` -> `SignatureFailed`
- `Active` -> `Terminating` -> `Terminated`
- `Active` -> `Renewed`
- `Expired` -> `Archived`
- `Terminated` -> `Archived`

Status names may be adapted to organizational policy, but transitions must be explicit and validated by the aggregate.

### Contract Type: Value Object

`ContractType` is a value object, not a domain entity. Its meaning is determined entirely by its normalized value, such as `master-services-agreement`, `nda`, `sow`, `employment`, `vendor`, or `license`. It has no independent identity, lifecycle, or business behavior outside the contract that uses it.

Persist the canonical value on `Contract` and validate it against the supported type vocabulary. The value object should normalize input, reject unsupported values, and compare by value. If the organization later needs to manage contract types as records with owners, versioned policies, approval rules, templates, or effective dates, introduce a separate `ContractTypeDefinition` entity in a reference-data context; the contract would still retain the type value or reference required for historical accuracy.

## Entities

### Contract Party

Represents a legal entity or person bound by the agreement.

Attributes include `PartyId`, legal name, party type, registration identifiers, jurisdiction, address, and roles such as customer, supplier, employee, licensor, or guarantor.

### Contract Version

Represents a particular legal representation of the contract.

Attributes include version number, document reference, content hash, author, created time, change summary, superseded version, and version status.

Only one version can be the executed version for a given execution event. A signed version is immutable.

### Clause

Represents a legal provision within a contract version or a reusable clause-library entry. It has a clause identifier, heading, text reference, clause type, location, version, and status. A clause is immutable once its containing contract version is executed; a wording change requires a new version or amendment.

### Contract Review

Represents a review assignment or decision by a person or organizational role.

It records reviewer, review type, decision, comments, conditions, timestamps, and the version reviewed.

### Approval

Represents an approval decision made under a defined approval policy. It records the approver, authority basis, decision, scope, conditions, and expiration of the decision.

### Signature Package

Represents a coordinated request for signatures against one exact contract version. It contains signers, signing order, deadlines, provider reference, and completion state.

### Obligation

Represents an actionable commitment made by a party and derived from a contract term. It has an owner, responsible party, description, source clause reference, due-date rule, recurrence, evidence requirements, consequence of failure, and status. It is not a copy of the clause text.

### Obligation Occurrence

Represents one scheduled instance of a recurring or milestone obligation. It tracks due date, completion, evidence, acceptance, and breach status.

### Notice

Represents a formal notice required or permitted by the contract, including notice type, recipient, delivery method, notice period, sent date, and effective date.

### Amendment

Represents an agreed change to an executed contract. It references the contract version it modifies, affected clauses, effective date, approval and signature state, and resulting version.

### Exception

Represents an approved deviation from a policy, standard clause, approval threshold, or obligation process. It requires an owner, rationale, scope, approver, and expiry or review date.

## Value Objects

Value objects are immutable and compared by value, not identity.

- `ContractId`, `ContractNumber`, `PartyId`, and `ObligationId`
- `ContractType` and `LifecycleStatus`
- `LegalName` and `Jurisdiction`
- `Address` and `ContactDetails`
- `Money` with amount and currency
- `Percentage` and `Quantity`
- `DateRange`, `EffectiveDate`, `DueDate`, and `NoticePeriod`
- `RecurrenceRule`
- `ClauseReference` with document and location
- `DocumentReference` with URI, media type, and content hash
- `VersionNumber`
- `RiskRating` and `RiskFactor`
- `ApprovalThreshold`
- `SignatureRequirement`
- `DeliveryMethod`
- `BusinessCalendar`
- `Actor` and `OrganizationalRole`
- `Reason` and `ChangeSummary`

These objects should validate their own basic invariants, such as non-negative money, valid currency codes, ordered date ranges, and positive notice periods.

## Aggregate Boundaries

### Contract Aggregate

Contains lifecycle state, parties, current terms, version references, clause references, key dates, renewal and termination terms, and the obligation definitions needed for contract invariants. It handles commands such as:

- `CreateContract`
- `SubmitForReview`
- `ApproveContract`
- `RejectContract`
- `RequestSignature`
- `MarkExecuted`
- `ActivateContract`
- `CreateAmendment`
- `StartTermination`
- `TerminateContract`
- `ArchiveContract`

### Obligation Plan Aggregate

Use a separate aggregate when a contract has many obligations or high-frequency occurrence updates. It owns obligation scheduling, assignment, evidence, and breach handling while referencing `ContractId` and the obligation definition. It must not edit clause text or contract versions.

### Approval Case Aggregate

Use a separate aggregate for complex, long-running approval workflows. It owns approval routing, delegation, quorum or sequence rules, and policy exceptions while referencing the contract version under review.

### Signature Package Aggregate

Owns the signature process after a package is created. External signature provider callbacks must be translated into domain commands and must not directly mutate a contract.

## Domain Services

Use a domain service when behavior does not naturally belong to one entity or aggregate:

- `ApprovalPolicyEvaluator`: determines required approvals from contract facts and policy.
- `RenewalEvaluator`: determines whether a renewal window is open and what action is due.
- `NoticeDeadlineCalculator`: calculates a notice deadline using contract terms and a business calendar.
- `ObligationScheduler`: creates occurrences from due-date and recurrence rules.
- `RiskAssessmentService`: evaluates configured risk factors and records explainable results.
- `ContractVersioningService`: creates immutable versions and establishes supersession.
- `AuthorityChecker`: verifies that an actor may approve, sign, amend, or terminate.
- `PartyMatchingService`: resolves party identity without changing the contract’s legal facts.
- `ContractNumberGenerator`: assigns numbers according to organizational policy.

Services should return decisions or domain results. They should not hide side effects such as sending email, calling an e-signature provider, or writing to an accounting system.

## Domain Events

Events describe facts that have already happened. Suggested events include:

- `ContractCreated`
- `ContractSubmittedForReview`
- `ContractVersionCreated`
- `ContractReviewCompleted`
- `ContractApproved`
- `ContractRejected`
- `ExceptionGranted`
- `SignatureRequested`
- `SignatureCompleted`
- `SignatureFailed`
- `ContractExecuted`
- `ContractActivated`
- `ObligationCreated`
- `ObligationOccurrenceDue`
- `ObligationCompleted`
- `ObligationBreached`
- `RenewalWindowOpened`
- `RenewalInitiated`
- `AmendmentExecuted`
- `TerminationInitiated`
- `ContractTerminated`
- `ContractExpired`
- `ContractArchived`

Each event should include an event ID, aggregate ID, aggregate version, occurred-at timestamp, actor or system source, correlation ID, and the relevant version reference.

## Core Invariants

1. A contract must have at least two legally identified parties before approval.
2. A contract cannot be approved unless all required reviews, required fields, and policy checks are complete.
3. Approval applies to one exact contract version and is invalidated by material changes.
4. A contract cannot be executed without valid approvals and authorized signers.
5. The executed version is immutable; changes require an amendment or a new contract.
6. A contract cannot become active before execution and its effective date.
7. Every obligation has exactly one responsible party and an accountable owner.
8. A recurring obligation must produce a determinable schedule or be flagged for manual scheduling.
9. A termination or renewal action must respect the contract’s notice period and authority rules.
10. A terminated or expired contract cannot receive ordinary amendments; a post-termination amendment must be explicitly permitted.
11. Sensitive contract data is disclosed only to actors authorized for that contract and field.
12. Every consequential state change is auditable and idempotent.

## Application Services and Commands

Application services coordinate transactions, authorization, repositories, and integrations. They do not own domain rules.

Examples:

- `ContractIntakeService`
- `ContractReviewService`
- `ContractApprovalService`
- `ContractExecutionService`
- `ObligationManagementService`
- `RenewalManagementService`
- `TerminationService`
- `ContractSearchService`

An application command should carry an idempotency key and actor context. A typical command flow is:

1. Load the relevant aggregate.
2. Authorize the actor and validate command preconditions.
3. Invoke aggregate behavior or a domain service.
4. Persist the aggregate and its new version atomically.
5. Publish resulting domain events after commit.
6. Let handlers update projections or invoke external systems.

## Policies and Strategies

Policies should be explicit and replaceable rather than embedded in controllers:

- approval routing policy
- signature sequencing policy
- delegated authority policy
- renewal and auto-renewal policy
- termination and cure-period policy
- obligation escalation policy
- document retention policy
- access and redaction policy
- clause standardization policy

Policies return an explainable result containing the rule, inputs, decision, and policy version used.

## External Integrations

Integrations belong at the bounded-context boundary and are protected by an anti-corruption layer. Typical integrations include:

- document management for binary files
- e-signature for signature envelopes
- identity and organization data for users and parties
- CRM or procurement for business context
- ERP for approved financial terms
- compliance or risk systems for controls and evidence
- notification services for reminders and escalations

External systems are not authoritative for contract lifecycle state. Their callbacks become integration commands, are authenticated, deduplicated, and translated into domain behavior.

## Read Models and Audit

Use projections for views such as:

- contract portfolio and lifecycle dashboard
- upcoming renewals and termination deadlines
- obligation calendar and overdue work
- approval and signature queues
- clause and risk search
- party exposure summary

The audit log is append-only and records actor, command, decision, old state, new state, contract version, correlation ID, and evidence references. Audit entries are separate from domain entities and cannot be edited through normal lifecycle commands.

## Recommended Initial Slice

For a first implementation, build these capabilities in order:

1. Contract intake with parties, type, dates, and document references.
2. Versioned drafting and review.
3. Policy-driven approval with immutable decisions.
4. Signature package creation and execution confirmation.
5. Activation and key-date monitoring.
6. Obligation registration, reminders, evidence, and breach handling.
7. Renewal, termination, amendment, and archival workflows.

Keep automated extraction, search, analytics, and external system writes as adapters around this model. They may propose facts or actions, but the domain remains responsible for accepting valid state changes.

## Implementation Status (as of 2026-09-04)

A Python scaffold implementing this model lives under `contract_lifecycle/`, organized as domain / infrastructure / application layers, one class per file. Covers slice items 1-6 above end-to-end; item 7 (renewal, termination, amendment, archival) is implemented on the aggregate but only lightly exercised.

- **`domain/value_objects/`** - all value objects listed above, plus `KeyDates`, `CommercialTerms`, `RenewalTerms`, `TerminationTerms`, `AccessPolicy`, and `AuditMetadata` (attributes the doc names on `Contract` but doesn't define as standalone value objects).
- **`domain/entities/`** - all entities listed above. The doc's `Exception` entity is implemented as `PolicyException` to avoid shadowing the Python builtin.
- **`domain/aggregates/contract.py`** - the `Contract` aggregate root, with one method per command in the "Aggregate Boundaries" section, plus the supporting methods needed to reach each state (`add_party`, `add_version`, `add_review`, `register_obligation`, `execute_amendment`, `record_signer_signed`, ...). Enforces invariants 1-6, 9, and 10 directly; 7-8 are enforced by `Obligation`'s own constructor and `ObligationScheduler` respectively; 11-12 are not enforced by the aggregate (see gaps below).
- **`domain/events/`** - every event in the "Domain Events" list, sharing a common `DomainEvent` envelope (event ID, aggregate ID, aggregate version, occurred-at, actor, correlation ID, version reference).
- **`domain/services/`** - `ApprovalPolicyEvaluator` (+ `ApprovalPolicy` protocol and an `AmountThresholdApprovalPolicy` implementation), `RenewalEvaluator`, `NoticeDeadlineCalculator`, `ObligationScheduler`, `ContractNumberGenerator` (+ `SequentialContractNumberGenerator`), `AuthorityChecker` (+ `RoleBasedAuthorityChecker`). Not implemented: `RiskAssessmentService`, `PartyMatchingService`, `ContractVersioningService` (its job is done directly by `Contract.add_version`).
- **`domain/repositories/`** - `ContractReader` / `ContractWriter` split and recombined into `ContractRepository`, plus a `DomainEventPublisher` port.
- **`infrastructure/sqlite/`** - `SqliteConnectionFactory`, `ContractSchema`, `ContractMapper` (aggregate <-> JSON), `SqliteContractRepository` (optimistic concurrency via a `row_version` column decoupled from the event-counting `aggregate_version`), `SqliteDomainEventPublisher` (writes to the same outbox table the repository populates, marks rows published, dispatches to subscribed handlers).
- **`application/`** - one `Command` dataclass per command (each carrying `idempotency_key`, `actor`, `correlation_id`), and `ContractIntakeService`, `ContractReviewService`, `ContractApprovalService`, `ContractExecutionService`, `ObligationManagementService`, `RenewalManagementService`, `TerminationService`, `ContractSearchService`, sharing an `ApplicationService` base for the load -> authorize -> mutate -> persist -> publish flow.
- **Tests**: one end-to-end smoke test (`tests/test_contract_lifecycle_smoke.py`) driving the full intake -> draft -> review -> approve -> sign -> execute -> activate -> obligation -> terminate -> archive path against real SQLite, plus one optimistic-concurrency-conflict test. Both pass.

## Technical Debt and Known Gaps

- **No separate Obligation Plan, Approval Case, or Signature Package aggregates.** The doc calls these out as separate aggregates for high-volume or long-running cases; the scaffold keeps `Obligation`, `Approval`, and `SignaturePackage` as entities directly on `Contract`. `ObligationScheduler` computes occurrences on request but nothing persists them - a real Obligation Management context needs its own aggregate and repository.
- **No anti-corruption layer or external integrations.** E-signature provider callbacks, document management, ERP/CRM, and compliance systems are all out of scope; `SignaturePackage.provider_reference` is just a string field with no adapter behind it.
- **No read models / projections.** `ContractSearchService` queries the same write-side `ContractReader`, not a read-optimized projection. The "Reporting and Insight" bounded context (portfolio dashboards, renewal/termination calendars, clause and risk search) is undesigned.
- **No dedicated audit log.** The doc specifies an append-only audit log with actor, command, decision, old/new state, and evidence references, separate from domain entities. The scaffold's `domain_events` outbox table is event-sourced-shaped, not that audit shape, and has no old/new state diff.
- **Invariants 11 and 12 are unenforced.** Field-level access control ("disclosed only to actors authorized for that contract and field") and full auditability/idempotency of every consequential change are not implemented beyond the command-level `idempotency_key` check and `AuthorityChecker`'s coarse role gate on approve/sign/amend/terminate.
- **`ContractNumberGenerator`'s default implementation is in-memory only.** `SequentialContractNumberGenerator`'s counter resets on process restart, which would collide with existing numbers in a real deployment. Needs a persistent sequence (e.g. backed by the same SQLite database) before production use.
- **`ObligationScheduler`'s recurrence math is approximate.** Monthly/quarterly/yearly steps are computed as fixed day counts (30/91/365) rather than true calendar arithmetic, so long-running recurring obligations will drift.
- **`RenewalEvaluator`'s window is a flat day count**, not policy-driven per contract type or jurisdiction, and nothing currently calls it on a schedule (no background job triggers `RenewalWindowOpened`/expiry checks).
- **SQLite adapter opens a new connection per call** rather than pooling, and has no migration mechanism (`CREATE TABLE IF NOT EXISTS` only) - adequate for the current scaffold and tests, not tuned for concurrent production load or schema evolution.
- **Test coverage is a single smoke test plus a concurrency test.** No per-value-object validation tests, no negative-path invariant tests (e.g. approving with fewer than two parties, executing without a completed signature), no domain-service unit tests.
- **No CLI, HTTP, or other entry point** exposes the application services yet - they are only exercised from the test suite.