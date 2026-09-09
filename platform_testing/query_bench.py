"""Deterministic query-agent pipeline benchmark.

Restarts the API once per variant with an explicit environment, runs the fixed
question set (`fixtures/query_bench_questions.jsonl`) through `clm-agent`, scores
each answer against the committed ground truth, and writes one report recording
the exact config.

    python -m platform_testing.query_bench --model llama3.2:3b --variants B0,B2

Requires: the platform seeded with the `capstone-review-2026` validation
portfolio, Ollama (or the configured provider) running. The harness is
deterministic — variant configs, question set, and scoring are all committed;
only the model's prose varies.

Writes `platform_testing/reports/query-bench-<UTC stamp>.{json,md}`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
REPORT_DIR = Path(__file__).parent / "reports"
QUESTIONS = Path(__file__).parent / "fixtures" / "query_bench_questions.jsonl"
API = "https://localhost:8443"
CREDS = {"grant_type": "password", "username": "admin@capstone.local", "password": "CapstoneAdmin!2026"}

# Committed variant table. Each maps to an explicit query-agent env.
VARIANTS: dict[str, dict[str, str]] = {
    "B0": {"QUERY_PLAN_TOOLS": "0", "QUERY_INTERPRET": "1", "QUERY_VERIFY": "1",
           "QUERY_DETERMINISTIC_COMPOSE": "0"},  # LLM draft for every question
    "B1": {"QUERY_PLAN_TOOLS": "0", "QUERY_INTERPRET": "0", "QUERY_VERIFY": "0",
           "QUERY_DETERMINISTIC_COMPOSE": "1"},  # minimal calls
    "B2": {"QUERY_PLAN_TOOLS": "0", "QUERY_INTERPRET": "1", "QUERY_VERIFY": "1",
           "QUERY_DETERMINISTIC_COMPOSE": "1"},  # split composer + verify
    "B3": {"QUERY_PLAN_TOOLS": "1", "QUERY_INTERPRET": "1", "QUERY_VERIFY": "1",
           "QUERY_DETERMINISTIC_COMPOSE": "1"},  # LLM planner on
}


def _load_questions() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]


def _score(q: dict, answer: str) -> str:
    low = answer.lower()
    if not answer.strip() or any(m in low for m in
                                 ("unavailable", "remoteprotocolerror", "traceback", "timeouterror")):
        return "fail"
    if q.get("reject_regex") and re.search(q["reject_regex"], low):
        return "wrong"
    if q.get("min_len") and len(low) < q["min_len"]:
        return "wrong"
    if any(s not in low for s in q.get("expect_all", [])):
        return "wrong"
    if q.get("expect_regex") and not re.search(q["expect_regex"], low):
        return "wrong"
    return "pass"


def _api_up() -> bool:
    try:
        import ssl
        ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(f"{API}/health", context=ctx, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _token() -> str:
    import ssl
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    body = "&".join(f"{k}={v}" for k, v in CREDS.items()).encode()
    req = urllib.request.Request(f"{API}/auth/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
        return json.load(r)["access_token"]


def _restart_api(env_extra: dict[str, str], model: str) -> None:
    subprocess.run(["bash", "scripts/run-all.sh", "--stop"], cwd=ROOT, capture_output=True)
    env = dict(os.environ)
    env.update({"LLM_PROVIDER": "ollama", "LLM_MODEL": model, "LLM_TEMPERATURE": "0"})
    env.update(env_extra)
    subprocess.run(["bash", "scripts/run-all.sh", "--no-sync", "--no-frontend", "--no-console"],
                   cwd=ROOT, env=env, capture_output=True)
    for _ in range(30):
        if _api_up():
            return
        time.sleep(1)
    raise RuntimeError("API did not come up")


def _ask(question: str, token: str, env_extra: dict[str, str], model: str) -> tuple[str, float]:
    env = dict(os.environ)
    env.update({"CLM_AGENT_TOKEN": token, "CLM_API_URL": API,
                "LLM_PROVIDER": "ollama", "LLM_MODEL": model})
    env.update(env_extra)
    start = time.time()
    proc = subprocess.run(["uv", "run", "clm-agent", "ask", question], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=1200)
    return (proc.stdout + " " + proc.stderr).strip(), round(time.time() - start, 1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--variants", default="B2", help="comma-separated keys from VARIANTS")
    args = parser.parse_args()

    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    for v in variants:
        if v not in VARIANTS:
            parser.error(f"unknown variant {v!r}; choose from {list(VARIANTS)}")
    questions = _load_questions()

    stamp = datetime.now(timezone.utc)
    report = {"generated_at": stamp.isoformat(),
              "config": {"model": args.model, "temperature": 0, "questions": str(QUESTIONS)},
              "variants": {}}

    for v in variants:
        env_extra = VARIANTS[v]
        print(f"\n== {v}  {json.dumps(env_extra)} ==", flush=True)
        _restart_api(env_extra, args.model)
        token = _token()
        rows = []
        for q in questions:
            ans, wall = _ask(q["question"], token, env_extra, args.model)
            ans_1l = re.sub(r"\s+", " ", ans)[:300]
            verdict = _score(q, ans)
            rows.append({"id": q["id"], "class": q["class"], "verdict": verdict,
                         "wall_s": wall, "answer": ans_1l})
            print(f"  {q['id']:20} {verdict:5} {wall:>6}s", flush=True)
        report["variants"][v] = {
            "env": env_extra,
            "pass": sum(1 for r in rows if r["verdict"] == "pass"),
            "total": len(rows),
            "rows": rows,
        }
    subprocess.run(["bash", "scripts/run-all.sh", "--stop"], cwd=ROOT, capture_output=True)

    REPORT_DIR.mkdir(exist_ok=True)
    name = f"query-bench-{stamp.strftime('%Y%m%dT%H%M%SZ')}"
    (REPORT_DIR / f"{name}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    md = [f"# Query-agent bench — {report['generated_at']}", "",
          f"model: `{args.model}` · temperature 0 · questions: `{QUESTIONS.name}`", ""]
    for v, data in report["variants"].items():
        md.append(f"## {v}  ({data['pass']}/{data['total']} pass)")
        md.append(f"`{json.dumps(data['env'])}`\n")
        md.append("| question | class | verdict | wall |\n|---|---|---|---|")
        md += [f"| {r['id']} | {r['class']} | {r['verdict']} | {r['wall_s']}s |" for r in data["rows"]]
        md.append("")
    (REPORT_DIR / f"{name}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nreport: {REPORT_DIR / (name + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
