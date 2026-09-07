from extraction_agent.retrieval import retrieve_profile


def test_co_branding_profile_is_retrieved_from_document_text() -> None:
    profile = retrieve_profile("misleading-file-name.pdf", "CO-BRANDING AND ADVERTISING AGREEMENT")
    assert profile["id"] == "co-branding-agreement"
    assert profile["retrieval_mode"] == "deterministic_profile"
    assert profile["vector_enabled"] is False


def test_filename_does_not_classify_document() -> None:
    profile = retrieve_profile("Co-Branding Agreement.pdf", "ordinary contract text")
    assert profile["id"] == "unclassified"


def test_unknown_source_uses_unclassified_profile() -> None:
    profile = retrieve_profile("miscellaneous.pdf", "ordinary contract text")
    assert profile["id"] == "unclassified"
    assert profile["score"] == 0
