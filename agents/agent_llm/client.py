"""The one place any agent talks to an LLM.

Every agent-side model call goes through here: provider/model/temperature/timeout
come from :mod:`agent_llm` (one ``.env``), and when a ``TraceRecorder`` is passed
the call is recorded (system prompt, context, parsed output, reasoning, timing).

Agents keep only what is genuinely their own - their system prompts, their
schemas, and how they use the result.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Callable

from any_llm import acompletion
from pydantic import BaseModel

from . import settings_for
from agent_trace import TraceRecorder

logger = logging.getLogger(__name__)

# Transient provider failures worth a short retry - rate limits and 5xx from
# shared/free API pools (e.g. OpenRouter free models) rather than bad requests.
_RETRYABLE = {"RateLimitError", "InternalServerError", "APIConnectionError", "APIStatusError"}
_RETRIES = max(0, int(os.environ.get("LLM_RETRIES", "2")))
_RETRY_BACKOFF = max(0.0, float(os.environ.get("LLM_RETRY_BACKOFF_SECONDS", "3")))


def _messages(system: str, user: Any) -> list[dict[str, str]]:
    content = user if isinstance(user, str) else json.dumps(user, default=str)
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


async def raw_completion(
    role: str,
    system: str,
    user: Any,
    *,
    schema: type[BaseModel] | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
):
    """A single provider call. Raises on failure.

    ``timeout`` overrides the role's default (used for best-effort steps that
    should fall back fast rather than block for the full provider timeout).
    Retries a small number of times on transient errors (rate limits, 5xx).
    """
    s = settings_for(role)
    kwargs: dict[str, Any] = {}
    if s.api_base:
        kwargs["api_base"] = s.api_base
    call_timeout = s.timeout_seconds if timeout is None else timeout

    for attempt in range(_RETRIES + 1):
        try:
            return await asyncio.wait_for(
                acompletion(
                    model=s.model,
                    provider=s.provider,
                    messages=_messages(system, user),
                    response_format=schema,
                    temperature=s.temperature if temperature is None else temperature,
                    **kwargs,
                ),
                timeout=call_timeout,
            )
        except Exception as exc:  # noqa: BLE001 - retry transient, re-raise the rest
            if attempt < _RETRIES and type(exc).__name__ in _RETRYABLE:
                wait = _RETRY_BACKOFF * (attempt + 1)
                logger.info("LLM %s retrying after %s (%.0fs)", role, type(exc).__name__, wait)
                await asyncio.sleep(wait)
                continue
            raise


async def acall(
    role: str,
    system: str,
    user: Any,
    *,
    schema: type[BaseModel] | None = None,
    recorder: TraceRecorder | None = None,
    phase: str | None = None,
    context_extra: dict[str, Any] | None = None,
    record_extra: dict[str, Any] | None = None,
    temperature: float | None = None,
    timeout: float | None = None,
) -> tuple[Any, str]:
    """Best-effort call. Returns ``(result, note)``.

    ``result`` is the parsed model (``schema`` given) or the message text
    (no schema), or ``None`` on failure. ``note`` is ``""`` on success, else
    ``"<ExcType>: <message>"``. Records a trace step when ``recorder`` +
    ``phase`` are supplied; ``record_extra`` keys (e.g. ``memory``,
    ``retrieval``, a fuller ``context``) override the computed ones.
    """
    s = settings_for(role)
    result: Any = None
    raw_text = ""
    note = ""
    started = recorder.start() if recorder is not None else None
    try:
        response = await raw_completion(role, system, user, schema=schema, temperature=temperature, timeout=timeout)
        message = response.choices[0].message
        raw_text = getattr(message, "content", None) or ""
        result = message.parsed if schema is not None else raw_text
        if schema is not None and result is None:
            note = "no structured output"
    except Exception as exc:  # noqa: BLE001 - callers decide what a failure means
        note = f"{type(exc).__name__}: {exc}"
        logger.warning("LLM call failed role=%s phase=%s: %s", role, phase, type(exc).__name__)

    if recorder is not None and phase is not None:
        record_kwargs: dict[str, Any] = dict(
            model=s.model,
            provider=s.provider,
            system_prompt=system,
            context={"user": user, **(context_extra or {})},
            output=result.model_dump(mode="json") if isinstance(result, BaseModel) else result,
            output_raw=raw_text,
            reasoning=str(getattr(result, "reasoning", "") or ""),
            started=started,
            note=note,
        )
        record_kwargs.update(record_extra or {})
        recorder.record(phase, **record_kwargs)
    return result, note


async def acall_retrying(
    role: str,
    system: str,
    user: str,
    schema: type[BaseModel],
    *,
    should_retry: Callable[[BaseModel | None], bool],
    max_attempts: int = 1,
    backoff_seconds: float = 0.0,
    retry_hint: str = "\nThe previous response was unsatisfactory. Re-read the input and answer fully.",
    recorder: TraceRecorder | None = None,
    phase: str | None = None,
    context_extra: dict[str, Any] | None = None,
    record_extra: dict[str, Any] | None = None,
) -> tuple[BaseModel | None, dict[str, Any]]:
    """Call, retrying while ``should_retry`` is true, up to ``max_attempts``.

    Returns ``(parsed, meta)`` where ``meta`` has ``attempts``, ``note`` and
    ``last_error`` (an exception instance or ``None``). Records one trace step
    reflecting the final attempt; ``record_extra`` keys override the computed ones.
    """
    parsed: BaseModel | None = None
    raw_text = ""
    last_error: Exception | None = None
    attempts = 0
    started = recorder.start() if recorder is not None else None

    for attempt in range(max(1, max_attempts)):
        attempts = attempt + 1
        prompt = user + (retry_hint if attempt else "")
        try:
            response = await raw_completion(role, system, prompt, schema=schema)
            message = response.choices[0].message
            raw_text = getattr(message, "content", None) or ""
            parsed = message.parsed
            last_error = None
        except Exception as exc:  # noqa: BLE001 - retryable
            last_error = exc
            logger.warning("LLM retrying call failed role=%s attempt=%s/%s: %s", role, attempts, max_attempts, type(exc).__name__)
        if not should_retry(parsed):
            break
        if attempts < max_attempts:
            await asyncio.sleep(backoff_seconds * attempts)

    note = f"attempts={attempts}"
    if last_error is not None:
        note += f" error={type(last_error).__name__}"
    if recorder is not None and phase is not None:
        s = settings_for(role)
        record_kwargs: dict[str, Any] = dict(
            model=s.model,
            provider=s.provider,
            system_prompt=system,
            context={"user": user, **(context_extra or {})},
            output=parsed.model_dump(mode="json") if isinstance(parsed, BaseModel) else None,
            output_raw=raw_text,
            reasoning=str(getattr(parsed, "reasoning", "") or ""),
            started=started,
            note=note,
        )
        record_kwargs.update(record_extra or {})
        recorder.record(phase, **record_kwargs)
    return parsed, {"attempts": attempts, "note": note, "last_error": last_error}
