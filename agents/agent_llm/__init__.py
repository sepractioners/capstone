"""Centralized LLM provider configuration for every agent.

One env file is the single source of truth for provider / model / temperature /
timeout and the local embedding endpoint. It is resolved (first hit wins):

1. ``AGENT_ENV_FILE`` if set
2. the first ``.env`` found walking up from this file
3. ``.env`` at the workspace root (the dir with ``pyproject.toml`` + ``agents/``)
4. ``.env`` in the current working directory

Importing this module also calls ``load_dotenv`` (without ``override``), so every
other module's ``os.environ.get(...)`` sees the same values - a single ``.env``
configures the whole workspace.

Resolution order for any role: ``<ROLE>_LLM_MODEL`` -> ``LLM_MODEL`` (a global
override) -> a per-role built-in default. So setting ``LLM_PROVIDER`` +
``LLM_MODEL`` once points every agent at the same backend.

Supported providers (via any-llm-sdk):
- ``ollama`` — local LLM (free, requires Ollama installation)
- ``anthropic`` — Claude models (requires ANTHROPIC_API_KEY)
- ``openrouter`` — OpenRouter proxy (requires OPENROUTER_API_KEY)
- Other any-llm providers: openai, groq, etc. (may require additional setup)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Per-role built-in defaults (used only when nothing is set in the environment).
_ROLE_DEFAULTS: dict[str, tuple[str, str]] = {
    "extraction": ("anthropic", "claude-haiku-4-5-20251001"),
    "review": ("anthropic", "claude-haiku-4-5-20251001"),
    "planner": ("anthropic", "claude-haiku-4-5-20251001"),
    "summary": ("anthropic", "claude-haiku-4-5-20251001"),
    "query": ("ollama", "gemma4:latest"),
    "platform": ("ollama", "gemma4:latest"),
}
_DEFAULT_TIMEOUT = "300"
_DEFAULT_TEMPERATURE = "0"


def _resolve_env_file() -> Path | None:
    explicit = os.environ.get("AGENT_ENV_FILE")
    if explicit:
        return Path(explicit)
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env").exists():
            return parent / ".env"
        if (parent / "pyproject.toml").exists() and (parent / "agents").is_dir():
            return parent / ".env"
    cwd_env = Path.cwd() / ".env"
    return cwd_env if cwd_env.exists() else None


ENV_FILE = _resolve_env_file()
if ENV_FILE and ENV_FILE.exists():
    load_dotenv(ENV_FILE, override=False)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


_OLLAMA_HOST = _env("OLLAMA_HOST").rstrip("/")


@dataclass(frozen=True)
class LLMSettings:
    role: str
    provider: str
    model: str
    temperature: float
    timeout_seconds: float
    api_base: str = ""


def settings_for(role: str) -> LLMSettings:
    """Provider/model/temperature/timeout/api_base for one agent role."""
    prefix = role.upper()
    default_provider, default_model = _ROLE_DEFAULTS.get(role, ("ollama", "gemma4:latest"))
    provider = _env(f"{prefix}_LLM_PROVIDER") or _env("LLM_PROVIDER") or default_provider
    api_base = _env(f"{prefix}_LLM_API_BASE") or _env("LLM_API_BASE")
    if not api_base and provider == "ollama" and _OLLAMA_HOST:
        api_base = _OLLAMA_HOST
    return LLMSettings(
        role=role,
        provider=provider,
        model=_env(f"{prefix}_LLM_MODEL") or _env("LLM_MODEL") or default_model,
        temperature=float(_env(f"{prefix}_LLM_TEMPERATURE") or _env("LLM_TEMPERATURE") or _DEFAULT_TEMPERATURE),
        timeout_seconds=float(
            _env(f"{prefix}_LLM_TIMEOUT_SECONDS") or _env("LLM_TIMEOUT_SECONDS") or _DEFAULT_TIMEOUT
        ),
        api_base=api_base,
    )


@dataclass(frozen=True)
class EmbeddingSettings:
    provider: str
    url: str
    model: str


EMBEDDING = EmbeddingSettings(
    provider=_env("EMBEDDING_PROVIDER") or "ollama",
    url=_env("EMBEDDING_URL")
    or _env("EXTRACTION_RAG_EMBEDDING_URL")
    or _env("QUERY_EMBEDDING_URL")
    or (f"{_OLLAMA_HOST}/api/embed" if _OLLAMA_HOST else "")
    or "http://127.0.0.1:11434/api/embed",
    model=_env("EMBEDDING_MODEL")
    or _env("EXTRACTION_RAG_EMBEDDING_MODEL")
    or _env("QUERY_EMBEDDING_MODEL")
    or "nomic-embed-text:latest",
)
