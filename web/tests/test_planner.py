"""Planner guardrails + best-effort LLM call."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from clm_web import planner
from clm_web.planner import Plan, PlanStep, _guard, plan


def test_guard_drops_extract_steps_without_an_attachment() -> None:
    raw = Plan(steps=[PlanStep(op="extract", input="x"), PlanStep(op="analyze", input="compare")])
    guarded = _guard(raw, "compare", has_attachment=False)
    assert [step.op for step in guarded.steps] == ["analyze"]


def test_guard_clamps_to_max_steps() -> None:
    raw = Plan(steps=[PlanStep(op="analyze", input=str(i)) for i in range(9)])
    guarded = _guard(raw, "m", has_attachment=False)
    assert len(guarded.steps) == planner.MAX_STEPS


def test_guard_falls_back_to_one_step_when_empty() -> None:
    guarded = _guard(Plan(steps=[]), "just a question", has_attachment=False)
    assert guarded.steps == [PlanStep(op="analyze", input="just a question")]


def test_guard_passes_through_a_clarification() -> None:
    raw = Plan(intent_ok=False, clarification="What would you like me to do?", steps=[])
    guarded = _guard(raw, "hi", has_attachment=False)
    assert guarded.intent_ok is False and guarded.steps == []


def test_plan_falls_back_when_the_model_call_fails() -> None:
    with patch("agent_llm.client.acompletion", new=AsyncMock(side_effect=RuntimeError("down"))):
        result, _ = asyncio.run(plan("extract this and summarize", has_attachment=True))
    assert result.steps == [PlanStep(op="extract", input="extract this and summarize")]


def test_plan_uses_and_guards_a_model_plan() -> None:
    model_plan = Plan(steps=[PlanStep(op="extract", input="ingest the file"), PlanStep(op="analyze", input="compare to vendor contracts")])
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=model_plan))])
    with patch("agent_llm.client.acompletion", new=AsyncMock(return_value=response)):
        result, _ = asyncio.run(plan("extract and compare", has_attachment=True))
    assert [step.op for step in result.steps] == ["extract", "analyze"]
