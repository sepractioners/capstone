"""Payload accepted by the tenant-scoped contract analysis MCP tool."""
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