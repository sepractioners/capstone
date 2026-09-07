"""Deterministic portfolio queries over authorized contract snapshots.

Shared by the read-only query MCP tools (``count_contracts`` / ``list_contracts``
/ ``find_contracts`` / ``aggregate_contracts``) and the query agent's
Tree-of-Thought planner. No LLM and no retrieval - exact answers to "how many",
"which", "list", "total", and "expiring when" questions. All date and money
arithmetic happens here, never in the model.

Every function takes the already tenant-filtered list of contract dicts (the
shape ``ContractMapper.to_dict`` produces) and never touches the database.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from contract_calc import parse_date, to_decimal, total_value as _total_value

Contract = dict[str, Any]

DEFAULT_FULL_MAX = 10
FIND_LIMIT = 200

# A ``where`` filter is a flat dict; every key is optional:
#   lifecycle_status, contract_type, party            (string match)
#   effective_year (int), effective_after, effective_before   (ISO date / date)
#   expiring_within_days (int), expiration_after, expiration_before
#   min_value, max_value                              (number)
Where = dict[str, Any]

_MEASURES = ("count", "sum_value", "avg_value", "min_value", "max_value")
_GROUP_BY = ("lifecycle_status", "contract_type", "party")

# Words carried by the question but never by the clause text being matched.
_MATCH_STOP = {
    "which", "contract", "contracts", "need", "needs", "require", "requires", "required",
    "requiring", "any", "that", "those", "have", "has", "having", "with", "list", "show",
    "all", "does", "do", "our", "the", "are", "there", "for", "clause", "clauses",
    "provision", "provisions", "about", "and", "include", "includes", "including", "some",
}

_FULL_FIELDS = (
    "id", "contract_number", "title", "contract_type", "lifecycle_status", "parties",
    "clauses", "obligations", "key_dates", "commercial_terms", "renewal_terms",
    "termination_terms", "risk_profile", "amendments",
)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _party_names(contract: Contract) -> str:
    return " ".join(_norm(p.get("legal_name", "")) for p in contract.get("parties", []))


def _merge_where(where: Where | None, lifecycle_status: str | None, contract_type: str | None) -> Where:
    merged = dict(where or {})
    if lifecycle_status:
        merged.setdefault("lifecycle_status", lifecycle_status)
    if contract_type:
        merged.setdefault("contract_type", contract_type)
    return merged


def passes_where(contract: Contract, where: Where, *, today: date | None = None) -> bool:
    """True when the contract satisfies every set key in ``where``."""
    if not where:
        return True
    today = today or date.today()

    if (w := where.get("lifecycle_status")) and _norm(contract.get("lifecycle_status")) != _norm(w):
        return False
    if (w := where.get("contract_type")) and _norm(contract.get("contract_type")) != _norm(w):
        return False
    if (w := where.get("party")) and _norm(w) not in _party_names(contract):
        return False

    key_dates = contract.get("key_dates") or {}
    effective = parse_date(key_dates.get("effective_date"))
    expiration = parse_date(key_dates.get("expiration_date"))

    if (year := where.get("effective_year")) is not None:
        if effective is None or effective.year != int(year):
            return False
    if (bound := parse_date(where.get("effective_after"))) and (effective is None or effective < bound):
        return False
    if (bound := parse_date(where.get("effective_before"))) and (effective is None or effective > bound):
        return False

    if (days := where.get("expiring_within_days")) is not None:
        if expiration is None or not (today <= expiration <= today + timedelta(days=int(days))):
            return False
    if (bound := parse_date(where.get("expiration_after"))) and (expiration is None or expiration < bound):
        return False
    if (bound := parse_date(where.get("expiration_before"))) and (expiration is None or expiration > bound):
        return False

    value = _total_value(contract)
    if (floor := to_decimal(where.get("min_value"))) is not None and (value is None or value < floor):
        return False
    if (cap := to_decimal(where.get("max_value"))) is not None and (value is None or value > cap):
        return False
    return True


def _select(contracts: list[Contract], where: Where) -> list[Contract]:
    today = date.today()
    return [c for c in contracts if passes_where(c, where, today=today)]


def _tally(contracts: list[Contract]) -> tuple[dict[str, int], dict[str, int]]:
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for contract in contracts:
        status = str(contract.get("lifecycle_status") or "unknown")
        ctype = str(contract.get("contract_type") or "unclassified")
        by_status[status] = by_status.get(status, 0) + 1
        by_type[ctype] = by_type.get(ctype, 0) + 1
    return (
        dict(sorted(by_status.items(), key=lambda kv: -kv[1])),
        dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
    )


def count_contracts(
    contracts: list[Contract],
    *,
    where: Where | None = None,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
) -> dict[str, Any]:
    """Exact counts. ``matched`` is the count for the filter; the ``by_*``
    breakdowns are always over the whole set."""
    where = _merge_where(where, lifecycle_status, contract_type)
    matched = _select(contracts, where)
    by_status, by_type = _tally(contracts)
    return {
        "total": len(contracts),
        "matched": len(matched),
        "filter": where,
        "by_lifecycle_status": by_status,
        "by_contract_type": by_type,
    }


def _summary(contract: Contract) -> dict[str, Any]:
    key_dates = contract.get("key_dates") or {}
    total_value = (contract.get("commercial_terms") or {}).get("total_value") or {}
    amount = total_value.get("amount")
    return {
        "id": contract.get("id"),
        "contract_number": contract.get("contract_number"),
        "title": contract.get("title"),
        "lifecycle_status": contract.get("lifecycle_status"),
        "contract_type": contract.get("contract_type"),
        "effective_date": key_dates.get("effective_date"),
        "expiration_date": key_dates.get("expiration_date"),
        "total_value": f"{amount} {total_value.get('currency', '')}".strip() if amount else None,
    }


def _full(contract: Contract) -> dict[str, Any]:
    return {field: contract[field] for field in _FULL_FIELDS if field in contract}


def list_contracts(
    contracts: list[Contract],
    *,
    where: Where | None = None,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
    detail: str = "summary",
    full_max: int = DEFAULT_FULL_MAX,
) -> dict[str, Any]:
    """List the matching contracts. ``detail="full"`` returns whole records for a
    small filtered set, else summaries with a note."""
    where = _merge_where(where, lifecycle_status, contract_type)
    matched = _select(contracts, where)
    want_full = str(detail).lower() == "full"
    fell_back = want_full and len(matched) > full_max
    if want_full and not fell_back:
        items, used = [_full(c) for c in matched], "full"
    else:
        items, used = [_summary(c) for c in matched], "summary"
    return {
        "matched": len(matched),
        "detail": used,
        "filter": where,
        "note": (
            f"{len(matched)} contracts matched - showing summaries. Narrow the filter to get "
            f"full detail (max {full_max})."
            if fell_back
            else ""
        ),
        "contracts": items,
    }


def match_terms(text: str) -> list[str]:
    """Content words from a phrase or question, for clause-text matching."""
    return [w for w in re.findall(r"[a-z][a-z-]+", text.lower()) if len(w) > 2 and w not in _MATCH_STOP]


def _contract_text(contract: Contract) -> str:
    parts = [str(contract.get("title") or ""), str(contract.get("contract_type") or "")]
    for clause in contract.get("clauses", []):
        parts.append(f"{clause.get('heading', '')} {clause.get('text', '')}")
    for obligation in contract.get("obligations", []):
        parts.append(
            f"{obligation.get('description', '')} {obligation.get('trigger_event', '')} "
            f"{obligation.get('consequence_of_failure', '')}"
        )
    for field in ("renewal_terms", "termination_terms", "commercial_terms", "risk_profile"):
        if contract.get(field):
            parts.append(json.dumps(contract[field], default=str))
    return " ".join(parts).lower()


def find_contracts(
    contracts: list[Contract],
    *,
    text: str,
    where: Where | None = None,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
    limit: int = FIND_LIMIT,
) -> dict[str, Any]:
    """Every contract whose clause / obligation / term text contains *all* the
    content words in ``text``. Complete enumeration, not a ranked sample."""
    where = _merge_where(where, lifecycle_status, contract_type)
    terms = match_terms(text)
    scoped = _select(contracts, where)
    if not terms:
        return {"matched": 0, "match_terms": [], "query": text, "filter": where, "truncated": False, "contracts": []}

    matched: list[dict[str, Any]] = []
    for contract in scoped:
        blob = _contract_text(contract)
        if not all(term in blob for term in terms):
            continue
        row = _summary(contract)
        row["matched_clauses"] = [
            clause.get("heading")
            for clause in contract.get("clauses", [])
            if any(t in f"{clause.get('heading', '')} {clause.get('text', '')}".lower() for t in terms)
        ][:6]
        matched.append(row)

    return {
        "matched": len(matched),
        "match_terms": terms,
        "query": text,
        "filter": where,
        "truncated": len(matched) > limit,
        "contracts": matched[:limit],
    }


def _measure(group: list[Contract], measure: str) -> str | int | None:
    if measure == "count":
        return len(group)
    values = [v for v in (_total_value(c) for c in group) if v is not None]
    if not values:
        return None
    if measure == "sum_value":
        return str(sum(values))
    if measure == "avg_value":
        return str((sum(values) / len(values)).quantize(Decimal("0.01")))
    if measure == "min_value":
        return str(min(values))
    if measure == "max_value":
        return str(max(values))
    return None


def aggregate_contracts(
    contracts: list[Contract],
    *,
    measure: str = "count",
    group_by: str = "",
    where: Where | None = None,
    lifecycle_status: str | None = None,
    contract_type: str | None = None,
) -> dict[str, Any]:
    """Deterministic count / sum / avg / min / max of contract value over a
    filtered set, optionally grouped. All money math uses Decimal; the model
    never computes."""
    where = _merge_where(where, lifecycle_status, contract_type)
    measure = measure if measure in _MEASURES else "count"
    group_by = group_by if group_by in _GROUP_BY else ""
    matched = _select(contracts, where)

    base = {"measure": measure, "group_by": group_by, "filter": where, "matched": len(matched)}
    if not group_by:
        return {**base, "value": _measure(matched, measure)}

    groups: dict[str, list[Contract]] = {}
    for contract in matched:
        if group_by == "party":
            keys = [p.get("legal_name", "?") for p in contract.get("parties", [])] or ["?"]
        else:
            keys = [str(contract.get(group_by) or "unknown")]
        for key in keys:
            groups.setdefault(key, []).append(contract)

    results = [
        {"group": key, "matched": len(members), "value": _measure(members, measure)}
        for key, members in groups.items()
    ]
    results.sort(key=lambda row: -row["matched"])
    return {**base, "results": results}


def facets(contracts: list[Contract]) -> dict[str, list[str]]:
    """The distinct filter values present, so a planner uses real ones."""
    by_status, by_type = _tally(contracts)
    return {"lifecycle_status": list(by_status), "contract_type": list(by_type)}
