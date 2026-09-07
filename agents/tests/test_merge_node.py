"""Fixture-based test for merge_node.py - no LLM call involved.

Three synthetic PageExtraction objects, mimicking this dataset's actual
behavior (the same clause block repeated verbatim across pages, plus a
deliberately conflicting title) exercise the dedupe/conflict-flagging
policy in isolation.
"""
import unittest

from extraction_agent.merge_node import merge_page_extractions
from extraction_agent.schema import (
    ContractCandidate,
    ExtractedClause,
    ExtractedKeyDates,
    ExtractedObligation,
    ExtractedParty,
    ExtractedRenewalTerms,
    ExtractedSigner,
    ExtractedTerminationTerms,
    PageExtraction,
)


def _merge(pages: list[PageExtraction], source_document_hash: str) -> ContractCandidate:
    return merge_page_extractions(
        pages,
        source_uri="file:///c.pdf",
        source_document_hash=source_document_hash,
        source_media_type="application/pdf",
        source_content_base64="ZmFrZQ==",  # "fake"
        source_original_filename="c.pdf",
    )


class MergeNodeTest(unittest.TestCase):
    def test_duplicated_clauses_across_pages_are_deduped(self) -> None:
        clause = ExtractedClause(
            heading="Clause One - Purpose", page_location="page 1", text="This agreement grants financing."
        )
        pages = [
            PageExtraction(page_number=1, title="Car Financing Agreement", clauses=[clause]),
            PageExtraction(page_number=2, clauses=[clause.model_copy(update={"page_location": "page 2"})]),
            PageExtraction(page_number=3, clauses=[clause.model_copy(update={"page_location": "page 3"})]),
        ]

        candidate = _merge(pages, "h1")

        self.assertEqual(len(candidate.clauses), 1)
        self.assertEqual(candidate.title, "Car Financing Agreement")
        self.assertEqual(candidate.field_conflicts, [])

    def test_conflicting_singleton_field_is_flagged_not_silently_dropped(self) -> None:
        pages = [
            PageExtraction(page_number=1, contract_type="car-financing-agreement"),
            PageExtraction(page_number=2, contract_type="motorcycle-financing-agreement"),
        ]

        candidate = _merge(pages, "h2")

        self.assertEqual(candidate.contract_type, "car-financing-agreement")
        conflict_fields = {c.field for c in candidate.field_conflicts}
        self.assertIn("contract_type", conflict_fields)
        conflict = next(c for c in candidate.field_conflicts if c.field == "contract_type")
        self.assertEqual(
            set(conflict.candidate_values), {"car-financing-agreement", "motorcycle-financing-agreement"}
        )

    def test_parties_from_different_pages_are_merged_by_name_with_combined_roles(self) -> None:
        pages = [
            PageExtraction(page_number=1, parties=[ExtractedParty(legal_name="Acme Corp", roles=["customer"])]),
            PageExtraction(
                page_number=3,
                parties=[
                    ExtractedParty(legal_name="Acme Corp", roles=["borrower"], registration_id="EIN-123"),
                ],
            ),
        ]

        candidate = _merge(pages, "h3")

        self.assertEqual(len(candidate.parties), 1)
        merged = candidate.parties[0]
        self.assertEqual(set(merged.roles), {"customer", "borrower"})
        self.assertEqual(merged.registration_id, "EIN-123")

    def test_signers_deduped_by_name_and_role(self) -> None:
        signer = ExtractedSigner(party_legal_name="Carlos Brown", signer_role="borrower")
        pages = [
            PageExtraction(page_number=1, signers=[signer]),
            PageExtraction(page_number=3, signers=[signer]),
        ]

        candidate = _merge(pages, "h4")

        self.assertEqual(len(candidate.signers), 1)

    def test_obligation_trigger_and_consequence_are_folded_from_every_copy(self) -> None:
        pages = [
            PageExtraction(
                page_number=1,
                obligations=[
                    ExtractedObligation(
                        description="Pay the fee",
                        responsible_party_legal_name="Acme Corp",
                        trigger_event="upon receipt of invoice",
                    )
                ],
            ),
            PageExtraction(
                page_number=2,
                obligations=[
                    ExtractedObligation(
                        description="Pay the fee",
                        responsible_party_legal_name="Acme Corp",
                        consequence_of_failure="1.5% monthly interest",
                        evidence_requirements=["paid invoice"],
                    )
                ],
            ),
        ]

        candidate = _merge(pages, "h-obl")

        self.assertEqual(len(candidate.obligations), 1)
        merged = candidate.obligations[0]
        self.assertEqual(merged.trigger_event, "upon receipt of invoice")
        self.assertEqual(merged.consequence_of_failure, "1.5% monthly interest")
        self.assertEqual(merged.evidence_requirements, ["paid invoice"])

    def test_renewal_and_termination_terms_take_first_value_and_boolean_or(self) -> None:
        pages = [
            PageExtraction(
                page_number=1,
                renewal_terms=ExtractedRenewalTerms(auto_renew=True, renewal_notice_days=60),
                key_dates=ExtractedKeyDates(renewal_deadline=None),
            ),
            PageExtraction(
                page_number=2,
                renewal_terms=ExtractedRenewalTerms(renewal_term_length_months=12),
                termination_terms=ExtractedTerminationTerms(termination_for_convenience=True),
            ),
        ]

        candidate = _merge(pages, "h-terms")

        self.assertTrue(candidate.renewal_terms.auto_renew)
        self.assertEqual(candidate.renewal_terms.renewal_notice_days, 60)
        self.assertEqual(candidate.renewal_terms.renewal_term_length_months, 12)
        self.assertTrue(candidate.termination_terms.termination_for_convenience)

    def test_no_pages_produces_untitled_unclassified_candidate(self) -> None:
        candidate = _merge([], "h5")

        self.assertEqual(candidate.title, "Untitled Contract")
        self.assertEqual(candidate.contract_type, "unclassified")
        self.assertEqual(candidate.parties, [])


if __name__ == "__main__":
    unittest.main()
