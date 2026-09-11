"""Request shape for organization-scoped query analysis."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    role: str
    text: str = Field(max_length=4000)


class ContractQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    organization_id: str = Field(min_length=1, max_length=120)
    contract_id: str | None = None
    history: list[ConversationTurn] = Field(default_factory=list, max_length=20)
    # Consecutive clarification turns already had on this conversation (0 for a
    # fresh question). The caller owns this count - it should stop asking and
    # surface a terminal message itself once it reaches the agent's
    # QUERY_CLARIFY_MAX_ROUNDS, rather than relying solely on the agent's own
    # gate. See ADR-0004 D3.
    clarify_round: int = Field(default=0, ge=0, le=20)