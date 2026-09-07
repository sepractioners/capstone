"""Full-fidelity step trace for agent LLM interactions.

Records everything one agent run does at each step: which system prompt, the
exact context sent to the model, the raw and parsed output, the reasoning
field, a memory snapshot, retrieval detail, timing, and the model/provider.

The web orchestrator collects these and stores them per run; the Agent
Administration UI renders them. This is a developer-observability record - it
deliberately captures prompts and model reasoning.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

_MAX_STRING = 200_000


def _safe(value: Any) -> Any:
    """JSON-safe rendering; truncate pathologically large strings."""
    if value is None:
        return None
    try:
        rendered = json.loads(json.dumps(value, default=str, ensure_ascii=False))
    except (TypeError, ValueError):
        rendered = str(value)
    return _truncate(rendered)


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_STRING:
        return value[:_MAX_STRING] + f"... [truncated {len(value) - _MAX_STRING} chars]"
    if isinstance(value, list):
        return [_truncate(item) for item in value]
    if isinstance(value, dict):
        return {key: _truncate(item) for key, item in value.items()}
    return value


class TraceRecorder:
    """Append-only collector of agent step records."""

    def __init__(self, agent: str) -> None:
        self._agent = agent
        self._steps: list[dict[str, Any]] = []

    def start(self) -> float:
        return time.monotonic()

    def record(
        self,
        phase: str,
        *,
        model: str = "",
        provider: str = "",
        system_prompt: str = "",
        context: Any = None,
        output: Any = None,
        output_raw: str = "",
        reasoning: str = "",
        memory: Any = None,
        retrieval: Any = None,
        started: float | None = None,
        note: str = "",
    ) -> None:
        self._steps.append(
            {
                "step": len(self._steps) + 1,
                "agent": self._agent,
                "phase": phase,
                "model": model,
                "provider": provider,
                "system_prompt": system_prompt,
                "context": _safe(context),
                "output": _safe(output),
                "output_raw": output_raw,
                "reasoning": reasoning or "",
                "memory": _safe(memory),
                "retrieval": _safe(retrieval),
                "ms": round((time.monotonic() - started) * 1000) if started is not None else None,
                "note": note,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )

    def extend(self, steps: list[dict[str, Any]]) -> None:
        for step in steps:
            step = dict(step)
            step["step"] = len(self._steps) + 1
            self._steps.append(step)

    @property
    def steps(self) -> list[dict[str, Any]]:
        return self._steps
