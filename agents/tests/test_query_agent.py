"""Query agent: plan (template routing) -> gather -> interpret -> draft -> verify.

All LLM calls are mocked; the deterministic portfolio tools run for real. Tool
*selection* is the planner's job (it names a template, which fixes the tool
allowlist); `_guard_plan` only does filter-value hygiene + allowlist enforcement
+ the fixed fallback. The degraded router (`_deterministic_route`) is what runs
when `QUERY_PLAN_TOOLS=0`.
"""
from __future__ import annotations

import asyncio
import dataclasses
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agent_llm import client as llm_client
from query_agent import agent
from query_agent.agent import QueryAnswer, answer

_RANK = dict(side_effect=lambda q, r, k, c=None: ([(0.8, x) for x in r[:k]], {"mode": "test"}))


@pytest.fixture(autouse=True)
def _pinned_config():
    """Pin the reasoning-loop config so the suite is independent of the local
    .env. LLM planner on, LLM draft always (deterministic compose off) so the
    mocked draft is exercised, interpret + verify on."""
    cfg = dataclasses.replace(
        agent.config, plan_tools=True, interpret=True, verify=True, deterministic_compose=False
    )
    with patch.object(agent, "config", cfg):
        yield cfg


def _resp(parsed):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed, content=""))])


def _plan(*tools, template=""):
    return agent._Plan(template=template, calls=[agent._ToolCall(**t) for t in tools])


CONTRACTS = [
    {
        "id": "c1", "title": "Services Agreement", "contract_number": "IMPORT-1",
        "lifecycle_status": "active", "contract_type": "services-agreement",
        "parties": [{"legal_name": "Acme Corp"}],
        "clauses": [{"heading": "Payment", "text": "Customer pays within thirty days."}],
        "key_dates": {}, "commercial_terms": {},
    },
    {
        "id": "c2", "title": "NDA", "contract_number": "IMPORT-2",
        "lifecycle_status": "active", "contract_type": "nda",
        "parties": [], "clauses": [], "key_dates": {}, "commercial_terms": {},
    },
    {
        "id": "c3", "title": "Old NDA", "contract_number": "IMPORT-3",
        "lifecycle_status": "in_review", "contract_type": "nda",
        "parties": [], "clauses": [], "key_dates": {}, "commercial_terms": {},
    },
]

_FACETS = {"lifecycle_status": ["active", "in_review"], "contract_type": ["services-agreement", "nda"]}


def _run(question, contracts=CONTRACTS, **kw):
    return asyncio.run(answer(question, contracts, **kw))


# --------------------------------------------------------------- planner routing
def test_count_question_routes_to_count_contracts_with_no_retrieval() -> None:
    draft = QueryAnswer(answer="2 contracts are active.", confidence=0.95, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "count_contracts", "lifecycle_status": "active"}, template="T1_portfolio_census")),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.95)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("How many active contracts do we have?")

    assert "2" in result.answer
    assert calls.await_count == 3  # plan + draft + verify - no interpret, no search
    trace = agent.get_trace()
    tool = next(s for s in trace if s["phase"] == "tool:count_contracts")
    assert tool["output"]["matched"] == 2
    assert not any(s["phase"] == "rank_evidence" for s in trace)


def test_clause_question_routes_to_search_and_runs_interpret() -> None:
    draft = QueryAnswer(
        answer="Customer pays within thirty days.", confidence=0.9,
        citations=[{"contract_id": "c1", "label": "clause:Payment", "evidence": "..."}],
    )
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "search_clauses", "query": "payment terms"}, template="T6_clause_detail")),
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.9)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("What does the payment clause say?")

    assert result.answer.startswith("Customer pays")
    assert calls.await_count == 4
    assert any(s["phase"] == "interpret" for s in agent.get_trace())


def test_mixed_question_emits_list_and_search_within_one_template() -> None:
    """A "how many X and what do their clauses say" question -> T6_clause_detail:
    list_contracts for the set + search_clauses for the terms."""
    draft = QueryAnswer(answer="2 active; termination on 30 days notice.", confidence=0.85, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan(
            {"tool": "list_contracts", "lifecycle_status": "active"},
            {"tool": "search_clauses", "query": "termination"},
            template="T6_clause_detail",
        )),
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.85)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("How many active contracts and what are their termination terms?")

    phases = [s["phase"] for s in agent.get_trace()]
    assert "tool:list_contracts" in phases and "rank_evidence" in phases
    assert result.answer.startswith("2 active")


def test_guard_drops_calls_outside_the_named_template_allowlist() -> None:
    """T1_portfolio_census allows only count/aggregate - a search_clauses call the
    planner slipped in is dropped, not run."""
    draft = QueryAnswer(answer="3 contracts.", confidence=0.9, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan(
            {"tool": "count_contracts"},
            {"tool": "search_clauses", "query": "anything"},
            template="T1_portfolio_census",
        )),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.9)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        _run("How many contracts do we have?")

    phases = [s["phase"] for s in agent.get_trace()]
    assert "tool:count_contracts" in phases
    assert "rank_evidence" not in phases  # the out-of-allowlist search_clauses was dropped


def test_unroutable_question_asks_for_clarification() -> None:
    """Planner returns nothing usable, and the question has no keyword/filter
    signal for the deterministic backstop either -> ADR-0004 D3: ask the human,
    never fabricate a plan. Only the plan LLM call happens - no gather, no
    interpret, no draft, no verify."""
    calls = AsyncMock(side_effect=[_resp(agent._Plan())])  # planner returned nothing usable
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("What are the most significant contractual risks across our portfolio?")

    assert result.needs_clarification is True
    assert result.uncertain is True
    assert calls.await_count == 1  # plan only

    trace = agent.get_trace()
    resolved = next(s for s in trace if s["phase"] == "plan_resolved")["output"]
    assert resolved["calls"] == []
    assert not any(s["phase"].startswith("tool:") for s in trace)
    assert not any(s["phase"] in ("draft_answer", "verify") for s in trace)


def test_clarify_gate_stops_asking_and_returns_a_terminal_answer() -> None:
    """clarify_round already at the configured max -> a terminal answer, not
    another question - the loop must terminate."""
    calls = AsyncMock(side_effect=[_resp(agent._Plan())])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run(
            "What are the most significant contractual risks across our portfolio?",
            clarify_round=agent.config.clarify_max_rounds,
        )

    assert result.needs_clarification is False
    assert result.answer == agent._TERMINAL_UNROUTED_TEXT


# ----------------------------------------------------------- degraded-mode router
def test_deterministic_route_maps_questions_to_templates() -> None:
    cases = {
        "How many contracts do we have, by lifecycle status?": ("T1_portfolio_census", ["count_contracts"]),
        "List all nda agreements": ("T2_filtered_roster", ["list_contracts"]),
        "Which contracts mention liability insurance?": ("T3_clause_presence", ["find_contracts"]),
        "What is the total value of our active contracts?": ("T4_financial_rollup", ["aggregate_contracts"]),
        "What are our payment obligations across all contracts?":
            ("T7_cross_contract_synthesis", ["find_contracts", "search_clauses"]),
    }
    for question, (template, tools) in cases.items():
        plan = agent._guard_plan(question, agent._deterministic_route(question, _FACETS), _FACETS)
        assert plan.template == template, question
        assert [c.tool for c in plan.calls] == tools, question


def test_deterministic_route_unknown_question_yields_no_plan() -> None:
    """No keyword, filter, or clause signal -> an empty plan, not a guess.
    _plan()/answer() turn this into a clarification, not a fabricated call."""
    question = "What are the most significant contractual risks across our portfolio?"
    plan = agent._guard_plan(question, agent._deterministic_route(question, _FACETS), _FACETS)
    assert plan.template == ""
    assert plan.calls == []


def test_which_contracts_have_clause_enumerates_completely() -> None:
    contracts = [
        {**CONTRACTS[0], "clauses": [{"heading": "Insurance", "text": "maintain liability insurance"}]},
        {**CONTRACTS[1], "clauses": [{"heading": "Insurance", "text": "carry liability insurance"}]},
        {**CONTRACTS[2], "clauses": [{"heading": "Term", "text": "one year"}]},
    ]
    draft = QueryAnswer(answer="2 contracts require liability insurance.", confidence=0.9, citations=[])
    calls = AsyncMock(side_effect=[  # T3 -> find_contracts only, no snippets, no interpret
        _resp(_plan({"tool": "find_contracts", "query": "liability insurance"}, template="T3_clause_presence")),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.9)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("Which contracts require liability insurance?", contracts)

    find = next(s for s in agent.get_trace() if s["phase"] == "tool:find_contracts")
    assert find["output"]["matched"] == 2
    assert result.answer.startswith("2 contracts")


def test_math_question_uses_tool_computed_value() -> None:
    contracts = [
        {**CONTRACTS[0], "commercial_terms": {"total_value": {"amount": "1000", "currency": "USD"}}},
        {**CONTRACTS[1], "commercial_terms": {"total_value": {"amount": "3000", "currency": "USD"}}},
    ]
    draft = QueryAnswer(answer="The active contracts are worth $4000 in total.", confidence=0.95, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "aggregate_contracts", "measure": "sum_value"}, template="T4_financial_rollup")),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.95)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        _run("What is the total value of our active contracts?", contracts)

    agg = next(s for s in agent.get_trace() if s["phase"] == "tool:aggregate_contracts")
    assert agg["output"]["measure"] == "sum_value"
    assert agg["output"]["value"] == "4000"


# --------------------------------------------------------------------- coverage
def test_coverage_record_flags_a_portfolio_spanning_synthesis() -> None:
    contracts = [
        {**CONTRACTS[0], "clauses": [{"heading": "Payment", "text": f"pay obligation {i}"}]}
        for i in range(40)
    ]
    for i, c in enumerate(contracts):
        c["id"], c["contract_number"] = f"x{i}", f"IMPORT-{i}"
    draft = QueryAnswer(answer="Across the 40 matching contracts (a sample of the evidence): ...", confidence=0.6, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan(
            {"tool": "find_contracts", "query": "payment"},
            {"tool": "search_clauses", "query": "payment"},
            template="T7_cross_contract_synthesis",
        )),
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.6)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        _run("What payment obligations do we have across all contracts?", contracts)

    cov = next(s for s in agent.get_trace() if s["phase"] == "coverage")["memory"]
    assert cov["matched"] == 40 and cov["spans_portfolio"] is True


def test_deterministic_compose_notes_a_capped_list() -> None:
    contracts = []
    for i in range(30):
        contracts.append({
            "id": f"v{i}", "contract_number": f"IMPORT-{i}", "title": f"Vendor {i}",
            "lifecycle_status": "active", "contract_type": "nda",
            "parties": [], "clauses": [], "key_dates": {}, "commercial_terms": {},
        })
    cfg = dataclasses.replace(agent.config, deterministic_compose=True, verify=False)
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "list_contracts", "contract_type": "nda"}, template="T2_filtered_roster")),
    ])
    with patch.object(agent, "config", cfg), patch.object(llm_client, "acompletion", new=calls), \
         patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("List all nda agreements", contracts)

    assert "capped" in result.answer.lower() or "more" in result.answer.lower()
    assert result.uncertain is True


# ------------------------------------------------------------------------- verify
def test_verify_drops_unsupported_citations_and_lowers_confidence() -> None:
    draft = QueryAnswer(
        answer="Payment is annual.", confidence=0.95,
        citations=[{"contract_id": "c1", "label": "clause:Payment", "evidence": "..."}],
    )
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "search_clauses", "query": "payment"}, template="T6_clause_detail")),
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=False, adjusted_confidence=0.2, unsupported_citation_labels=["clause:Payment"])),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("Is payment annual?")

    assert result.citations == []
    assert result.confidence == 0.2 and result.uncertain is True


def test_verify_can_be_disabled() -> None:
    draft = QueryAnswer(answer="ok", confidence=0.6, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "count_contracts"}, template="T1_portfolio_census")), _resp(draft),
    ])
    no_verify = dataclasses.replace(agent.config, verify=False)
    with patch.object(agent, "config", no_verify), patch.object(llm_client, "acompletion", new=calls), patch.object(
        agent, "rank_with_scores", **_RANK
    ):
        result = _run("How many contracts do we have?")

    assert result.answer == "ok" and calls.await_count == 2


def test_no_tenant_contract_raises() -> None:
    with pytest.raises(ValueError, match="No tenant-scoped contract"):
        _run("q", contract_id="other")


def test_full_trace_captures_prompt_and_timing() -> None:
    draft = QueryAnswer(answer="120 contracts.", confidence=0.9, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(agent._Plan(reasoning="census", template="T1_portfolio_census",
                          calls=[agent._ToolCall(tool="count_contracts")])),
        _resp(draft),
        _resp(agent._Verification(reasoning="matches", supported=True, adjusted_confidence=0.9)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        _run("How many contracts and what types do we have?")

    trace = agent.get_trace()
    phases = [s["phase"] for s in trace]
    assert phases[0] == "context"
    for expected in ("plan", "plan_resolved", "tool:count_contracts", "coverage", "draft_answer", "verify", "result"):
        assert expected in phases
    plan_step = next(s for s in trace if s["phase"] == "plan")
    assert plan_step["system_prompt"] == agent._PLAN_PROMPT
    assert plan_step["ms"] is not None
