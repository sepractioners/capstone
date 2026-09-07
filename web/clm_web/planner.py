"""Turn a free-form agent request into a bounded, typed execution plan.

The orchestrator used to be a static router on a UI toggle. This planner lets
one message drive a short sequence - e.g. "extract this PDF and tell me how it
compares to our other vendor contracts" becomes extract -> analyze.

Guardrails are deterministic and always applied after the model responds:
- steps are only `extract` or `analyze`,
- `extract` is dropped when there is no attachment,
- the plan is clamped to `PLANNER_MAX_STEPS`,
- a non-actionable message yields a single clarification, no steps.

The LLM call is best-effort: on failure the plan falls back to one step
matching the obvious intent.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Literal

from agent_llm.client import acall
from agent_trace import TraceRecorder
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MAX_STEPS = max(1, int(os.environ.get("PLANNER_MAX_STEPS", "3")))

_PROMPT = (
    "You plan how a contract assistant should handle one user message. The assistant has two "
    "capabilities:\n"
    "- extract: pull a contract from an attached PDF/JSON/CSV into the system (only possible "
    "when a file is attached).\n"
    "- analyze: answer a question over the organization's stored contracts.\n"
    "Return the minimal ordered list of steps (at most 3). Each step's `input` is the "
    "instruction or question for that step. If the message is a greeting or otherwise not an "
    "actionable request, set intent_ok=false and give a short clarification instead. "
    "Return only the schema."
)


class PlanStep(BaseModel):
    op: Literal["extract", "analyze"]
    input: str = ""


class Plan(BaseModel):
    reasoning: str = ""
    intent_ok: bool = True
    clarification: str = ""
    steps: list[PlanStep] = Field(default_factory=list)


def _guard(plan: Plan, message: str, has_attachment: bool) -> Plan:
    if not plan.intent_ok and plan.clarification.strip():
        return Plan(intent_ok=False, clarification=plan.clarification.strip(), steps=[])
    steps = [step for step in plan.steps if step.op in ("extract", "analyze")]
    if not has_attachment:
        steps = [step for step in steps if step.op != "extract"]
    steps = steps[:MAX_STEPS]
    if not steps:
        steps = [PlanStep(op="extract" if has_attachment else "analyze", input=message)]
    return Plan(intent_ok=True, reasoning=plan.reasoning, steps=steps)


async def plan(message: str, has_attachment: bool) -> tuple[Plan, list[dict[str, Any]]]:
    """Produce a guarded execution plan for one agent message, plus its trace."""
    rec = TraceRecorder("planner")
    fallback = Plan(steps=[PlanStep(op="extract" if has_attachment else "analyze", input=message)])
    parsed, note = await acall(
        "planner", _PROMPT, {"message": message, "has_attachment": has_attachment}, schema=Plan, recorder=rec, phase="plan"
    )
    if not isinstance(parsed, Plan):
        logger.warning("planner call failed (%s); using fallback plan", note or "no plan")
        return fallback, rec.steps
    return _guard(parsed, message, has_attachment), rec.steps
