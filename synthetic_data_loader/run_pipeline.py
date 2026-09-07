"""Batch driver: runs the extraction pipeline over every PDF/JSON/CSV file
in a directory and prints a summary report (loaded / skipped-stage counts
/ hard failures).

    python run_pipeline.py --limit 3         # small validation run first
    python run_pipeline.py                   # full subset
"""
from __future__ import annotations

import argparse
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Optional

from extraction_agent.pipeline import run

DEFAULT_DATA_DIR = Path(__file__).parent / "data" / "cuad_subset"
DEFAULT_DATABASE_PATH = str(Path(__file__).parent.parent / "clm.sqlite3")
_SUPPORTED_SUFFIXES = {".pdf", ".json", ".csv"}


def bind_to_organization(database_path: str, contract_ids: list[str], organization_id: Optional[str]) -> None:
    """Bind newly imported contracts to the selected local organization."""
    if not contract_ids:
        return
    connection = sqlite3.connect(database_path)
    try:
        if organization_id is None:
            organizations = connection.execute("SELECT id FROM organizations ORDER BY created_at").fetchall()
            if len(organizations) != 1:
                return
            organization_id = organizations[0][0]
        connection.executemany(
            "INSERT OR IGNORE INTO contract_tenants (contract_id, organization_id, created_at) VALUES (?, ?, datetime('now'))",
            [(contract_id, organization_id) for contract_id in contract_ids],
        )
        connection.commit()
    finally:
        connection.close()


def main(data_dir: Path, database_path: str, limit: Optional[int], organization_id: Optional[str]) -> None:
    files = sorted(p for p in data_dir.iterdir() if p.suffix.lower() in _SUPPORTED_SUFFIXES)
    if limit is not None:
        files = files[:limit]

    status_counts: Counter[str] = Counter()
    skip_reasons: Counter[str] = Counter()
    failures: list[tuple[str, str]] = []
    already_ingested = 0
    contracts_seen = 0

    for path in files:
        print(f"Processing {path.name}...", flush=True)
        try:
            results = run(str(path), database_path=database_path)
        except Exception as e:  # noqa: BLE001 - report and continue the batch
            failures.append((path.name, f"{type(e).__name__}: {e}"))
            print(f"  FAILED: {e}")
            continue

        for result in results:
            contracts_seen += 1
            bind_to_organization(database_path, [result["contract_id"]], organization_id)
            status_counts[result["lifecycle_status"]] += 1
            if result["already_ingested"]:
                already_ingested += 1
            for skip in result.get("skipped_stages", []):
                skip_reasons[skip["stage"]] += 1
            suffix = " (already ingested)" if result["already_ingested"] else ""
            print(f"  -> {result['contract_number']}: {result['lifecycle_status']}{suffix}")

    print("\n=== Batch summary ===")
    print(f"Files processed: {len(files)}")
    print(f"Contracts produced: {contracts_seen}")
    print(f"Already ingested (idempotent skip): {already_ingested}")
    print("Final lifecycle status counts:")
    for status, count in status_counts.most_common():
        print(f"  {status}: {count}")
    if skip_reasons:
        print("Stages the ingest handler stopped short of (partial results):")
        for stage, count in skip_reasons.most_common():
            print(f"  {stage}: {count}")
    if failures:
        print(f"Hard failures: {len(failures)}")
        for name, reason in failures:
            print(f"  {name}: {reason}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--database-path", type=str, default=DEFAULT_DATABASE_PATH)
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N files")
    parser.add_argument("--organization-id", type=str, default=None, help="Tenant to receive imports; auto-selects the only local organization")
    args = parser.parse_args()
    main(args.data_dir, args.database_path, args.limit, args.organization_id)
