"""Normalize external legal datasets into the hybrid RAG knowledge JSONL format.

The importer intentionally accepts generic JSON/JSONL exports so datasets such
as LEDGAR, ContractNLI, or curated Kaggle files can be added without coupling
the extractor to their original schema.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def normalize_record(raw: dict[str, Any], dataset: str, index: int) -> dict[str, Any] | None:
    """Map common legal-dataset fields into one RAG knowledge record."""
    text = raw.get("text") or raw.get("sentence") or raw.get("context") or raw.get("clause")
    if not text:
        return None
    label = raw.get("contract_type") or raw.get("category") or raw.get("label") or "unclassified"
    record_id = str(raw.get("id") or raw.get("uid") or f"{dataset}:{index}")
    return {
        "id": record_id,
        "dataset": dataset,
        "knowledge_type": raw.get("knowledge_type", "dataset_example"),
        "contract_type": str(label),
        "name": raw.get("name", record_id),
        "text": str(text),
        "guidance": raw.get("guidance", "Use the source text as authority; preserve evidence and do not infer unsupported facts."),
        "required_fields": raw.get("required_fields", ["title", "parties", "clauses"]),
        "recommended_fields": raw.get("recommended_fields", ["key_dates", "obligations", "commercial_terms", "signers"]),
    }


def import_dataset(input_path: str | Path, output_path: str | Path, dataset: str) -> int:
    """Normalize JSON or JSONL input and write JSONL RAG records."""
    source = Path(input_path)
    raw_text = source.read_text(encoding="utf-8")
    try:
        parsed = json.loads(raw_text)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
    records = [record for index, raw in enumerate(rows) if (record := normalize_record(raw, dataset, index))]
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(json.dumps(record, ensure_ascii=True) + "\n" for record in records), encoding="utf-8")
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()
    print(f"records={import_dataset(args.input, args.output, args.dataset)}")


if __name__ == "__main__":
    main()
