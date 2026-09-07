"""Tenant-scoped, provider-agnostic contract analysis agent.

Reasoning shape: **plan (tree of thought) -> gather -> interpret -> draft -> verify.**

One question can carry several distinct information needs at once - a count, a
filtered list, and a clause lookup. ``_plan`` branches on the *kinds* of question
present and emits one tool call per need:

- ``count_contracts`` / ``list_contracts`` - deterministic portfolio queries
  (exact counts, filtered rosters, whole contract records). No LLM, no retrieval.
- ``search_clauses`` - embedding-ranked clause/obligation snippets.

Deterministic keyword guards add a count/list call the planner missed. ``_gather``
runs every call, then ``_interpret`` (clause branch only), ``_draft_answer``
synthesises across all results, and ``_verify`` checks it.

Every step is recorded to a ``TraceRecorder`` (system prompt, exact context,
parsed output, reasoning, retrieval detail, timing); ``get_trace()`` returns it
for the caller to persist. The query agent runs one request per subprocess, so
the last trace is safe to keep in a module global.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Literal

import yaml
from agent_llm.client import acall
from agent_trace import TraceRecorder
from contract_calc import parse_money, resolve_timeframe_days
from pydantic import BaseModel, Field

from . import portfolio
from .config import config
from .evidence import flatten_contract_evidence
from .retrieval import rank_with_scores

logger = logging.getLogger(__name__)

_last_trace: list[dict[str, Any]] = []


def get_trace() -> list[dict[str, Any]]:
    """Full step trace of the most recent ``answer()`` call in this process."""
    return _last_trace


class Citation(BaseModel):
    contract_id: str
    label: str
    evidence: str


class QueryAnswer(BaseModel):
    answer: str
    confidence: float = Field(ge=0, le=1)
    uncertain: bool = False
    citations: list[Citation] = Field(default_factory=list)


class _ToolCall(BaseModel):
    """One information need the planner routes to a deterministic or search tool."""

    tool: Literal[
        "count_contracts", "list_contracts", "find_contracts", "aggregate_contracts", "search_clauses"
    ]
    # filters (a where clause) - all optional
    lifecycle_status: str = ""
    contract_type: str = ""
    party: str = ""
    effective_year: int | None = None
    expiring_within_days: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    # aggregate_contracts
    measure: Literal["", "count", "sum_value", "avg_value", "min_value", "max_value"] = ""
    group_by: Literal["", "lifecycle_status", "contract_type", "party"] = ""
    # list_contracts
    detail: Literal["summary", "full"] = "summary"
    # find_contracts / search_clauses
    query: str = ""

    def where(self) -> dict[str, Any]:
        keys = ("lifecycle_status", "contract_type", "party", "effective_year",
                "expiring_within_days", "min_value", "max_value")
        return {k: getattr(self, k) for k in keys if getattr(self, k) not in ("", None)}


class _Plan(BaseModel):
    reasoning: str = ""  # the tree: which kinds of question this is
    calls: list[_ToolCall] = Field(default_factory=list)


class _Verification(BaseModel):
    reasoning: str = ""
    supported: bool = True
    adjusted_confidence: float = Field(default=0.5, ge=0, le=1)
    unsupported_citation_labels: list[str] = Field(default_factory=list)
    note: str = ""


class _ObligationReading(BaseModel):
    party: str = ""
    obligation: str = ""
    trigger: str = ""
    consequence: str = ""
    deadline: str = ""


class _RightReading(BaseModel):
    party: str = ""
    right: str = ""
    trigger: str = ""
    consequence: str = ""


class _MaterialPoint(BaseModel):
    point: str = ""
    why: str = ""
    severity: Literal["high", "medium", "low"] = "medium"


class _Interpretation(BaseModel):
    reasoning: str = ""
    obligations: list[_ObligationReading] = Field(default_factory=list)
    rights: list[_RightReading] = Field(default_factory=list)
    what_matters: list[_MaterialPoint] = Field(default_factory=list)


PROMPT_PATH = Path(__file__).parent / "prompts" / "contract_query.yaml"

_PLAN_PROMPT = (
    "You route a contract question to data tools. One question often has several needs at "
    "once - resolve every one of them. Emit one call per distinct need (1 to 5). Every tool "
    "shares an optional filter: lifecycle_status, contract_type (use the exact facet values "
    "given), party (a counterparty name), effective_year, expiring_within_days (e.g. 90 for "
    "'next quarter' - never compute a date yourself), min_value / max_value.\n"
    "- COUNT ('how many active', 'how many NDAs signed in 2024') -> count_contracts.\n"
    "- LIST ('which contracts expire in the next quarter', 'list our active vendor "
    "agreements', 'show every co-branding deal') -> list_contracts. detail='full' only for a "
    "small tightly filtered set.\n"
    "- WHICH-HAVE-CLAUSE / PORTFOLIO-WIDE CLAUSE ('which contracts require liability "
    "insurance', 'do any have a non-compete', 'what are our payment obligations across all "
    "contracts') -> find_contracts, `query` = the key phrase only ('liability insurance', "
    "'payment'). Scans EVERY contract - use it, not search_clauses, for the full matching "
    "set.\n"
    "- MATH ('total value of active contracts', 'average value by contract type', 'how much "
    "do we pay Acme') -> aggregate_contracts, measure = count|sum_value|avg_value|min_value|"
    "max_value, group_by optional (lifecycle_status|contract_type|party). The tool does the "
    "arithmetic.\n"
    "- CLAUSE DETAIL for one/few contracts ('what does the indemnity clause say', 'explain "
    "the termination terms in the Acme deal') -> search_clauses with a focused query.\n"
    "Every call must use one of the five tool names. Return only the schema."
)
_VERIFY_PROMPT = (
    "Check the drafted answer against the supplied data. The `counts`, `contract_lists`, and "
    "`aggregates` blocks are deterministic platform facts and are authoritative for numbers, "
    "totals, and enumeration - a claim matching them is supported (a citation with "
    "contract_id 'portfolio' is valid). Other claims must be backed by the cited evidence. "
    "Set supported=false only if the answer contradicts those blocks or the evidence does "
    "not back a clause-level claim. List the labels of any citations nothing supports. Give "
    "a calibrated confidence in [0,1]. Return only the schema."
)
_INTERPRET_PROMPT = (
    "You are reading tenant-scoped contract evidence to build an explicit model before "
    "answering. From the evidence only:\n"
    "- obligations: each commitment, the responsible party, the event that triggers it, the "
    "consequence the text attaches to non-performance (empty if unstated), and any deadline.\n"
    "- rights: each right or option a party holds, what triggers it, and its effect.\n"
    "- what_matters: the few points that most affect risk or money (near deadlines, "
    "unilateral termination rights, auto-renewal lock-in, uncapped liability, penalties), "
    "each with a one-line why and a severity.\n"
    "Do not invent terms the evidence does not contain. Return only the schema."
)


def _system_prompt() -> str:
    with PROMPT_PATH.open(encoding="utf-8") as prompt_file:
        return yaml.safe_load(prompt_file)["system_prompt"]


def _history_text(history: Any) -> str:
    """Bounded, text-only conversation context - never evidence or reasoning."""
    if not history:
        return ""
    turns = []
    for turn in list(history)[-8:]:
        role = getattr(turn, "role", None) or (turn.get("role") if isinstance(turn, dict) else "user")
        text = getattr(turn, "text", None) or (turn.get("text") if isinstance(turn, dict) else "")
        if text:
            turns.append(f"{role}: {str(text)[:600]}")
    return "\n".join(turns)


async def _call(
    system: str,
    user: dict[str, Any],
    schema: type[BaseModel],
    rec: TraceRecorder,
    phase: str,
    *,
    timeout: float | None = None,
) -> BaseModel | None:
    parsed, _note = await acall(
        "query",
        system,
        user,
        schema=schema,
        recorder=rec,
        phase=phase,
        context_extra={"response_format": schema.__name__},
        timeout=timeout,
    )
    return parsed if isinstance(parsed, BaseModel) else None


_COUNT_RE = re.compile(r"\b(how many|number of|count of|total number|# of)\b", re.I)
_LIST_RE = re.compile(
    r"\b(list|which|show (?:me )?(?:all|every|the)|show all|enumerate|find (?:all|every)|"
    r"do any|does any|are there any|what (?:contracts|agreements|deals))\b",
    re.I,
)
_SCOPE_RE = re.compile(r"\b(all|every|across|each|our|portfolio|company-wide)\b", re.I)
_MATH_RE = re.compile(
    r"\b(total\s+(?:\w+\s+){0,2}value|combined value|aggregate value|sum of|"
    r"(?:average|avg|mean)\s+(?:\w+\s+){0,2}value|"
    r"how much (?:do|does|are|is|have) we|total spend|total (?:contract )?worth)\b",
    re.I,
)
_CLAUSE_RE = re.compile(
    r"\b(clause|obligation|indemnif|liabilit|insur|terminat|renew|non-?compete|"
    r"payment|warrant|confidential|audit right|governing law|notice period|cure period|"
    r"what does|say about)",
    re.I,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_OVER_RE = re.compile(r"\b(over|above|more than|greater than|at least|exceed(?:ing|s)?|worth (?:over|more than))\b", re.I)


def _infer_where(question: str, facets: dict[str, list[str]]) -> dict[str, Any]:
    lowered = question.lower()
    where: dict[str, Any] = {}
    status = next((s for s in facets.get("lifecycle_status", []) if s and s in lowered), "")
    if status:
        where["lifecycle_status"] = status
    ctype = next((t for t in facets.get("contract_type", []) if t and t.replace("-", " ") in lowered), "")
    if ctype:
        where["contract_type"] = ctype
    year = _YEAR_RE.search(question)
    if year and re.search(r"\b(signed|executed|effective|dated|in|from|after|since)\b", lowered):
        where["effective_year"] = int(year.group(0))
    days = resolve_timeframe_days(question)
    if days and re.search(r"\b(expir|renew|end|terminat|lapse)\w*", lowered):
        where["expiring_within_days"] = days
    if _OVER_RE.search(lowered):
        amount = parse_money(question)
        if amount:
            where["min_value"] = float(amount)
    return where


def _default_plan(question: str, facets: dict[str, list[str]]) -> _Plan:
    """Deterministic plan when the planner is disabled or returns nothing -
    same keyword routing as the guard, from an empty plan."""
    return _guard_plan(question, _Plan(reasoning="deterministic keyword routing"), facets, seeded=True)


def _guard_plan(question: str, plan: _Plan, facets: dict[str, list[str]], *, seeded: bool = False) -> _Plan:
    """Add the deterministic call the planner obviously missed (or, when ``seeded``,
    build the whole plan from keywords)."""
    calls = list(plan.calls[: config.max_tool_calls])
    tools = {c.tool for c in calls}
    where = _infer_where(question, facets)

    def _mk(tool: str, **extra: Any) -> _ToolCall:
        return _ToolCall(tool=tool, **dict(where), **extra)

    clause_hit = _CLAUSE_RE.search(question)
    is_list = bool(_LIST_RE.search(question))
    enumerate_clause = bool(clause_hit) and (is_list or bool(_SCOPE_RE.search(question)))

    if enumerate_clause and "find_contracts" not in tools:
        calls.append(_mk("find_contracts", query=clause_hit.group(0)))
        tools.add("find_contracts")

    if _MATH_RE.search(question) and "aggregate_contracts" not in tools:
        measure = "avg_value" if re.search(r"\b(average|avg|mean)\b", question, re.I) else "sum_value"
        group_by = "contract_type" if re.search(r"\bby (?:type|contract type)\b", question, re.I) else ""
        calls.append(_mk("aggregate_contracts", measure=measure, group_by=group_by))
        tools.add("aggregate_contracts")

    if _COUNT_RE.search(question) and "count_contracts" not in tools:
        calls.insert(0, _mk("count_contracts"))
        tools.add("count_contracts")

    # A "which / show / find" question, or any filter parsed from the text, is an
    # enumeration - list the matching contracts.
    wants_list = (is_list or bool(where)) and not enumerate_clause
    if wants_list and not tools & {"list_contracts", "count_contracts", "aggregate_contracts"}:
        calls.append(_mk("list_contracts"))
        tools.add("list_contracts")

    if not calls:
        fallback = "search_clauses" if clause_hit else "count_contracts"
        calls = [_ToolCall(tool="search_clauses", query=question) if clause_hit else _mk("count_contracts")]
        tools.add(fallback)

    # A clause search adds representative detail. Skip it for a pure "which
    # contracts have <clause>" (already enumerated) or a purely structural
    # count / list / math / filter question with no clause angle.
    pure_enumeration = enumerate_clause and not _SCOPE_RE.search(question) and len(calls) == 1
    structural_only = not clause_hit and (
        bool(_COUNT_RE.search(question) or _MATH_RE.search(question))
        or (is_list and not enumerate_clause)
        or bool(where)
    )
    if "search_clauses" not in tools and not pure_enumeration and not structural_only:
        calls.append(_ToolCall(tool="search_clauses", query=question))

    return _Plan(reasoning=plan.reasoning, calls=calls[: config.max_tool_calls])


async def _plan(question: str, history_text: str, facets: dict[str, list[str]], rec: TraceRecorder) -> _Plan:
    if not config.plan_tools:
        plan = _default_plan(question, facets)
        rec.record("plan", context={"question": question}, output=plan.model_dump(mode="json"), note="planner disabled - QUERY_PLAN_TOOLS=0")
        return plan
    parsed = await _call(
        _PLAN_PROMPT,
        {"question": question, "conversation": history_text, "facets": facets},
        _Plan,
        rec,
        "plan",
        timeout=config.fast_timeout_seconds,
    )
    return _guard_plan(question, parsed if isinstance(parsed, _Plan) else _Plan(), facets)


async def _gather(
    question: str,
    plan: _Plan,
    contracts: list[dict[str, Any]],
    all_records: list[dict[str, str]],
    embed_cache: dict[str, list[float]],
    rec: TraceRecorder,
) -> dict[str, Any]:
    """Run every planned tool call. Deterministic tools first, then retrieval."""
    counts: list[dict[str, Any]] = []
    lists: list[dict[str, Any]] = []
    aggregates: list[dict[str, Any]] = []
    snippets: list[dict[str, str]] = []
    seen: set[str] = set()
    for call in plan.calls:
        where = call.where()
        if call.tool in ("search_clauses", "find_contracts"):
            key = f"{call.tool}:{call.query.strip().lower()}"
        elif call.tool == "aggregate_contracts":
            key = f"aggregate:{call.measure}:{call.group_by}:{sorted(where.items())}"
        else:
            key = f"{call.tool}:{call.detail}:{sorted(where.items())}"
        if key in seen:
            continue
        seen.add(key)

        if call.tool == "count_contracts":
            result = portfolio.count_contracts(contracts, where=where)
            rec.record("tool:count_contracts", context={"filter": result["filter"]}, output=result)
            counts.append(result)
        elif call.tool == "list_contracts":
            result = portfolio.list_contracts(
                contracts, where=where, detail=call.detail, full_max=config.list_full_max
            )
            rec.record(
                "tool:list_contracts",
                context={"filter": result["filter"], "detail": result["detail"]},
                output={**result, "contracts": result["contracts"][:50]},
            )
            lists.append(result)
        elif call.tool == "find_contracts":
            result = portfolio.find_contracts(contracts, text=call.query or question, where=where)
            rec.record(
                "tool:find_contracts",
                context={"query": result["query"], "match_terms": result["match_terms"], "filter": result["filter"]},
                output={**result, "contracts": result["contracts"][:60]},
            )
            lists.append(result)
        elif call.tool == "aggregate_contracts":
            result = portfolio.aggregate_contracts(
                contracts, measure=call.measure or "count", group_by=call.group_by, where=where
            )
            rec.record(
                "tool:aggregate_contracts",
                context={"measure": result["measure"], "group_by": result["group_by"], "filter": result["filter"]},
                output=result,
            )
            aggregates.append(result)
        elif call.tool == "search_clauses":
            snippets = _merge_evidence(snippets, _rank(call.query or question, all_records, embed_cache, rec))
    return {"counts": counts, "lists": lists, "aggregates": aggregates, "snippets": snippets}


async def _interpret(
    question: str, evidence: list[dict[str, str]], rec: TraceRecorder
) -> _Interpretation | None:
    """Build the trigger -> consequence -> what-matters model before drafting.

    Best-effort: a failure is recorded and returns None; the answer still lands.
    """
    parsed = await _call(
        _INTERPRET_PROMPT,
        {"question": question, "evidence": evidence},
        _Interpretation,
        rec,
        "interpret",
        timeout=config.fast_timeout_seconds,
    )
    return parsed if isinstance(parsed, _Interpretation) else None


def _interpretation_view(interpretation: _Interpretation | None) -> dict[str, Any] | None:
    return interpretation.model_dump(mode="json") if interpretation is not None else None


async def _draft_answer(
    question: str,
    history_text: str,
    gathered: dict[str, Any],
    interpretation: _Interpretation | None,
    rec: TraceRecorder,
) -> QueryAnswer:
    parsed = await _call(
        _system_prompt(),
        {
            "question": question,
            "conversation": history_text,
            "counts": gathered["counts"],
            "contract_lists": gathered["lists"],
            "aggregates": gathered["aggregates"],
            "evidence": gathered["snippets"][: config.evidence_budget],
            "interpretation": _interpretation_view(interpretation),
        },
        QueryAnswer,
        rec,
        "draft_answer",
    )
    if parsed is None:
        raise RuntimeError("Query agent returned no structured answer")
    return parsed  # type: ignore[return-value]


async def _verify(
    question: str,
    draft: QueryAnswer,
    gathered: dict[str, Any],
    interpretation: _Interpretation | None,
    rec: TraceRecorder,
) -> QueryAnswer:
    cited = [c.model_dump() for c in draft.citations]
    parsed = await _call(
        _VERIFY_PROMPT,
        {
            "question": question,
            "answer": draft.answer,
            "citations": cited,
            "counts": gathered["counts"],
            "contract_lists": gathered["lists"],
            "aggregates": gathered["aggregates"],
            "interpretation": _interpretation_view(interpretation),
        },
        _Verification,
        rec,
        "verify",
    )
    if not isinstance(parsed, _Verification):
        return draft
    unsupported = {label.lower() for label in parsed.unsupported_citation_labels}
    kept = [c for c in draft.citations if c.label.lower() not in unsupported]
    return draft.model_copy(
        update={
            "citations": kept,
            "confidence": round(min(draft.confidence, parsed.adjusted_confidence), 3),
            "uncertain": draft.uncertain or not parsed.supported or (bool(draft.citations) and not kept),
        }
    )


def _merge_evidence(current: list[dict[str, str]], new: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = {(r["contract_id"], r["label"], r["evidence"]) for r in current}
    merged = list(current)
    for record in new:
        key = (record["contract_id"], record["label"], record["evidence"])
        if key not in seen:
            seen.add(key)
            merged.append(record)
    return merged[: config.evidence_budget]


def _rank(
    query: str,
    records: list[dict[str, str]],
    cache: dict[str, list[float]],
    rec: TraceRecorder,
) -> list[dict[str, str]]:
    started = rec.start()
    ranked, meta = rank_with_scores(query, records, config.search_k, cache)
    rec.record(
        "rank_evidence",
        context={"query": query},
        retrieval={
            **meta,
            "results": [
                {"score": score, "contract_id": r["contract_id"], "label": r["label"], "evidence": r["evidence"][:400]}
                for score, r in ranked
            ],
        },
        started=started,
    )
    return [record for _score, record in ranked]


async def answer(
    question: str,
    contracts: list[dict[str, Any]],
    contract_id: str | None = None,
    history: Any = None,
) -> QueryAnswer:
    """Retrieve tenant-scoped evidence and reason to a cited answer."""
    global _last_trace
    rec = TraceRecorder("query")
    _last_trace = rec.steps

    selected = [c for c in contracts if not contract_id or c.get("id") == contract_id]
    if not selected:
        raise ValueError("No tenant-scoped contract matched the query")

    history_text = _history_text(history)
    all_records = [record for contract in selected for record in flatten_contract_evidence(contract)]
    facets = portfolio.facets(selected)
    rec.record(
        "context",
        context={
            "question": question,
            "contract_id": contract_id,
            "contracts_in_scope": len(selected),
            "conversation_history": history_text,
            "evidence_records_available": len(all_records),
            "facets": facets,
        },
        memory={"history_turns": history_text.count(chr(10)) + 1 if history_text else 0},
    )

    plan = await _plan(question, history_text, facets, rec)
    rec.record("plan_resolved", output=plan.model_dump(mode="json"), reasoning=plan.reasoning)

    embed_cache: dict[str, list[float]] = {}
    gathered = await _gather(question, plan, selected, all_records, embed_cache, rec)

    scratchpad: dict[str, Any] = {
        "tool_calls": [c.model_dump(exclude_defaults=True) for c in plan.calls],
        "count_results": len(gathered["counts"]),
        "list_results": len(gathered["lists"]),
        "aggregate_results": len(gathered["aggregates"]),
        "evidence_labels": [r["label"] for r in gathered["snippets"]],
    }

    snippets = gathered["snippets"][: config.evidence_budget]
    interpretation = await _interpret(question, snippets, rec) if (config.interpret and snippets) else None
    if config.interpret and not snippets:
        rec.record("interpret", note="skipped - no clause evidence gathered")
    elif not config.interpret:
        rec.record("interpret", note="skipped - QUERY_INTERPRET=0")
    scratchpad["what_matters"] = [m.point for m in interpretation.what_matters] if interpretation else []
    rec.record("scratchpad", memory=scratchpad)

    draft = await _draft_answer(question, history_text, gathered, interpretation, rec)
    verified = await _verify(question, draft, gathered, interpretation, rec) if config.verify else draft
    if not config.verify:
        rec.record("verify", note="skipped - QUERY_VERIFY=0")
    rec.record("result", output=verified.model_dump(mode="json"))
    return verified
