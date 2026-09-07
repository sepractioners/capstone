"""ContractCandidate: the payload shape the `ingest_contract` MCP tool accepts.

Deliberately kept separate from anything in the `agents/extraction_agent`
package - the MCP server has no import-time dependency on the agent, and
any other future agent (a JSON importer, a CSV importer, a human-curated
fixture loader) can produce this same shape.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExtractedParty(BaseModel):
    legal_name: str
    party_type: str = "organization"
    country_code: str = "US"
    subdivision: Optional[str] = None
    roles: list[str] = Field(default_factory=lambda: ["other"])
    registration_id: Optional[str] = None


class ExtractedClause(BaseModel):
    heading: str
    clause_type: str = "general_provision"
    page_location: str
    text: str


class ExtractedObligation(BaseModel):
    description: str
    responsible_party_legal_name: str
    due_date: Optional[date] = None
    recurrence_frequency: Optional[str] = None
    recurrence_interval: int = 1
    trigger_event: str = ""
    consequence_of_failure: str = ""
    grace_period_days: int = 0
    evidence_requirements: list[str] = Field(default_factory=list)


class ExtractedSigner(BaseModel):
    party_legal_name: str
    signer_role: str
    order: int = 1
    signed_at: Optional[date] = None


class ExtractedKeyDates(BaseModel):
    effective_date: Optional[date] = None
    execution_date: Optional[date] = None
    expiration_date: Optional[date] = None
    renewal_deadline: Optional[date] = None
    termination_notice_deadline: Optional[date] = None


class ExtractedCommercialTerms(BaseModel):
    total_value_amount: Optional[Decimal] = None
    total_value_currency: Optional[str] = None
    payment_terms: Optional[str] = None


class ExtractedRenewalTerms(BaseModel):
    auto_renew: bool = False
    renewal_notice_days: Optional[int] = None
    renewal_term_length_months: Optional[int] = None


class ExtractedTerminationTerms(BaseModel):
    notice_period_days: Optional[int] = None
    cure_period_days: int = 0
    termination_for_convenience: bool = False


class FieldConflict(BaseModel):
    field: str
    candidate_values: list[str]


class ReviewFinding(BaseModel):
    field: str
    issue: str
    severity: str = "warning"
    suggestion: str = ""


class ContractCandidate(BaseModel):
    source_document_hash: str
    source_uri: str
    source_media_type: str
    source_content_base64: str
    source_original_filename: Optional[str] = None
    title: str
    contract_type: str
    parties: list[ExtractedParty] = Field(default_factory=list)
    clauses: list[ExtractedClause] = Field(default_factory=list)
    obligations: list[ExtractedObligation] = Field(default_factory=list)
    signers: list[ExtractedSigner] = Field(default_factory=list)
    key_dates: ExtractedKeyDates = Field(default_factory=ExtractedKeyDates)
    commercial_terms: ExtractedCommercialTerms = Field(default_factory=ExtractedCommercialTerms)
    renewal_terms: ExtractedRenewalTerms = Field(default_factory=ExtractedRenewalTerms)
    termination_terms: ExtractedTerminationTerms = Field(default_factory=ExtractedTerminationTerms)
    field_conflicts: list[FieldConflict] = Field(default_factory=list)
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    review_summary: str = ""
    extraction_trace: list[dict[str, Any]] = Field(default_factory=list)


class SkippedStage(BaseModel):
    stage: str
    reason: str


class IngestResult(BaseModel):
    contract_id: str
    contract_number: str
    lifecycle_status: str
    already_ingested: bool
    skipped_stages: list[SkippedStage] = Field(default_factory=list)
    field_conflicts: list[FieldConflict] = Field(default_factory=list)
    review_findings: list[ReviewFinding] = Field(default_factory=list)
    review_summary: str = ""
    extraction_trace: list[dict[str, Any]] = Field(default_factory=list)
