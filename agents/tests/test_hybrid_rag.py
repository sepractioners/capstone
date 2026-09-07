import json
from pathlib import Path

from extraction_agent import hybrid_rag


def test_hybrid_retrieval_merges_fts_and_vector_results(tmp_path, monkeypatch) -> None:
    database = tmp_path / "rag.sqlite3"
    vectors = {
        "profile": [1.0, 0.0],
        "example": [0.8, 0.2],
        "query": [1.0, 0.0],
    }
    monkeypatch.setattr(hybrid_rag, "embed", lambda text: vectors["query"] if text == "query" else vectors["profile"] if "profile" in text else vectors["example"])
    hybrid_rag.add_records(
        [
            {
                "id": "profile-co-branding",
                "dataset": "internal-procedural",
                "knowledge_type": "contract_profile",
                "contract_type": "co-branding-agreement",
                "name": "Co-branding profile",
                "text": "co-branding agreement branding marks effective date",
                "required_fields": ["title", "parties"],
            },
            {
                "id": "example-1",
                "dataset": "cuad",
                "knowledge_type": "kaggle_example",
                "contract_type": "co-branding-agreement",
                "name": "Example agreement",
                "text": "co-branded site advertising services",
            },
        ],
        database,
    )
    result = hybrid_rag.retrieve("query", database)
    assert result is not None
    assert result["retrieval_mode"] == "hybrid_fts_sqlite"
    assert result["nearest_examples"]
