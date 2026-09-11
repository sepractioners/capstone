"""Deterministic subsystem probe for the query agent.

Loads the seeded portfolio straight from ``clm.sqlite3`` (the same tenant-scoped
load the query MCP uses), runs one or every benchmark question through
``query_agent.agent.answer()`` at an explicit, recorded config, and writes a
report containing, per question:

- the **resolved plan** (tools + filters) and its diff against the fixture's
  ``expect_plan`` — a deterministic routing score even though a model may have
  produced the plan, because the plan is structured output;
- every deterministic tool result (count / list / find / aggregate);
- every LLM call: system prompt, exact context in, raw + parsed output, timing,
  error;
- the final answer and its verdict against the fixture ground truth.

No API server. Re-running with the same config + model yields an identical plan
and identical tool results when ``QUERY_PLAN_TOOLS=0``; with the LLM planner on,
the plan varies with the model and the report says so.

    uv run python -m platform_testing.probe.query_agent_probe --question q14_portfolio_risk_summary
    uv run python -m platform_testing.probe.query_agent_probe --all --plan-tools 0

Writes ``platform_testing/reports/query-probe-<UTC stamp>.{json,md}``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent.parent / "fixtures" / "query_bench_questions.jsonl"
REPORT_DIR = Path(__file__).parent.parent / "reports"

_LLM_PHASES = {"plan", "interpret", "draft_answer", "verify"}
_FAIL_MARKERS = ("unavailable", "remoteprotocolerror", "traceback", "validationerror", "timeouterror")


# --------------------------------------------------------------------------- scoring
def score_answer(question: dict[str, Any], answer: str) -> str:
    """fail | wrong | pass — same contract as query_bench.py::_score."""
    low = answer.lower()
    if not answer.strip() or any(m in low for m in _FAIL_MARKERS):
        return "fail"
    if question.get("reject_regex") and re.search(question["reject_regex"], low):
        return "wrong"
    if question.get("min_len") and len(low) < question["min_len"]:
        return "wrong"
    if any(s not in low for s in question.get("expect_all", [])):
        return "wrong"
    if question.get("expect_regex") and not re.search(question["expect_regex"], low):
        return "wrong"
    return "pass"


_WHERE_KEYS = (
    "lifecycle_status", "contract_type", "party", "effective_year",
    "expiring_within_days", "min_value", "max_value",
)


def _plan_call_shape(call: dict[str, Any]) -> dict[str, Any]:
    filters = {k: call[k] for k in _WHERE_KEYS if call.get(k) not in ("", None)}
    shape: dict[str, Any] = {"tool": call.get("tool"), "filters": filters}
    if call.get("query"):
        shape["query"] = call["query"]
    if call.get("measure"):
        shape["measure"] = call["measure"]
    if call.get("group_by"):
        shape["group_by"] = call["group_by"]
    return shape


def _resolved_plan(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    step = next((s for s in reversed(trace) if s["phase"] == "plan_resolved"), None)
    if step is None or not step.get("output"):
        return []
    return [_plan_call_shape(c) for c in step["output"].get("calls", [])]


def score_plan(expect: list[dict[str, Any]] | None, resolved: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare the resolved plan to the fixture's expect_plan (order-independent).

    ``expect`` entries need only the keys they care about — a bare
    ``{"tool": "find_contracts"}`` matches any find_contracts call.
    """
    if expect is None:
        return {"scored": False}
    got_tools = sorted(c["tool"] for c in resolved)
    want_tools = sorted(e["tool"] for e in expect)
    matched = []
    for want in expect:
        hit = next(
            (c for c in resolved if c["tool"] == want["tool"]
             and all(c.get(k) == v for k, v in want.items() if k != "tool")),
            None,
        )
        matched.append(hit is not None)
    return {
        "scored": True,
        "verdict": "match" if all(matched) and got_tools == want_tools else
                   ("partial" if any(matched) else "miss"),
        "expected": expect,
        "resolved": resolved,
    }


# --------------------------------------------------------------------------- run
def _llm_calls(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls = []
    for s in trace:
        if s["phase"] not in _LLM_PHASES:
            continue
        if not s.get("system_prompt") and not s.get("model"):
            continue  # a "skipped"/"disabled" marker, not an actual call
        calls.append({
            "phase": s["phase"],
            "model": s.get("model", ""),
            "provider": s.get("provider", ""),
            "ms": s.get("ms"),
            "note": s.get("note", ""),
            "system_prompt": s.get("system_prompt", ""),
            "input": (s.get("context") or {}).get("user"),
            "output": s.get("output"),
            "output_raw": s.get("output_raw", ""),
        })
    return calls


def _tool_results(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"phase": s["phase"], "context": s.get("context"), "output": s.get("output")}
        for s in trace if s["phase"].startswith("tool:")
    ]


async def _run_one(question: dict[str, Any], contracts: list[dict[str, Any]]) -> dict[str, Any]:
    from query_agent.agent import answer, get_trace

    err = None
    answer_json = None
    try:
        result = await answer(question["question"], contracts)
        answer_json = result.model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - keep the partial trace
        err = f"{type(exc).__name__}: {exc}"

    trace = get_trace()
    resolved = _resolved_plan(trace)
    answer_text = (answer_json or {}).get("answer", "") if answer_json else ""
    return {
        "id": question["id"],
        "question": question["question"],
        "class": question.get("class", ""),
        "error": err,
        "answer": answer_json,
        "answer_verdict": score_answer(question, answer_text) if not err else "fail",
        "plan": score_plan(question.get("expect_plan"), resolved),
        "llm_calls": _llm_calls(trace),
        "tool_results": _tool_results(trace),
        "step_trace": trace,
    }


def _load_questions() -> list[dict[str, Any]]:
    return [json.loads(l) for l in FIXTURE.read_text(encoding="utf-8").splitlines() if l.strip()]


def _write_reports(bundle: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = REPORT_DIR / f"query-probe-{stamp}.json"
    json_path.write_text(json.dumps(bundle, indent=2, default=str), encoding="utf-8")

    cfg = bundle["config"]
    lines = [
        f"# Query-agent probe — {bundle['generated_at']}",
        "",
        f"model `{cfg['model']}` · provider `{cfg['provider']}` · temp {cfg['temperature']} · "
        f"plan_tools={cfg['plan_tools']} interpret={cfg['interpret']} verify={cfg['verify']} "
        f"deterministic_compose={cfg['deterministic_compose']}",
        f"org `{cfg['org']}` · {cfg['contracts_in_scope']} contracts · fixture `{FIXTURE.name}`",
        "",
        "| question | answer | plan | LLM calls | wall |",
        "|---|---|---|---|---|",
    ]
    for row in bundle["rows"]:
        plan = row["plan"]
        plan_cell = plan["verdict"] if plan.get("scored") else "—"
        calls = row["llm_calls"]
        ms = sum(c["ms"] or 0 for c in calls)
        lines.append(
            f"| {row['id']} | {row['answer_verdict']} | {plan_cell} | "
            f"{len(calls)} | {ms/1000:.1f}s |"
        )
    lines.append("")

    for row in bundle["rows"]:
        lines += [f"## {row['id']}", "", f"> {row['question']}", ""]
        if row["error"]:
            lines += [f"**error:** `{row['error']}`", ""]
        plan = row["plan"]
        lines.append("**Resolved plan:**")
        lines.append("```json")
        lines.append(json.dumps(plan.get("resolved", []), indent=2))
        lines.append("```")
        if plan.get("scored"):
            lines.append(f"plan verdict: **{plan['verdict']}** (expected: `{json.dumps(plan['expected'])}`)")
        lines.append("")
        for c in row["llm_calls"]:
            lines += [
                f"### LLM · {c['phase']}  ({c['model']}, {c['ms']}ms{', ' + c['note'] if c['note'] else ''})",
                "",
                "<details><summary>system prompt</summary>", "",
                "```", c["system_prompt"], "```", "", "</details>", "",
                "**input:**", "```json", json.dumps(c["input"], indent=2, default=str)[:4000], "```", "",
                "**output (parsed):**", "```json", json.dumps(c["output"], indent=2, default=str)[:4000], "```", "",
            ]
            if c["output_raw"]:
                lines += ["**output (raw):**", "```", c["output_raw"][:4000], "```", ""]
        if row["answer"]:
            lines += ["**final answer:**", "```json", json.dumps(row["answer"], indent=2), "```", ""]
    (REPORT_DIR / f"query-probe-{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
    return json_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--question", help="fixture question id (default: all)")
    parser.add_argument("--all", action="store_true", help="run every fixture question")
    parser.add_argument("--org", required=True,
                        help="organization id — every load, filter and retrieval is scoped to it")
    parser.add_argument("--db", default=os.environ.get("CLM_DATABASE_PATH", "clm.sqlite3"))
    parser.add_argument("--model", help="override LLM_MODEL for this run")
    parser.add_argument("--plan-tools", choices=["0", "1"], help="override QUERY_PLAN_TOOLS")
    args = parser.parse_args()

    # Config is frozen at import — set env before importing query_agent.
    if args.model:
        os.environ["LLM_MODEL"] = args.model
    if args.plan_tools is not None:
        os.environ["QUERY_PLAN_TOOLS"] = args.plan_tools

    questions = _load_questions()
    if not args.all:
        if not args.question:
            parser.error("give --question <id> or --all")
        questions = [q for q in questions if q["id"] == args.question]
        if not questions:
            parser.error(f"no fixture question with id {args.question!r}")

    from clm_mcp_core.dependencies import build_dependencies
    from clm_mcp_core.tenant_contracts import contracts_for_organization
    from query_agent.config import config

    deps = build_dependencies(args.db)
    contracts = contracts_for_organization(deps, args.db, args.org)

    print(f"probe: {len(questions)} question(s) · model={config.model} · "
          f"plan_tools={config.plan_tools} · {len(contracts)} contracts", flush=True)

    rows = []
    for q in questions:
        print(f"  {q['id']:32} ...", end="", flush=True)
        row = asyncio.run(_run_one(q, contracts))
        print(f" answer={row['answer_verdict']:5} plan="
              f"{row['plan'].get('verdict', '-'):7} llm={len(row['llm_calls'])}", flush=True)
        rows.append(row)

    bundle = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "model": config.model, "provider": config.provider, "temperature": config.temperature,
            "plan_tools": config.plan_tools, "interpret": config.interpret, "verify": config.verify,
            "deterministic_compose": config.deterministic_compose,
            "org": args.org, "db": args.db, "contracts_in_scope": len(contracts),
        },
        "rows": rows,
    }
    path = _write_reports(bundle)
    passed = sum(1 for r in rows if r["answer_verdict"] == "pass")
    plan_ok = sum(1 for r in rows if r["plan"].get("verdict") == "match")
    plan_scored = sum(1 for r in rows if r["plan"].get("scored"))
    print(f"\nanswer {passed}/{len(rows)} pass · plan {plan_ok}/{plan_scored} match")
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
