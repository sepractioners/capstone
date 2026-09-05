"""Per-page LLM extraction, via any-llm (provider-agnostic model access).

Only used for the PDF path - JSON/CSV records are already structured and
skip this node entirely (see structured_mapper.py).
"""
from __future__ import annotations

import os
from pathlib import Path

from any_llm import acompletion

from .schema import PageExtraction

DEFAULT_PROVIDER = os.environ.get("EXTRACTION_LLM_PROVIDER", "anthropic")
DEFAULT_MODEL = os.environ.get("EXTRACTION_LLM_MODEL", "claude-haiku-4-5-20251001")

def _load_system_prompt() -> str:
    """Load the PDF extraction prompt from the package YAML resource."""
    import yaml

    prompt_path = Path(__file__).with_name("system_prompt.yaml")
    with prompt_path.open(encoding="utf-8") as prompt_file:
        prompt = yaml.safe_load(prompt_file)
    if not isinstance(prompt, dict) or not isinstance(prompt.get("system_prompt"), str):
        raise ValueError(f"Invalid extraction prompt file: {prompt_path}")
    return prompt["system_prompt"]


_SYSTEM_PROMPT = _load_system_prompt()


async def extract_page(page_number: int, page_text: str, preceding_tail: str = "") -> PageExtraction:
    """Extract structured contract facts from one PDF page.

    The tail of the previous page is supplied only as continuity context;
    the returned page number is always taken from ``page_number`` so callers
    can safely associate the result with the loaded chunk.
    """
    context = f"[end of previous page, for continuity]\n{preceding_tail}\n\n" if preceding_tail else ""
    response = await acompletion(
        model=DEFAULT_MODEL,
        provider=DEFAULT_PROVIDER,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"{context}[page {page_number}]\n{page_text}"},
        ],
        response_format=PageExtraction,
        temperature=0,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        return PageExtraction(page_number=page_number)
    parsed.page_number = page_number
    return parsed
