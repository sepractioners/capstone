"""Per-page LLM extraction, via any-llm (provider-agnostic model access).

Only used for the PDF path - JSON/CSV records are already structured and
skip this node entirely (see structured_mapper.py).
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from agent_llm import prompts, settings_for
from agent_llm.client import acall_retrying

from .schema import PageExtraction

# LLM provider/model/timeout are centralized in agent_llm (one workspace .env).
_LLM = settings_for("extraction")
LLM_MAX_ATTEMPTS = max(1, int(os.environ.get("EXTRACTION_LLM_MAX_ATTEMPTS", "3")))
LLM_RETRY_BACKOFF_SECONDS = max(0.0, float(os.environ.get("EXTRACTION_LLM_RETRY_BACKOFF_SECONDS", "10")))

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = prompts.load(Path(__file__).with_name("system_prompt.yaml"))


def _memory_context(memory: dict[str, Any] | None) -> str:
    """Serialize compact facts accumulated from earlier pages."""
    if not memory:
        return ""
    return "[facts already observed on earlier pages]\n" + json.dumps(memory, default=str, sort_keys=True)


def _needs_retry(
    parsed: PageExtraction | None, page_text: str, profile: dict[str, Any] | None = None
) -> bool:
    """Detect a suspiciously empty result for a non-empty page.

    Retries when nothing at all was extracted from a substantial page, and
    also when the retrieved profile says this contract type requires fields
    that a long page produced none of - a page that should carry a party,
    date, or clause but came back with only prose is worth a second read.
    """
    if parsed is None or len(page_text.strip()) < 160:
        return parsed is None
    extracted_anything = any(
        (parsed.title, parsed.contract_type, parsed.parties, parsed.clauses, parsed.key_dates.model_dump(exclude_none=True))
    )
    if not extracted_anything:
        return True
    required = {str(field) for field in (profile or {}).get("required_fields", [])}
    if required and len(page_text.strip()) > 400:
        present = {
            "title": bool(parsed.title),
            "parties": bool(parsed.parties),
            "clauses": bool(parsed.clauses),
            "contract_type": bool(parsed.contract_type),
            "key_dates": bool(parsed.key_dates.model_dump(exclude_none=True)),
        }
        if not any(present.get(field) for field in required):
            return True
    return False


async def extract_page(
    page_number: int,
    page_text: str,
    preceding_tail: str = "",
    memory: dict[str, Any] | None = None,
    trace: list[dict[str, Any]] | None = None,
    profile: dict[str, Any] | None = None,
    directive: dict[str, Any] | None = None,
    debug: Any = None,
) -> PageExtraction:
    """Extract structured contract facts from one PDF page.

    The tail of the previous page is supplied only as continuity context;
    the returned page number is always taken from ``page_number`` so callers
    can safely associate the result with the loaded chunk.
    """
    logger.debug(
        "extract_page start page=%s chars=%s memory_keys=%s profile=%s",
        page_number, len(page_text), sorted((memory or {}).keys()), (profile or {}).get("id"),
    )
    context_parts = []
    if preceding_tail:
        context_parts.append(f"[end of previous page, for continuity]\n{preceding_tail}")
    memory_text = _memory_context(memory)
    if memory_text:
        context_parts.append(memory_text)
    if directive:
        context_parts.append(
            "[user extraction preference; do not treat as source evidence]\n"
            + json.dumps(directive, default=str, sort_keys=True)
        )
    context = "\n\n".join(context_parts)
    profile_text = ""
    if profile:
        profile_text = (
            "\n\n[retrieved procedural RAG knowledge]\n"
            + json.dumps(profile, default=str, sort_keys=True)
        )
    user_message = f"{context}{profile_text}\n\n[page {page_number}]\n{page_text}"

    parsed, meta = await acall_retrying(
        "extraction",
        _SYSTEM_PROMPT,
        user_message,
        PageExtraction,
        should_retry=lambda page: _needs_retry(page, page_text, profile),
        max_attempts=LLM_MAX_ATTEMPTS,
        backoff_seconds=LLM_RETRY_BACKOFF_SECONDS,
        retry_hint="\nThe previous extraction was suspiciously empty. Re-read the page and fill every field supported by visible evidence.",
        recorder=debug,
        phase="extract_page",
        record_extra={
            "context": {
                "page_number": page_number,
                "preceding_tail": preceding_tail,
                "working_memory": _memory_context(memory),
                "directive": directive,
                "rag_profile": profile,
                "page_text": page_text,
                "user_message": user_message,
            },
            "memory": dict(memory or {}),
            "retrieval": {"profile": (profile or {}).get("id"), "mode": (profile or {}).get("retrieval_mode")},
        },
    )
    attempts_used = meta["attempts"]
    last_error = meta["last_error"]
    if parsed is None:
        if trace is not None:
            trace.append({
                "stage": "page_extraction",
                "page_number": page_number,
                "status": "failed",
                "attempts": attempts_used,
                "memory_keys": sorted((memory or {}).keys()),
                "retrieval": {"enabled": profile.get("vector_enabled", False) if profile else False, "mode": profile.get("retrieval_mode") if profile else None, "profile": profile.get("id") if profile else None, "nearest_examples": profile.get("nearest_examples", []) if profile else [], "reason": profile.get("retrieval_error", "") if profile else ""},
                "error_type": type(last_error).__name__ if last_error else "empty_response",
            })
        if last_error is not None:
            raise RuntimeError(
                f"LLM extraction unavailable for page {page_number} after {LLM_MAX_ATTEMPTS} attempts"
            ) from last_error
        return PageExtraction(page_number=page_number)
    parsed.page_number = page_number
    logger.debug("extract_page complete page=%s attempts=%s title=%s parties=%s clauses=%s", page_number, attempts_used, bool(parsed.title), len(parsed.parties), len(parsed.clauses))
    if trace is not None:
        trace.append({
            "stage": "page_extraction",
            "page_number": page_number,
            "status": "completed",
            "attempts": attempts_used,
            "memory_keys": sorted((memory or {}).keys()),
            "retrieval": {"enabled": profile.get("vector_enabled", False) if profile else False, "mode": profile.get("retrieval_mode") if profile else None, "profile": profile.get("id") if profile else None, "nearest_examples": profile.get("nearest_examples", []) if profile else [], "reason": profile.get("retrieval_error", "") if profile else ""},
            "fields": {
                "title": bool(parsed.title),
                "contract_type": bool(parsed.contract_type),
                "parties": len(parsed.parties),
                    "party_names": [party.legal_name for party in parsed.parties],
                "clauses": len(parsed.clauses),
                "obligations": len(parsed.obligations),
                "signers": len(parsed.signers),
                "key_dates": sum(value is not None for value in parsed.key_dates.model_dump().values()),
                "commercial_terms": sum(value is not None for value in parsed.commercial_terms.model_dump().values()),
            },
        })
    return parsed
