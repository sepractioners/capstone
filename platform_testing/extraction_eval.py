"""Field-level extraction accuracy against a ground-truth JSONL.

Runs the real extraction pipeline (load -> extract -> review, no ingest) over a
directory of PDFs and scores each field against expectations. Only fields that
are present in the ground-truth record are scored; ``null`` means "not
evaluated". Writes a JSON + Markdown report to ``platform_testing/reports/``.

    python -m platform_testing.extraction_eval --limit 8

Ground-truth JSONL record:
    {"filename": "...", "title": "...", "parties": ["...", "..."],
     "contract_type": "affiliate-agreement", "effective_date": "2001-05-15",
     "expiration_date": null, "clause_count": 12}
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extraction_agent.pipeline import acandidates

FIELDS = ("title", "parties", "contract_type", "effective_date", "expiration_date", "clause_count")
# Committed offline fixture (8 CC BY 4.0 CUAD contracts) so the eval runs without
# the opt-in CUAD download. Point --data-dir at synthetic_data_loader/data/cuad_subset
# for the larger local set.
DEFAULT_DATA_DIR = Path(__file__).parent / "fixtures" / "cuad_pdf"
DEFAULT_TRUTH = Path(__file__).parent / "fixtures" / "cuad_ground_truth.jsonl"
REPORT_DIR = Path(__file__).parent / "reports"


def _norm(text: str) -> set[str]:
    return {token for token in "".join(c.lower() if c.isalnum() else " " for c in text).split() if token}


def _f1(predicted: set[str], expected: set[str]) -> float:
    if not predicted and not expected:
        return 1.0
    if not predicted or not expected:
        return 0.0
    overlap = len(predicted & expected)
    precision = overlap / len(predicted)
    recall = overlap / len(expected)
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def score_field(field: str, predicted: Any, expected: Any) -> float:
    """Return a 0..1 score for one field. ``expected is None`` -> not scored."""
    if expected is None:
        return -1.0
    if field == "title":
        return _f1(_norm(str(predicted or "")), _norm(str(expected)))
    if field == "parties":
        pred = {frozenset(_norm(name)) for name in (predicted or [])}
        exp = {frozenset(_norm(name)) for name in expected}
        matched = sum(1 for e in exp if any(e & p for p in pred))
        recall = matched / len(exp) if exp else 1.0
        precision = matched / len(pred) if pred else 0.0
        return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    if field == "contract_type":
        return 1.0 if str(predicted or "").strip().lower() == str(expected).strip().lower() else 0.0
    if field in ("effective_date", "expiration_date"):
        return 1.0 if str(predicted or "")[:10] == str(expected)[:10] else 0.0
    if field == "clause_count":
        predicted, expected = int(predicted or 0), int(expected)
        if expected == 0:
            return 1.0 if predicted == 0 else 0.0
        return max(0.0, 1.0 - abs(predicted - expected) / expected)
    return -1.0


def _candidate_fields(candidate: Any) -> dict[str, Any]:
    return {
        "title": candidate.title,
        "parties": [party.legal_name for party in candidate.parties],
        "contract_type": candidate.contract_type,
        "effective_date": candidate.key_dates.effective_date,
        "expiration_date": candidate.key_dates.expiration_date,
        "clause_count": len(candidate.clauses),
    }


async def _run_one(pdf_path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    try:
        candidates = await acandidates(str(pdf_path))
    except Exception as exc:  # noqa: BLE001 - record the failure, keep going
        return {"filename": pdf_path.name, "error": type(exc).__name__, "scores": {}}
    if not candidates:
        return {"filename": pdf_path.name, "error": "no_candidate", "scores": {}}
    predicted = _candidate_fields(candidates[0])
    scores = {field: score_field(field, predicted.get(field), expected.get(field)) for field in FIELDS}
    return {
        "filename": pdf_path.name,
        "predicted": {k: str(v) for k, v in predicted.items()},
        "scores": {field: value for field, value in scores.items() if value >= 0},
        "requires_human_confirmation": any(
            f.severity == "blocker" for f in candidates[0].review_findings
        ),
    }


def _load_truth(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate(data_dir: Path, truth_path: Path, limit: int) -> dict[str, Any]:
    truth = _load_truth(truth_path)[:limit]
    rows = []
    for record in truth:
        pdf_path = data_dir / record["filename"]
        if not pdf_path.exists():
            rows.append({"filename": record["filename"], "error": "pdf_missing", "scores": {}})
            continue
        rows.append(asyncio.run(_run_one(pdf_path, record)))
    per_field: dict[str, list[float]] = {field: [] for field in FIELDS}
    for row in rows:
        for field, value in row.get("scores", {}).items():
            per_field[field].append(value)
    field_means = {field: round(statistics.mean(values), 3) for field, values in per_field.items() if values}
    overall = round(statistics.mean([v for values in per_field.values() for v in values]), 3) if field_means else 0.0
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "documents": len(rows),
        "overall_score": overall,
        "field_scores": field_means,
        "rows": rows,
    }


def _write_reports(result: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    json_path = REPORT_DIR / f"extraction-eval-{stamp}.json"
    json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    lines = [
        f"# Extraction eval - {result['generated_at']}",
        "",
        f"Documents: {result['documents']}  |  Overall score: **{result['overall_score']}**",
        "",
        "| Field | Mean score |",
        "|---|---|",
        *[f"| {field} | {score} |" for field, score in result["field_scores"].items()],
        "",
        "| Document | Score summary |",
        "|---|---|",
    ]
    for row in result["rows"]:
        if row.get("error"):
            lines.append(f"| {row['filename']} | error: {row['error']} |")
        else:
            summary = ", ".join(f"{field} {value}" for field, value in row["scores"].items())
            lines.append(f"| {row['filename']} | {summary} |")
    (REPORT_DIR / f"extraction-eval-{stamp}.md").write_text("\n".join(lines), encoding="utf-8")
    return json_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--truth", type=Path, default=DEFAULT_TRUTH)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    result = evaluate(args.data_dir, args.truth, args.limit)
    path = _write_reports(result)
    print(f"overall={result['overall_score']} field_scores={result['field_scores']}")
    print(f"report: {path}")


if __name__ == "__main__":
    main()
