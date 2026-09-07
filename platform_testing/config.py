"""Scenario-evaluation config. LLM provider details come from ``agent_llm``."""
from __future__ import annotations

import os
from dataclasses import dataclass

from agent_llm import settings_for

_llm = settings_for("platform")


@dataclass(frozen=True)
class EvaluationConfig:
    provider: str = _llm.provider
    model: str = _llm.model
    temperature: float = _llm.temperature
    api_key: str | None = (
        os.environ.get("PLATFORM_LLM_API_KEY")
        or os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )


config = EvaluationConfig()
