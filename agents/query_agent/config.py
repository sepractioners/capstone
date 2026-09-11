"""Query-agent behavioural config. LLM provider details come from ``agent_llm``.

Provider / model / temperature / timeout and the embedding endpoint are
centralized (one ``.env``); only the reasoning-loop knobs live here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from agent_llm import EMBEDDING, settings_for

_llm = settings_for("query")


@dataclass(frozen=True)
class QueryAgentConfig:
    # Centralized LLM settings (see agent_llm / the workspace .env)
    provider: str = _llm.provider
    model: str = _llm.model
    temperature: float = _llm.temperature
    timeout_seconds: float = _llm.timeout_seconds
    embedding_url: str = EMBEDDING.url
    embedding_model: str = EMBEDDING.model
    # Reasoning knobs (query-specific)
    plan_tools: bool = os.environ.get("QUERY_PLAN_TOOLS", "1") != "0"
    interpret: bool = os.environ.get("QUERY_INTERPRET", "1") != "0"
    verify: bool = os.environ.get("QUERY_VERIFY", "1") != "0"
    # Compose structural answers (count / list / breakdown / enumerate / aggregate)
    # straight from tool output - no LLM draft call - when no clause evidence was
    # gathered. The LLM draft still runs for clause-synthesis questions.
    deterministic_compose: bool = os.environ.get("QUERY_DETERMINISTIC_COMPOSE", "1") != "0"
    # Best-effort steps (plan, interpret) fall back to deterministic behaviour
    # rather than block for the full provider timeout on a slow local model.
    fast_timeout_seconds: float = max(20.0, float(os.environ.get("QUERY_FAST_TIMEOUT_SECONDS", "120")))
    # T9 (risk_exposure_review) needs, per named risk topic, one find_contracts
    # (matched count) + one search_clauses (real clause text) call - 4 topics x 2
    # + list_contracts for near-term deadlines = 9. 5 silently starved it down to
    # a single search_clauses call across the whole plan. 20 gives T9 (and any
    # future template that decomposes into several topic-pairs) real headroom;
    # every other template uses far fewer calls than that already.
    max_tool_calls: int = max(1, int(os.environ.get("QUERY_MAX_TOOL_CALLS", "20")))
    list_full_max: int = max(1, int(os.environ.get("QUERY_LIST_FULL_MAX", "10")))
    evidence_budget: int = max(4, int(os.environ.get("QUERY_EVIDENCE_BUDGET", "30")))
    search_k: int = max(2, int(os.environ.get("QUERY_SEARCH_K", "8")))
    # A question that projects onto no template (planner failed/declined, and
    # deterministic keyword+facet routing found nothing either) gets a
    # clarification, not a fabricated plan. Bounded so the loop terminates.
    clarify_max_rounds: int = max(1, int(os.environ.get("QUERY_CLARIFY_MAX_ROUNDS", "3")))
    # Bounded self-correction (in-request, not the cross-turn clarify loop above).
    # If gather() comes back with zero clause snippets for a template whose mode
    # needs real synthesis (S), replan once with that gap named explicitly before
    # falling through to today's deterministic-compose safety net unchanged. 0
    # disables replanning entirely.
    gather_replan_max_rounds: int = max(0, int(os.environ.get("QUERY_GATHER_REPLAN_MAX_ROUNDS", "1")))
    # If verify() flags unsupported claims, redraft once with those specific
    # labels named before falling through to today's confidence-capping
    # (min(draft.confidence, verify.adjusted_confidence)) unchanged. 0 disables.
    draft_reverify_max_rounds: int = max(0, int(os.environ.get("QUERY_DRAFT_REVERIFY_MAX_ROUNDS", "1")))


config = QueryAgentConfig()
