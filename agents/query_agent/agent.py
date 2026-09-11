"""Tenant-scoped, provider-agnostic contract analysis agent.

Reasoning shape: **plan -> gather -> interpret -> coverage -> draft -> verify.**

Routing is spec-driven (ADR-0006): ``_plan`` has the LLM planner name one
**prompt template** (``prompts/templates.yaml``) per question, which fixes the
tools it may use; ``_guard_plan`` does filter-value hygiene and allowlist
enforcement only - no tool selection. If the planner is unavailable or names
nothing usable, ``_plan`` tries deterministic keyword + facet routing
(``_deterministic_route``) as a backstop. If *neither* projects the question
onto a template, ``answer()`` does not fabricate a plan - it asks the human for
clarification, bounded by ``config.clarify_max_rounds``.

- ``count_contracts`` / ``list_contracts`` / ``aggregate_contracts`` -
  deterministic portfolio queries (exact counts, filtered rosters, value math).
  No LLM, no retrieval.
- ``find_contracts`` - complete phrase enumeration over clause/obligation text.
- ``search_clauses`` - embedding-ranked clause/obligation snippets.

``_gather`` runs every planned call, then ``_interpret`` (clause branch only),
``_coverage`` records matched-vs-read, ``_draft_answer`` synthesises (or
``_compose_deterministic`` templates a structural answer with no LLM call), and
``_verify`` checks it - including that a partial-coverage answer doesn't claim
completeness.

Two bounded, in-request self-correction loops sit inside this pipeline (not to
be confused with the cross-turn clarification loop above, which needs a human
reply on the next turn): if a synthesis-mode template's ``_gather`` comes back
with zero clause text, ``answer()`` replans once with that gap named
(``config.gather_replan_max_rounds``); if ``_verify`` flags an unsupported
claim, ``answer()`` redrafts once with the specific labels named
(``config.draft_reverify_max_rounds``). Both exhaust to today's existing safe
behaviour unchanged - never a third attempt, never worse than not looping at
all.

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

from agent_llm import prompts
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
    needs_clarification: bool = False  # the question didn't project onto a template - answer is a question back
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
    template: str = ""  # the named prompt template (see templates.yaml); fixes the tool allowlist
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
TEMPLATES_PATH = Path(__file__).parent / "prompts" / "templates.yaml"


def _load_templates() -> tuple[dict[str, dict[str, Any]], str]:
    """The routing spec (`templates.yaml`): id -> {tools, cues, scaffold, ...}
    plus the fallback template id. See agents/query_agent/docs/prompt-templates.md."""
    import yaml

    spec = yaml.safe_load(TEMPLATES_PATH.read_text(encoding="utf-8")) or {}
    return spec.get("templates", {}) or {}, spec.get("fallback", "") or ""


_TEMPLATES, _FALLBACK_TEMPLATE = _load_templates()
_TEMPLATE_TOOLS: dict[str, set[str]] = {
    tid: set(t.get("tools", []) or []) for tid, t in _TEMPLATES.items()
}
# Templates whose YAML `mode` includes "S" need real clause text to answer -
# a plan that never calls search_clauses for one of these has nothing to
# synthesise from. Used only to decide whether a thin gather() is worth one
# bounded replan (see _gather_needs_evidence below) - not a tool-selection
# decision, just reading a property the spec already declares.
_TEMPLATE_NEEDS_EVIDENCE: set[str] = {
    tid for tid, t in _TEMPLATES.items() if "S" in (t.get("mode") or "").split()
}


def _plan_prompt() -> str:
    """Build the planner system prompt from the template catalogue so the two
    never drift. The model names one template; that fixes its tool allowlist."""
    lines = [
        "Route a contract question. First name the single `template` whose cues best "
        f"fit the question; then emit one tool call per distinct need (1 to "
        f"{config.max_tool_calls}) using ONLY that template's tools. If nothing fits, "
        f"use `{_FALLBACK_TEMPLATE}`.",
        "",
        "Every tool call is scoped to the caller's organization. Counts, sums and "
        "date arithmetic are done by the tools - never compute a number or a date yourself.",
        "",
        "FILTERS: the user message carries `facets` = the lifecycle_status and "
        "contract_type values that exist in this organization's portfolio. When the "
        "question names one, copy the exact facet string ('vendor-agreement', not "
        "'vendor agreements') onto every filterable call. Other filters: party, "
        "effective_year, expiring_within_days (90 for 'next quarter' - never compute a "
        "date), min_value / max_value.",
        "",
        "If the user message carries `prior_attempt_gap`, this is a replan: your first "
        "plan for this same question missed something. Fix that specific gap - do not "
        "just repeat the same calls.",
        "",
        "Templates:",
    ]
    for tid, t in _TEMPLATES.items():
        tools = ", ".join(t.get("tools", []) or []) or "(no tools)"
        lines.append(f"- {tid}  [tools: {tools}]")
        scaffold = " ".join((t.get("scaffold") or "").split())
        if scaffold:
            lines.append(f"    {scaffold}")
        cues = t.get("cues", []) or []
        if cues:
            lines.append(f"    cues: {' | '.join(str(c) for c in cues[:3])}")
    lines += ["", "Return only the schema: {template, reasoning, calls}."]
    return "\n".join(lines)


_PLAN_PROMPT = _plan_prompt()
_VERIFY_PROMPT = (
    "Check the drafted answer against the supplied data. The `counts`, `contract_lists`, and "
    "`aggregates` blocks are deterministic platform facts and are authoritative for numbers, "
    "totals, and enumeration - a claim matching them is supported (a citation with "
    "contract_id 'portfolio' is valid). Other claims must be backed by the cited evidence. "
    "When a `counts` block has a non-empty `filter`, the count answer MUST equal its "
    "`matched` value - a number taken from `by_lifecycle_status` / `by_contract_type` while "
    "a filter is set is unsupported (those breakdowns ignore the filter). Likewise a "
    "`contract_lists` answer must use its `matched`. "
    "Set supported=false if the answer contradicts those blocks, uses an unfiltered "
    "breakdown where `matched` applies, or the evidence does not back a clause-level claim. "
    "COVERAGE: when `coverage.spans_portfolio` is true the answer was built from a sample "
    "of a larger matched set - an answer that implies it covers every matching contract "
    "('all our contracts', 'every contract', 'the portfolio as a whole') without saying it "
    "read a sample is unsupported; it must state the fraction read and offer the exact "
    "count or a narrower filter. "
    "List the labels of any citations nothing supports. Give a calibrated confidence in "
    "[0,1]. Return only the schema."
)
_INTERPRET_PROMPT = (
    "You are reading tenant-scoped contract evidence to build an explicit model before "
    "answering. Every field below is filled ONLY from the evidence you were given - if the "
    "evidence array is short or covers only one topic, your output must be short and cover "
    "only that topic too. An empty list is a correct answer when the evidence supports "
    "nothing.\n"
    "- obligations: each commitment, the responsible party, the event that triggers it, the "
    "consequence the text attaches to non-performance (empty if unstated), and any deadline.\n"
    "- rights: each right or option a party holds, what triggers it, and its effect.\n"
    "- what_matters: the points that most affect risk or money - but ONLY ones a specific "
    "evidence entry actually states. Before adding a point, find the exact evidence entry "
    "it comes from; if you cannot name one, drop the point. Do not add a point because it is "
    "a common contract risk in general - severity and category come from what the text says, "
    "not from your prior knowledge of what contracts like this usually contain.\n"
    "Do not invent terms the evidence does not contain. Return only the schema."
)


def _system_prompt() -> str:
    return prompts.load(PROMPT_PATH)


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


def _history_clarify_floor(history: Any) -> int:
    """Backstop clarification-round count for a caller that doesn't pass
    ``clarify_round`` explicitly: count trailing assistant turns that read as a
    clarification question (ends in "?"), stopping at the first assistant turn
    that doesn't. A real caller should pass ``clarify_round``; this only bounds
    the loop when it can't."""
    if not history:
        return 0
    rounds = 0
    for turn in reversed(list(history)):
        role = getattr(turn, "role", None) or (turn.get("role") if isinstance(turn, dict) else "")
        if role != "assistant":
            continue
        text = str(getattr(turn, "text", None) or (turn.get("text") if isinstance(turn, dict) else "") or "")
        if not text.strip().endswith("?"):
            break
        rounds += 1
    return rounds


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


_SEP_RE = re.compile(r"[-_]+")


def _slug_match(needle: str, haystack: str) -> bool:
    """True when a facet value appears in the question regardless of how the
    two spell a multi-word value - ``co-branding-agreement`` / ``co branding
    agreements`` / ``in_review`` / ``in review`` all resolve. The facet form is
    the exact value stored on the contract; the question keeps its own hyphens
    and plurals, so normalise both to spaced, singular tokens before matching."""
    n = _SEP_RE.sub(" ", needle.lower()).strip()
    h = _SEP_RE.sub(" ", haystack.lower())
    if not n:
        return False
    if n in h:
        return True
    # tolerate a trailing plural on the last word ("agreements" vs "agreement")
    return bool(re.search(rf"(?:^|\s){re.escape(n)}s?(?:$|\s)", h))


def _infer_where(question: str, facets: dict[str, list[str]]) -> dict[str, Any]:
    lowered = question.lower()
    where: dict[str, Any] = {}
    status = next((s for s in facets.get("lifecycle_status", []) if s and _slug_match(s, question)), "")
    if status:
        where["lifecycle_status"] = status
    ctype = next((t for t in facets.get("contract_type", []) if t and _slug_match(t, question)), "")
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


_CLAUSE_PHRASE_RE = re.compile(
    r"\b(?:mention|mentions|require|requires|contain|contains|include|includes|have|has|with|about)\s+"
    r"(?:an?\s+|any\s+|the\s+|explicit\s+|a\s+)*"
    r"([a-z][a-z\- ]{2,40}?)"
    r"(?=\s*(?:\?|$|[,.;]|\bclause|\bprovision|\bobligation|\bterm))",
    re.I,
)


_PHRASE_STOP_RE = re.compile(
    r"\b(all|any|our|its|their|contracts?|agreements?|deals?|portfolio|across|every|them|we|us|do)\b",
    re.I,
)


def _clause_query(question: str, clause_hit: re.Match[str]) -> str:
    """The phrase to search clause/obligation text for. Prefer the words the
    question actually names ('liability insurance') over the first bare keyword
    the clause regex happened to hit ('liabilit'), but fall back when the
    captured phrase is question filler ('across all contracts')."""
    match = _CLAUSE_PHRASE_RE.search(question)
    if match:
        phrase = re.sub(r"^(?:a|an|any|the|our)\s+", "", match.group(1).strip(), flags=re.I).strip()
        if len(phrase) >= 3 and not _PHRASE_STOP_RE.search(phrase):
            return phrase
    return clause_hit.group(0)


_FILTERABLE_TOOLS = {"count_contracts", "list_contracts", "find_contracts", "aggregate_contracts"}


def _deterministic_route(question: str, facets: dict[str, list[str]]) -> _Plan:
    """Keyword + facet routing for the deterministic templates - no model. This
    is the ``QUERY_PLAN_TOOLS=0`` degraded router (ADR-0006 D4) AND the backstop
    tried when the LLM planner is unavailable or names no usable calls. A
    question with no keyword, filter, or clause signal returns an *empty* plan -
    ``_plan`` does not invent one; ``answer()`` asks the human instead (bounded
    clarification loop, ADR-0006 D3).
    """
    where = _infer_where(question, facets)

    def _mk(tool: str, **extra: Any) -> _ToolCall:
        return _ToolCall(tool=tool, **dict(where), **extra)

    clause_hit = _CLAUSE_RE.search(question)
    is_list = bool(_LIST_RE.search(question))
    scoped = bool(_SCOPE_RE.search(question))
    enumerate_clause = bool(clause_hit) and (is_list or scoped)

    calls: list[_ToolCall] = []
    template = ""
    if enumerate_clause:
        calls.append(_mk("find_contracts", query=_clause_query(question, clause_hit)))
        template = "T3_clause_presence"
        if scoped:  # portfolio-wide clause question -> also gather evidence to synthesise
            calls.append(_ToolCall(tool="search_clauses", query=question))
            template = "T7_cross_contract_synthesis"
    elif _MATH_RE.search(question):
        measure = "avg_value" if re.search(r"\b(average|avg|mean)\b", question, re.I) else "sum_value"
        group_by = "contract_type" if re.search(r"\bby (?:type|contract type)\b", question, re.I) else ""
        calls.append(_mk("aggregate_contracts", measure=measure, group_by=group_by))
        template = "T4_financial_rollup"
    elif _COUNT_RE.search(question):
        calls.append(_mk("count_contracts"))
        template = "T1_portfolio_census"
    elif is_list or where:
        calls.append(_mk("list_contracts"))
        template = "T2_filtered_roster"
    elif clause_hit:
        calls.append(_ToolCall(tool="search_clauses", query=question))
        template = "T6_clause_detail"

    return _Plan(reasoning="deterministic keyword routing (degraded mode)", template=template, calls=calls)


def _guard_plan(question: str, plan: _Plan, facets: dict[str, list[str]]) -> _Plan:
    """Filter-value hygiene + template-allowlist enforcement only. No tool
    selection and no fabricated plan.

    - fill any filter key a call left empty from the deterministic parse (facet
      spelling, relative dates, value bounds) - the planner picks tools, the
      parse owns the scope;
    - drop any call whose tool is not in the named template's allowlist.

    A plan with no calls after this (planner declined, timed out, or named a
    template but emitted nothing usable) is returned as-is - empty. Nothing here
    guesses a tool or a search phrase on the caller's behalf; ``_plan`` tries the
    deterministic backstop next, and ``answer()`` asks the human if that is also
    empty (ADR-0006 D3).
    """
    where = _infer_where(question, facets)
    allow = _TEMPLATE_TOOLS.get(plan.template)  # None -> unknown / blank template, allow anything

    kept: list[_ToolCall] = []
    for call in plan.calls[: config.max_tool_calls]:
        if allow is not None and call.tool not in allow:
            continue
        if call.tool in _FILTERABLE_TOOLS:
            for key, value in where.items():
                if getattr(call, key, "") in ("", None):
                    setattr(call, key, value)
        kept.append(call)

    return _Plan(template=plan.template, reasoning=plan.reasoning, calls=kept[: config.max_tool_calls])


async def _plan(
    question: str,
    history_text: str,
    facets: dict[str, list[str]],
    rec: TraceRecorder,
    feedback: str = "",
) -> _Plan:
    """LLM planner first (unless degraded mode); if it produced no usable calls
    - disabled, timed out, or named a template but emitted nothing - try the
    deterministic backstop. Either way this can return an empty plan; that is
    not an error, it means the question did not project onto any template.

    ``feedback``: set only on a bounded replan round (see answer()) - names a
    gap in the *previous* round's gather result ("you got match counts but no
    clause text"), never a tool to call. Empty on the first round."""
    guarded = _Plan()
    if config.plan_tools:
        user: dict[str, Any] = {"question": question, "conversation": history_text, "facets": facets}
        if feedback:
            user["prior_attempt_gap"] = feedback
        parsed = await _call(
            _PLAN_PROMPT,
            user,
            _Plan,
            rec,
            "plan",
            timeout=config.fast_timeout_seconds,
        )
        if isinstance(parsed, _Plan):
            guarded = _guard_plan(question, parsed, facets)

    if not guarded.calls:
        backstop = _guard_plan(question, _deterministic_route(question, facets), facets)
        rec.record(
            "plan_backstop",
            output=backstop.model_dump(mode="json"),
            note="degraded mode - QUERY_PLAN_TOOLS=0, deterministic routing" if not config.plan_tools
            else "planner produced no usable calls - tried deterministic routing",
        )
        if backstop.calls:
            guarded = backstop
    return guarded


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


_DRAFT_LIST_ROWS = 15
_BREAKDOWN_RE = re.compile(r"\bby (?:lifecycle )?(?:status|type|contract type)\b|\bbreak ?down\b|\beach (?:status|type)\b", re.I)
_STATUS_WORD_RE = re.compile(r"\bstatus\b", re.I)
_NAME_LIMIT = 12


def _row_name(row: dict[str, Any]) -> str:
    return str(row.get("title") or row.get("contract_number") or row.get("id") or "?")


def _compose_deterministic(question: str, gathered: dict[str, Any], coverage: dict[str, Any] | None = None) -> QueryAnswer | None:
    """Template an answer straight from tool output. Returns None when the
    question needs language-model synthesis (no structured results, or the
    caller gathered clause snippets). Structural questions - count, filtered
    count, list, breakdown, enumerate-by-phrase, aggregate - are a pure
    function of what Retrieve produced; the LLM only reformats a number there,
    and that is the step that fails on a small model."""
    if gathered.get("snippets"):
        return None
    counts = gathered.get("counts") or []
    lists = gathered.get("lists") or []
    aggregates = gathered.get("aggregates") or []
    if not (counts or lists or aggregates):
        return None

    parts: list[str] = []
    cites: list[Citation] = []
    capped = False

    for c in counts:
        flt = c.get("filter") or {}
        if flt:
            parts.append(f"{c['matched']} contract(s) match {_fmt_filter(flt)}.")
            cites.append(Citation(contract_id="portfolio", label="count.matched",
                                  evidence=f"{c['matched']} (filter: {_fmt_filter(flt)})"))
        elif _BREAKDOWN_RE.search(question):
            book = c.get("by_lifecycle_status") if _STATUS_WORD_RE.search(question) or "lifecycle" in question.lower() else c.get("by_contract_type")
            book = book or c.get("by_lifecycle_status") or c.get("by_contract_type") or {}
            body = ", ".join(f"{k} {v}" for k, v in book.items())
            parts.append(f"{c.get('total', sum(book.values()))} contracts total: {body}.")
            cites.append(Citation(contract_id="portfolio", label="count.breakdown", evidence=body))
        else:
            parts.append(f"{c.get('total', c.get('matched'))} contracts in total.")
            cites.append(Citation(contract_id="portfolio", label="count.total", evidence=str(c.get("total", c.get("matched")))))

    for lst in lists:
        rows = lst.get("contracts") or []
        matched_n = int(lst.get("matched", len(rows)) or 0)
        names = [_row_name(r) for r in rows[:_NAME_LIMIT]]
        shortfall = max(len(rows), matched_n) - len(names)
        more = "" if shortfall <= 0 else f", and {shortfall} more"
        if shortfall > 0 or lst.get("truncated"):
            capped = True
        terms = lst.get("match_terms")
        if terms:
            label, kind = "find_contracts.matched", f" mention {' + '.join(terms)}"
        else:
            label, kind = "contract_lists.matched", " match the filter" if lst.get("filter") else ""
        listing = f": {'; '.join(names)}{more}" if names else ""
        parts.append(f"{lst.get('matched', len(rows))} contract(s){kind}{listing}.")
        cites.append(Citation(contract_id="portfolio", label=label, evidence=str(lst.get("matched", len(rows)))))

    for agg in aggregates:
        results = agg.get("results")
        if results:
            body = ", ".join(f"{r['group']}: {r['value']}" for r in results)
            parts.append(f"{agg['measure']} by {agg.get('group_by')}: {body}.")
            cites.append(Citation(contract_id="portfolio", label=f"aggregate.{agg['measure']}", evidence=body))
        else:
            parts.append(f"{agg['measure']}: {agg.get('value')}.")
            cites.append(Citation(contract_id="portfolio", label=f"aggregate.{agg['measure']}", evidence=str(agg.get("value"))))

    if not parts:
        return None
    partial = capped or bool(coverage and coverage.get("truncated"))
    if partial:
        parts.append("This list is capped - ask for a narrower filter or the full set for every match.")
    return QueryAnswer(answer=" ".join(parts), confidence=0.9, uncertain=partial, citations=cites)


def _fmt_filter(flt: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v}" for k, v in flt.items())


def _trim_lists_for_draft(lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the authoritative `matched` count and a bounded sample of rows. A
    small model drowns in 20+ full rows and answers nothing; the count is what
    an enumeration question actually needs, plus enough names to be concrete."""
    trimmed: list[dict[str, Any]] = []
    for block in lists:
        rows = block.get("contracts", []) or []
        sample = [
            {k: r.get(k) for k in ("contract_number", "title", "lifecycle_status", "contract_type")}
            for r in rows[:_DRAFT_LIST_ROWS]
        ]
        trimmed.append({
            "matched": block.get("matched"),
            "match_terms": block.get("match_terms"),
            "filter": block.get("filter"),
            "truncated": block.get("truncated") or len(rows) > _DRAFT_LIST_ROWS,
            "contracts": sample,
        })
    return trimmed


_TERMINAL_UNROUTED_TEXT = (
    "I still can't determine how to answer that. I can help with contract counts and "
    "breakdowns, filtered lists, clause lookups by topic, value totals, and obligation "
    "due dates - try phrasing your question around one of those."
)


def _clarification_text(facets: dict[str, list[str]]) -> str:
    """A targeted narrowing question grounded in the portfolio's real facet
    values - not a generic "please rephrase"."""
    statuses = ", ".join(facets.get("lifecycle_status", [])[:6])
    types = ", ".join(facets.get("contract_type", [])[:8])
    parts = ["I couldn't determine how to answer that from the portfolio. Could you narrow it"]
    hints = []
    if types:
        hints.append(f"by contract type ({types})")
    if statuses:
        hints.append(f"status ({statuses})")
    hints += ["a party name", "a clause topic (e.g. indemnification, termination, insurance)",
              "or a time window (e.g. 'expiring in 90 days')"]
    return parts[0] + " - " + ", ".join(hints) + "?"


def _unrouted_response(
    facets: dict[str, list[str]], history: Any, clarify_round: int, rec: TraceRecorder
) -> QueryAnswer:
    """Neither the LLM planner nor deterministic routing could project the
    question onto a template. Never fabricate a plan (ADR-0006 D3): ask the
    human, bounded by `clarify_max_rounds` on both the caller-supplied
    `clarify_round` and a history-derived floor (defence in depth if the caller
    doesn't track rounds itself)."""
    rounds = max(clarify_round, _history_clarify_floor(history))
    if rounds >= config.clarify_max_rounds:
        answer = QueryAnswer(answer=_TERMINAL_UNROUTED_TEXT, confidence=0.3, uncertain=True)
        note = f"clarify round gate reached ({rounds}/{config.clarify_max_rounds}) - terminal, not asking again"
    else:
        answer = QueryAnswer(answer=_clarification_text(facets), confidence=0.3, uncertain=True,
                             needs_clarification=True)
        note = f"question did not project onto a template (round {rounds}) - asking for clarification"
    rec.record("clarify", note=note, output=answer.model_dump(mode="json"))
    return answer


def _coverage(gathered: dict[str, Any]) -> dict[str, Any]:
    """How much of the matched set the answer actually rests on. When a synthesis
    is built from top-K evidence over a larger matched set, the answer must say
    so (`spans_portfolio`) and offer the exact count / a narrower filter."""
    matched = 0
    listing_truncated = False
    for lst in gathered.get("lists") or []:
        m = int(lst.get("matched") or 0)
        matched = max(matched, m)
        rows = lst.get("contracts") or []
        if lst.get("truncated") or (m and len(rows) < m):
            listing_truncated = True
    evidence_fed = len(gathered.get("snippets") or [])
    spans = evidence_fed > 0 and matched > _DRAFT_LIST_ROWS
    return {
        "matched": matched,
        "evidence_fed": evidence_fed,
        "names_shown": min(matched, _NAME_LIMIT) if matched else 0,
        "truncated": bool(listing_truncated or spans),
        "spans_portfolio": bool(spans),
    }


async def _draft_answer(
    question: str,
    history_text: str,
    gathered: dict[str, Any],
    interpretation: _Interpretation | None,
    coverage: dict[str, Any],
    rec: TraceRecorder,
    feedback: str = "",
) -> QueryAnswer:
    """``feedback``: set only on a bounded redraft round (see answer()) - the
    specific unsupported claims/labels verify() flagged in the *previous*
    draft. Empty on the first round."""
    user: dict[str, Any] = {
        "question": question,
        "conversation": history_text,
        "counts": gathered["counts"],
        "contract_lists": _trim_lists_for_draft(gathered["lists"]),
        "aggregates": gathered["aggregates"],
        "evidence": gathered["snippets"][: config.evidence_budget],
        "interpretation": _interpretation_view(interpretation),
        "coverage": coverage,
    }
    if feedback:
        user["prior_attempt_unsupported"] = feedback
    parsed = await _call(
        _system_prompt(),
        user,
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
    coverage: dict[str, Any],
    rec: TraceRecorder,
) -> tuple[QueryAnswer, _Verification | None]:
    """Returns ``(verified_answer, raw_verification)``. The raw ``_Verification``
    is what answer() checks to decide whether a bounded redraft is worth trying
    (config.draft_reverify_max_rounds) - the adjusted QueryAnswer alone doesn't
    expose ``supported`` / ``unsupported_citation_labels``. ``None`` when verify
    didn't return a usable result (unchanged from before: the draft ships as-is)."""
    cited = [c.model_dump() for c in draft.citations]
    parsed = await _call(
        _VERIFY_PROMPT,
        {
            "question": question,
            "answer": draft.answer,
            "citations": cited,
            "counts": gathered["counts"],
            "contract_lists": _trim_lists_for_draft(gathered["lists"]),
            "aggregates": gathered["aggregates"],
            "interpretation": _interpretation_view(interpretation),
            "coverage": coverage,
        },
        _Verification,
        rec,
        "verify",
    )
    if not isinstance(parsed, _Verification):
        return draft, None
    unsupported = {label.lower() for label in parsed.unsupported_citation_labels}
    kept = [c for c in draft.citations if c.label.lower() not in unsupported]
    verified = draft.model_copy(
        update={
            "citations": kept,
            "confidence": round(min(draft.confidence, parsed.adjusted_confidence), 3),
            "uncertain": draft.uncertain or not parsed.supported or (bool(draft.citations) and not kept),
        }
    )
    return verified, parsed


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
    clarify_round: int = 0,
) -> QueryAnswer:
    """Retrieve tenant-scoped evidence and reason to a cited answer.

    ``clarify_round``: how many consecutive clarification turns the caller has
    already had on this conversation (0 for a fresh question). The orchestrator
    is the primary owner of this count and should stop calling the agent past
    ``config.clarify_max_rounds``; the agent enforces the same bound itself as a
    second gate (ADR-0006 D3)."""
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

    if not plan.calls:
        result = _unrouted_response(facets, history, clarify_round, rec)
        rec.record("result", output=result.model_dump(mode="json"))
        return result

    embed_cache: dict[str, list[float]] = {}
    gathered = await _gather(question, plan, selected, all_records, embed_cache, rec)

    # Bounded self-correction 1/2: a template whose mode needs real synthesis
    # (S) but whose gather() came back with zero clause text has nothing to
    # synthesise from - replan once with that gap named, never more than
    # config.gather_replan_max_rounds times. Exhausted -> proceed exactly as
    # before (interpret skips itself, the existing safety net composes a safe,
    # honest, thinner answer). Never a third, fourth, ... attempt.
    replan_round = 0
    while (
        plan.template in _TEMPLATE_NEEDS_EVIDENCE
        and not gathered["snippets"]
        and replan_round < config.gather_replan_max_rounds
    ):
        replan_round += 1
        gap = (
            f"Your previous plan named template {plan.template} and gathered match "
            "counts (find_contracts / list_contracts) but zero clause text - no "
            "search_clauses call returned evidence. This template needs real clause "
            "text to answer, not only match counts."
        )
        plan = await _plan(question, history_text, facets, rec, feedback=gap)
        rec.record(
            "plan_resolved",
            output=plan.model_dump(mode="json"),
            reasoning=plan.reasoning,
            note=f"replan round {replan_round}/{config.gather_replan_max_rounds} - "
            "prior gather had 0 clause snippets for an S-mode template",
        )
        if not plan.calls:
            result = _unrouted_response(facets, history, clarify_round, rec)
            rec.record("result", output=result.model_dump(mode="json"))
            return result
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

    coverage = _coverage(gathered)
    rec.record("coverage", memory=coverage)

    draft = _compose_deterministic(question, gathered, coverage) if config.deterministic_compose else None
    if draft is not None:
        # Deterministic compose is already grounded 1:1 in tool output - no
        # redraft loop here, there is no LLM draft to correct.
        rec.record("draft_answer", note="deterministic compose - structural question, no clause evidence",
                   output=draft.model_dump(mode="json"))
        if config.verify:
            verified, _verification = await _verify(question, draft, gathered, interpretation, coverage, rec)
        else:
            verified = draft
            rec.record("verify", note="skipped - QUERY_VERIFY=0")
    else:
        draft = await _draft_answer(question, history_text, gathered, interpretation, coverage, rec)
        if not config.verify:
            verified = draft
            rec.record("verify", note="skipped - QUERY_VERIFY=0")
        else:
            verified, verification = await _verify(question, draft, gathered, interpretation, coverage, rec)
            # Bounded self-correction 2/2: verify flagged an unsupported claim -
            # redraft once with the specific labels named, never more than
            # config.draft_reverify_max_rounds times. Exhausted -> ship the last
            # draft with the existing confidence-capping unchanged (_verify()
            # already applies min(draft.confidence, adjusted_confidence) on
            # every round, including this last one).
            redraft_round = 0
            while (
                verification is not None
                and (not verification.supported or verification.unsupported_citation_labels)
                and redraft_round < config.draft_reverify_max_rounds
            ):
                redraft_round += 1
                labels = ", ".join(verification.unsupported_citation_labels) or "the flagged claim(s)"
                gap = (
                    "Your previous answer made claims not backed by the supplied data - "
                    f"unsupported: {labels}. Remove or fix exactly those claims; keep "
                    "everything else that was already supported."
                )
                draft = await _draft_answer(
                    question, history_text, gathered, interpretation, coverage, rec, feedback=gap
                )
                verified, verification = await _verify(question, draft, gathered, interpretation, coverage, rec)

    rec.record("result", output=verified.model_dump(mode="json"))
    return verified
