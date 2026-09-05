"""Environment-file configuration for platform scenario evaluation."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(Path(__file__).parent / ".env")


@dataclass(frozen=True)
class EvaluationConfig:
    """Provider-neutral any-llm configuration from ``platform_testing/.env``."""

    provider: str = os.environ.get("PLATFORM_LLM_PROVIDER", "ollama")
    model: str = os.environ.get("PLATFORM_LLM_MODEL", "gemma4:latest")
    temperature: float = float(os.environ.get("PLATFORM_LLM_TEMPERATURE", "0"))
    api_key: str | None = os.environ.get("PLATFORM_LLM_API_KEY")


config = EvaluationConfig()