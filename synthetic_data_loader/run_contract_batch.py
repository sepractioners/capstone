"""Run the extraction agent over complete Kaggle contract samples.

The JSONL checkpoint and Markdown log are append-only and resumable. Slow local
LLM inference is recorded per contract rather than treated as a corpus failure.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from extraction_agent.pipeline import run

DEFAULT_LOG = Path("agents/extraction_agent/docs/improvement-test-log.md")
DEFAULT_LOCK = Path("platform_testing/reports/kaggle_contracts.lock")


def configure_debug_logging(log_path: Path | None = None) -> None:
    """Enable verbose logs for every extraction, retrieval, and MCP module."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=handlers,
        force=True,
    )
    for logger_name in ("extraction_agent", "clm_mcp_server", "contract_lifecycle", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.DEBUG)


def checkpoint_state(output: Path) -> tuple[set[str], dict[str, int]]:
    if not output.exists():
        return set(), {}
    completed: set[str] = set()
    attempts: dict[str, int] = {}
    for line in output.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        attempts[record["source"]] = max(attempts.get(record["source"], 0), int(record.get("attempt", 1)))
        if record.get("status") == "completed":
            completed.add(record["source"])
    return completed, attempts


def acquire_lock(lock_path: Path) -> None:
    """Prevent two contract batches from processing the same corpus concurrently."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        try:
            pid = int(lock_path.read_text(encoding="utf-8"))
            os.kill(pid, 0)
        except (ValueError, OSError):
            lock_path.unlink(missing_ok=True)
        else:
            raise RuntimeError(f"Contract batch already running with PID {pid}: {lock_path}")
    lock_path.write_text(str(os.getpid()), encoding="utf-8")


def append_markdown(log_path: Path, record: dict[str, Any]) -> None:
    """Append one human-readable contract result to the improvement log."""
    result = record.get("results", [])
    statuses = [item.get("lifecycle_status") for item in result if isinstance(item, dict)]
    title = Path(record["source"]).name
    lines = [
        f"\n### Contract Sample: `{title}`",
        f"- Timestamp: `{record['timestamp']}`",
        f"- Attempt: `{record.get('attempt', 1)}`",
        f"- Status: `{record['status']}`",
        f"- Lifecycle statuses: `{', '.join(statuses) or 'none'}`",
    ]
    if record.get("error_type"):
        lines.append(f"- Error type: `{record['error_type']}`")
        lines.append(f"- Error: `{record.get('error', '')}`")
    traces = [event for item in result if isinstance(item, dict) for event in item.get("extraction_trace", [])]
    if traces:
        lines.append(f"- Trace events: `{len(traces)}`")
        lines.append(f"- Completed page events: `{sum(event.get('status') == 'completed' for event in traces)}`")
        lines.append(f"- Failed page events: `{sum(event.get('status') == 'failed' for event in traces)}`")
        profiles = sorted({event.get('retrieval', {}).get('profile') for event in traces if event.get('retrieval', {}).get('profile')})
        lines.append(f"- Retrieved profiles: `{', '.join(profiles) or 'none'}`")
    with log_path.open("a", encoding="utf-8") as log:
        log.write("\n".join(lines) + "\n")


def run_batch(data_dir: Path, output: Path, log_path: Path, limit: int, database_path: str | None, lock_path: Path = DEFAULT_LOCK) -> dict[str, int]:
    """Process up to ``limit`` complete PDFs with JSONL and Markdown checkpoints."""
    output.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    acquire_lock(lock_path)
    done, prior_attempts = checkpoint_state(output)
    attempted = succeeded = failed = 0
    files = sorted(data_dir.glob("*.pdf"))[:limit]
    try:
        with output.open("a", encoding="utf-8") as report:
            for path in files:
                if str(path) in done:
                    continue
                attempted += 1
                source = str(path)
                attempt = prior_attempts.get(source, 0) + 1
                record: dict[str, Any] = {"source": source, "status": "running", "attempt": attempt, "timestamp": datetime.now(timezone.utc).isoformat()}
                logging.getLogger(__name__).debug("contract start index=%s/%s source=%s database=%s", attempted, len(files), path, database_path)
                try:
                    record["results"] = run(str(path), database_path=database_path)
                    record["status"] = "completed"
                    succeeded += 1
                    logging.getLogger(__name__).debug("contract result source=%s payload=%s", path, json.dumps(record["results"], ensure_ascii=False, default=str))
                    logging.getLogger(__name__).debug("contract completed source=%s results=%s", path, len(record["results"]))
                except Exception as error:
                    record.update({"status": "failed", "error_type": type(error).__name__, "error": str(error)})
                    failed += 1
                    logging.getLogger(__name__).exception("contract failed source=%s", path)
                report.write(json.dumps(record, default=str) + "\n")
                report.flush()
                append_markdown(log_path, record)
                print(f"{attempted}/{len(files)} {record['status']} {path.name}", flush=True)
    finally:
        lock_path.unlink(missing_ok=True)
    return {"requested": limit, "available": len(files), "attempted": attempted, "succeeded": succeeded, "failed": failed, "resumed": len(done)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("synthetic_data_loader/data/cuad_subset"))
    parser.add_argument("--output", type=Path, default=Path("platform_testing/reports/kaggle_contracts.jsonl"))
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--database-path", default=None)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--debug-log", type=Path, default=None, help="Also write full DEBUG logs to this file")
    parser.add_argument("--verbose", action="store_true", help="Enable full DEBUG logs on the console")
    args = parser.parse_args()
    if args.verbose or args.debug_log:
        configure_debug_logging(args.debug_log)
    print(json.dumps(run_batch(args.data_dir, args.output, args.log, args.limit, args.database_path, args.lock)))


if __name__ == "__main__":
    main()
