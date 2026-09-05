"""Pydantic schemas used inside the extraction agent.

`ContractCandidate` here is deliberately a separate definition from
`clm_mcp_server.ingest_payload.ContractCandidate` (per the architecture
decision that the MCP server has no import-time dependency on the agent
package) but is kept field-for-field identical so `.model_dump()` on one
side deserializes cleanly as the other's tool input.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ExtractedParty(BaseModel):
    """A party identified in a contract source."""

    legal_name: str
    party_type: str = "organization"
    country_code: str = "US"
    subdivision: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    registration_id: Optional[str] = None


class ExtractedClause(BaseModel):
    """A clause or provision identified in a contract source."""

    heading: str
    clause_type: str = "general_provision"
    page_location: str
    text: str


class ExtractedObligation(BaseModel):
    """An obligation with its responsible party and optional timing."""

    description: str
    responsible_party_legal_name: str
    due_date: Optional[date] = None
    recurrence_frequency: Optional[str] = None
    recurrence_interval: int = 1


class ExtractedSigner(BaseModel):
    """A signer identified from an actual signature block."""

    party_legal_name: str
    signer_role: str
    order: int = 1
    signed_at: Optional[date] = None


class ExtractedKeyDates(BaseModel):
    """Important dates extracted from a contract."""

    effective_date: Optional[date] = None
    execution_date: Optional[date] = None
    expiration_date: Optional[date] = None


class ExtractedCommercialTerms(BaseModel):
    """Commercial value and payment terms extracted from a contract."""

    total_value_amount: Optional[Decimal] = None
    total_value_currency: Optional[str] = None
    payment_terms: Optional[str] = None


class FieldConflict(BaseModel):
    """Distinct singleton values found for one field across pages."""

    field: str
    candidate_values: list[str]


class PageExtraction(BaseModel):
    """What one page/chunk LLM call is asked to produce."""

    page_number: int
    title: Optional[str] = None
    contract_type: Optional[str] = None
    parties: list[ExtractedParty] = Field(default_factory=list)
    clauses: list[ExtractedClause] = Field(default_factory=list)
    obligations: list[ExtractedObligation] = Field(default_factory=list)
    signers: list[ExtractedSigner] = Field(default_factory=list)
    key_dates: ExtractedKeyDates = Field(default_factory=ExtractedKeyDates)
    commercial_terms: ExtractedCommercialTerms = Field(default_factory=ExtractedCommercialTerms)
    continues_from_previous_page: bool = False


class ContractCandidate(BaseModel):
    """The final, merged shape sent to the MCP server's ingest_contract tool."""

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
    field_conflicts: list[FieldConflict] = Field(default_factory=list)
