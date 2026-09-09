"""Score platform_testing/reports/query_bench.tsv against ground truth.

Reads the raw rows written by bench-query-agent.sh and prints a verdict table
(pass / wrong / fail) per variant, plus wall-time and llm-call totals.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

TSV = Path("platform_testing/reports/query_bench.tsv")

# q -> (predicate on the lowercased answer text)
GROUND_TRUTH = {
    "1": lambda a: all(s in a for s in ("24", "15")) and re.search(r"\b1\b.*review|in.?review.*\b1\b|1 in review", a),
    "2": lambda a: re.search(r"\b2\b", a) and not re.search(r"\b(24|40)\b\s*(active\s+)?(vendor|contract)", a),
    "3": lambda a: re.search(r"\b4\b", a) and a.count("co-branding") + a.count("co branding") >= 1,
    "4": lambda a: "7" in a and "distribution" in a and re.search(r"nda\D*1\b", a),
    "5": lambda a: re.search(r"\b15\b", a),
    "6": lambda a: bool(re.search(r"pay|invoic|obligation", a)) and len(a) > 80,
}
FAIL_MARKERS = ("unavailable", "remoteprotocolerror", "traceback", "validationerror", "timeouterror")


def verdict(q: str, ans: str) -> str:
    low = ans.lower()
    if any(m in low for m in FAIL_MARKERS) or not ans.strip():
        return "fail"
    if q in GROUND_TRUTH and GROUND_TRUTH[q](low):
        return "pass"
    return "wrong"


def main() -> int:
    if not TSV.exists():
        print(f"no {TSV}")
        return 1
    rows = list(csv.DictReader(TSV.open(encoding="utf-8"), delimiter="\t"))
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_variant[r["variant"]].append(r)

    for variant, rs in by_variant.items():
        rs = {r["q"]: r for r in rs}  # last write per q wins
        p = sum(1 for r in rs.values() if verdict(r["q"], r["answer"]) == "pass")
        wall = sum(int(r["wall_s"]) for r in rs.values())
        calls = sum(int(r["llm_calls"]) for r in rs.values())
        print(f"\n== {variant}  {p}/{len(rs)} pass   {wall}s total   {calls} LLM calls ==")
        for q in sorted(rs):
            r = rs[q]
            v = verdict(q, r["answer"])
            print(f"  Q{q}  {v:5}  {r['wall_s']:>4}s  calls={r['llm_calls']}  {r['answer'][:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
