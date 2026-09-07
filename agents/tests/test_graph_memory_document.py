"""Per-document working memory folds defined terms and headings across pages."""
from __future__ import annotations

from extraction_agent.graph import _update_document_memory
from extraction_agent.schema import ExtractedClause, ExtractedParty, PageExtraction


def test_document_memory_accumulates_defined_terms_and_last_heading() -> None:
    memory: dict = {}
    _update_document_memory(
        memory,
        PageExtraction(
            page_number=1,
            title="Co-Branding Agreement",
            defined_terms={"PCQ": "PC Quote, Inc."},
            parties=[ExtractedParty(legal_name="PC Quote, Inc.")],
            clauses=[ExtractedClause(heading="Definitions", page_location="page 1", text="...")],
        ),
    )
    _update_document_memory(
        memory,
        PageExtraction(
            page_number=2,
            defined_terms={"ABW": "A.B. Watley, Inc."},
            clauses=[ExtractedClause(heading="Term", page_location="page 2", text="...")],
        ),
    )

    assert memory["title"] == "Co-Branding Agreement"
    assert memory["defined_terms"] == {"PCQ": "PC Quote, Inc.", "ABW": "A.B. Watley, Inc."}
    assert memory["last_heading"] == "Term"
    assert memory["parties"] == ["PC Quote, Inc."]


def test_first_non_null_wins_for_singletons() -> None:
    memory: dict = {}
    _update_document_memory(memory, PageExtraction(page_number=1, contract_type="affiliate-agreement"))
    _update_document_memory(memory, PageExtraction(page_number=2, contract_type="vendor-agreement"))
    assert memory["contract_type"] == "affiliate-agreement"
