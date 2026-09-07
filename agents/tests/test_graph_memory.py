from extraction_agent.graph import _update_party_memory
from extraction_agent.schema import ExtractedParty, PageExtraction


def test_party_memory_remains_string_names_across_pages() -> None:
    memory = {"parties": ["First Party"]}
    _update_party_memory(
        memory,
        PageExtraction(page_number=2, parties=[ExtractedParty(legal_name="Second Party")]),
    )
    assert memory["parties"] == ["First Party", "Second Party"]