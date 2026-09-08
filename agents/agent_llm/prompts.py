"""Compose agent system prompts from their structured YAML files.

Prompt files are authored as sections (``persona``, ``goals``, ``constraints``
and whatever else that agent needs) rather than one long string, so they stay
reviewable. This flattens a section spec into the single string an LLM call
wants, without each agent hand-rolling its own reader.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _render(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(f"- {_render(item)}" for item in value)
    if isinstance(value, dict):
        return "\n\n".join(f"{key}:\n{_render(val)}" for key, val in value.items())
    return str(value)


def compose(spec: dict[str, Any]) -> str:
    """Flatten a structured prompt spec into one system-prompt string."""
    sections: list[str] = []
    for key, value in spec.items():
        body = _render(value)
        if not body:
            continue
        sections.append(body if key == "persona" else f"{key.replace('_', ' ').capitalize()}:\n{body}")
    return "\n\n".join(sections)


def load(path: str | Path) -> str:
    """Read a prompt YAML and return its system prompt."""
    prompt_path = Path(path)
    with prompt_path.open(encoding="utf-8") as prompt_file:
        spec = yaml.safe_load(prompt_file)
    if not isinstance(spec, dict) or not spec:
        raise ValueError(f"Invalid prompt file: {prompt_path}")
    flat = spec.get("system_prompt")
    return flat if isinstance(flat, str) else compose(spec)
