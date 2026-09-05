"""Optional local Gemma/Ollama evaluator for completed scenario traces."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from any_llm import completion
import yaml

from .config import config


PROMPT_PATH = Path(__file__).parent / "prompts" / "gemma_evaluation.yaml"


def evaluate(trace: dict[str, Any]) -> dict[str, Any]:
    """Ask the configured any-llm provider to evaluate a completed trace."""
    with PROMPT_PATH.open(encoding="utf-8") as prompt_file:
        prompt = yaml.safe_load(prompt_file)["system_prompt"]
    if config.api_key:
        import os

        os.environ.setdefault("ANTHROPIC_API_KEY", config.api_key)
        os.environ.setdefault("OPENAI_API_KEY", config.api_key)
    response = completion(
        model=config.model,
        provider=config.provider,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"SCENARIO TRACE:\n{json.dumps(trace, indent=2, default=str)}"},
        ],
        temperature=config.temperature,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)
