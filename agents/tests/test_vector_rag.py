from pathlib import Path

from extraction_agent.vector_rag import retrieve_vector_profile


def test_missing_vector_index_falls_back_without_network() -> None:
    assert retrieve_vector_profile("unknown.pdf", "text", Path("missing-index.json")) is None