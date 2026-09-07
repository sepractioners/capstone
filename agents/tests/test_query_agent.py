"""Query agent: plan (tree of thought) -> gather -> interpret -> draft -> verify.

All LLM calls are mocked; the deterministic portfolio tools run for real.
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


def _resp(parsed):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed))])


def _plan(*tools):
    return agent._Plan(calls=[agent._ToolCall(**t) for t in tools])


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


def _run(question, contracts=CONTRACTS, **kw):
    return asyncio.run(answer(question, contracts, **kw))


def test_count_question_routes_to_count_contracts_with_no_retrieval() -> None:
    draft = QueryAnswer(answer="2 contracts are active.", confidence=0.95, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "count_contracts", "lifecycle_status": "active"})),
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
        _resp(_plan({"tool": "search_clauses", "query": "payment terms"})),
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.9)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("What does the payment clause say?")

    assert result.answer.startswith("Customer pays")
    assert calls.await_count == 4
    assert any(s["phase"] == "interpret" for s in agent.get_trace())


def test_mixed_question_emits_both_count_and_search() -> None:
    draft = QueryAnswer(answer="2 active; termination on 30 days notice.", confidence=0.85, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan(
            {"tool": "count_contracts", "lifecycle_status": "active"},
            {"tool": "search_clauses", "query": "termination"},
        )),
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.85)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("How many active contracts and what are their termination terms?")

    phases = [s["phase"] for s in agent.get_trace()]
    assert "tool:count_contracts" in phases and "rank_evidence" in phases
    assert result.answer.startswith("2 active")


def test_which_contracts_have_clause_uses_find_contracts_not_a_sample() -> None:
    contracts = [
        {**CONTRACTS[0], "clauses": [{"heading": "Insurance", "text": "maintain liability insurance"}]},
        {**CONTRACTS[1], "clauses": [{"heading": "Insurance", "text": "carry liability insurance"}]},
        {**CONTRACTS[2], "clauses": [{"heading": "Term", "text": "one year"}]},
    ]
    draft = QueryAnswer(answer="2 contracts require liability insurance.", confidence=0.9, citations=[])
    calls = AsyncMock(side_effect=[
        # planner wrongly picks search_clauses; the guard adds find_contracts
        _resp(_plan({"tool": "search_clauses", "query": "liability insurance"})),
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.9)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("Which contracts require liability insurance?", contracts)

    trace = agent.get_trace()
    find = next(s for s in trace if s["phase"] == "tool:find_contracts")
    assert find["output"]["matched"] == 2
    assert result.answer.startswith("2 contracts")


def test_math_question_routes_to_aggregate_contracts() -> None:
    contracts = [
        {**CONTRACTS[0], "commercial_terms": {"total_value": {"amount": "1000", "currency": "USD"}}},
        {**CONTRACTS[1], "commercial_terms": {"total_value": {"amount": "3000", "currency": "USD"}}},
    ]
    draft = QueryAnswer(answer="The active contracts are worth $4000 in total.", confidence=0.95, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "search_clauses", "query": "value"})),  # planner misses the math need
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.95)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        _run("What is the total value of our active contracts?", contracts)

    agg = next(s for s in agent.get_trace() if s["phase"] == "tool:aggregate_contracts")
    assert agg["output"]["measure"] == "sum_value"
    assert agg["output"]["value"] == "4000"


def test_portfolio_wide_clause_question_enumerates_with_find_contracts() -> None:
    contracts = [
        {**CONTRACTS[0], "clauses": [{"heading": "Payment", "text": "Customer shall make payment within 30 days"}]},
        {**CONTRACTS[1], "clauses": [{"heading": "Payment", "text": "payment due on invoice"}]},
        {**CONTRACTS[2], "clauses": [{"heading": "Term", "text": "one year"}]},
    ]
    draft = QueryAnswer(answer="Two contracts carry payment obligations.", confidence=0.9, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "search_clauses", "query": "payment"})),  # planner picks only search
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.9)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        _run("What are our payment obligations across all contracts?", contracts)

    find = next(s for s in agent.get_trace() if s["phase"] == "tool:find_contracts")
    assert find["output"]["matched"] == 2


def test_keyword_guard_forces_count_when_planner_misses_it() -> None:
    draft = QueryAnswer(answer="ok", confidence=0.7, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "search_clauses", "query": "contracts"})),  # planner wrongly chose search only
        _resp(agent._Interpretation()),
        _resp(draft),
        _resp(agent._Verification(supported=True, adjusted_confidence=0.7)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        _run("How many contracts do we have?")

    assert any(s["phase"] == "tool:count_contracts" for s in agent.get_trace())


def test_plan_failure_falls_back_to_the_default_plan() -> None:
    draft = QueryAnswer(answer="ok", confidence=0.6, citations=[])
    calls = AsyncMock(side_effect=[_resp(None), _resp(agent._Interpretation()), _resp(draft), _resp(None)])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        result = _run("What are the terms and who signed it?")

    assert result.answer == "ok"
    assert any(s["phase"] == "tool:count_contracts" for s in agent.get_trace())


def test_verify_drops_unsupported_citations_and_lowers_confidence() -> None:
    draft = QueryAnswer(
        answer="Payment is annual.", confidence=0.95,
        citations=[{"contract_id": "c1", "label": "clause:Payment", "evidence": "..."}],
    )
    calls = AsyncMock(side_effect=[
        _resp(_plan({"tool": "search_clauses", "query": "payment"})),
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
    calls = AsyncMock(side_effect=[_resp(_plan({"tool": "count_contracts"})), _resp(draft)])
    no_verify = dataclasses.replace(agent.config, verify=False)
    with patch.object(agent, "config", no_verify), patch.object(llm_client, "acompletion", new=calls), patch.object(
        agent, "rank_with_scores", **_RANK
    ):
        result = _run("How many contracts do we have?")

    assert result.answer == "ok" and calls.await_count == 2


def test_no_tenant_contract_raises() -> None:
    with pytest.raises(ValueError, match="No tenant-scoped contract"):
        _run("q", contract_id="other")


def test_full_trace_captures_plan_tools_and_timing() -> None:
    draft = QueryAnswer(answer="120 contracts.", confidence=0.9, citations=[])
    calls = AsyncMock(side_effect=[
        _resp(agent._Plan(reasoning="count branch", calls=[agent._ToolCall(tool="count_contracts")])),
        _resp(draft),
        _resp(agent._Verification(reasoning="matches", supported=True, adjusted_confidence=0.9)),
    ])
    with patch.object(llm_client, "acompletion", new=calls), patch.object(agent, "rank_with_scores", **_RANK):
        _run("How many contracts and what types do we have?")

    trace = agent.get_trace()
    phases = [s["phase"] for s in trace]
    assert phases[0] == "context"
    for expected in ("plan", "plan_resolved", "tool:count_contracts", "draft_answer", "verify", "result"):
        assert expected in phases
    plan_step = next(s for s in trace if s["phase"] == "plan")
    assert plan_step["system_prompt"] == agent._PLAN_PROMPT
    assert plan_step["ms"] is not None
