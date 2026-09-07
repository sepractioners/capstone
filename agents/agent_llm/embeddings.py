"""Local embeddings - one implementation for every agent.

Endpoint and model come from :mod:`agent_llm` (``EMBEDDING_URL`` /
``EMBEDDING_MODEL`` / ``OLLAMA_HOST`` in the workspace ``.env``).
"""
from __future__ import annotations

import json
import urllib.request

from . import EMBEDDING


def embed(text: str, *, max_chars: int = 12000, timeout: float = 120.0) -> list[float]:
    """Return one embedding vector for ``text`` from the configured endpoint."""
    payload = {"model": EMBEDDING.model, "input": text[:max_chars]}
    request = urllib.request.Request(
        EMBEDDING.url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    return (body.get("embeddings") or [body.get("embedding")])[0]
