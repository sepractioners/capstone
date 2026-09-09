"""Deterministic extraction-accuracy benchmark.

Runs `platform_testing.extraction_eval` once per RAG setting in an isolated
subprocess (so no import-time env caching leaks between runs), then merges the
per-run reports into one, recording the exact config that produced them.

    python -m platform_testing.extraction_bench --model llama3.2:3b --rag both --limit 8

Config is fully determined by the CLI args + the committed fixture
(`platform_testing/fixtures/cuad_pdf/` + `cuad_ground_truth.jsonl`). The model's
output still varies run to run; the harness does not.

Writes `platform_testing/reports/extraction-bench-<UTC stamp>.{json,md}`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORT_DIR = Path(__file__).parent / "reports"
_REPORT_RE = re.compile(r"report:\s*(.+\.json)\s*$", re.MULTILINE)


def _run(rag: bool, args: argparse.Namespace) -> dict:
    """One extraction_eval run with a deterministic, explicit environment."""
    env = dict(os.environ)
    env.update({
        "LLM_PROVIDER": args.provider,
        "LLM_MODEL": args.model,
        "EXTRACTION_LLM_MODEL": args.model,
        "LLM_TEMPERATURE": "0",
        "LLM_TIMEOUT_SECONDS": str(args.timeout),
        "EXTRACTION_LLM_MAX_ATTEMPTS": str(args.attempts),
        "EXTRACTION_RAG_ENABLED": "1" if rag else "0",
        "EXTRACTION_RAG_DB": args.rag_db,
        "EXTRACTION_MAX_PAGES": str(args.max_pages),
        "EXTRACTION_REVIEW_ENABLED": "1" if args.review else "0",
    })
    cmd = [sys.executable, "-m", "platform_testing.extraction_eval",
           "--data-dir", str(args.data_dir), "--truth", str(args.truth),
           "--limit", str(args.limit)]
    print(f"  RAG={'on' if rag else 'off'}  {' '.join(cmd[2:])}", flush=True)
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                          timeout=args.run_timeout)
    if proc.returncode != 0:
        return {"rag": rag, "error": "subprocess_failed", "stderr": proc.stderr[-2000:]}
    match = _REPORT_RE.search(proc.stdout)
    if not match:
        return {"rag": rag, "error": "no_report", "stdout": proc.stdout[-2000:]}
    result = json.loads(Path(match.group(1)).read_text(encoding="utf-8"))
    result["rag"] = rag
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="llama3.2:3b", help="Ollama / provider model id")
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--rag", choices=["on", "off", "both"], default="both")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--max-pages", type=int, default=0, help="0 = all pages")
    parser.add_argument("--review", type=int, choices=[0, 1], default=1)
    parser.add_argument("--timeout", type=int, default=300, help="per-LLM-call timeout (s)")
    parser.add_argument("--attempts", type=int, default=3, help="per-call retry attempts")
    parser.add_argument("--run-timeout", type=int, default=14400, help="hard cap per RAG run (s)")
    parser.add_argument("--data-dir", type=Path,
                        default=Path(__file__).parent / "fixtures" / "cuad_pdf")
    parser.add_argument("--truth", type=Path,
                        default=Path(__file__).parent / "fixtures" / "cuad_ground_truth.jsonl")
    parser.add_argument("--rag-db", default="synthetic_data_loader/rag_knowledge.sqlite3")
    args = parser.parse_args()

    settings = ["on", "off"] if args.rag == "both" else [args.rag]
    config = {
        "model": args.model, "provider": args.provider, "temperature": 0,
        "limit": args.limit, "max_pages": args.max_pages, "review": bool(args.review),
        "call_timeout_s": args.timeout, "call_attempts": args.attempts,
        "data_dir": str(args.data_dir), "truth": str(args.truth),
    }
    print(f"extraction bench :: {json.dumps(config)}")

    runs = [_run(s == "on", args) for s in settings]
    stamp = datetime.now(timezone.utc)
    report = {
        "generated_at": stamp.isoformat(),
        "config": config,
        "runs": {("rag_on" if r.get("rag") else "rag_off"): {
            k: r[k] for k in ("overall_score", "field_scores", "documents", "error", "rows")
            if k in r
        } for r in runs},
    }
    on, off = report["runs"].get("rag_on", {}), report["runs"].get("rag_off", {})
    if "overall_score" in on and "overall_score" in off:
        report["rag_delta_overall"] = round(on["overall_score"] - off["overall_score"], 3)

    REPORT_DIR.mkdir(exist_ok=True)
    name = f"extraction-bench-{stamp.strftime('%Y%m%dT%H%M%SZ')}"
    (REPORT_DIR / f"{name}.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    md = [f"# Extraction bench — {report['generated_at']}", "",
          "```", json.dumps(config, indent=2), "```", ""]
    for label, run in report["runs"].items():
        md.append(f"## {label}")
        if run.get("error"):
            md.append(f"error: `{run['error']}`\n")
            continue
        md.append(f"documents: {run.get('documents')}  ·  overall: **{run.get('overall_score')}**\n")
        md.append("| field | mean score |\n|---|---|")
        md += [f"| {f} | {s} |" for f, s in (run.get("field_scores") or {}).items()]
        md.append("")
    if "rag_delta_overall" in report:
        md.append(f"**RAG on − off (overall): {report['rag_delta_overall']:+}**")
    (REPORT_DIR / f"{name}.md").write_text("\n".join(md), encoding="utf-8")

    print(f"\nreport: {REPORT_DIR / (name + '.json')}")
    for label, run in report["runs"].items():
        print(f"  {label}: overall={run.get('overall_score')} {run.get('error') or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
