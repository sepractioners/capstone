"""Exercises ingest_contract_handler directly - no LLM, no MCP transport.

Verifies the fast-forward/stop-at-last-supported-stage policy: a complete
candidate should reach ACTIVE, an incomplete one should stop earlier with
an honest reason, and re-ingesting the same document is idempotent.
"""
import base64
import os
import tempfile
import unittest
from datetime import date

from clm_mcp_server.dependencies import build_dependencies
from clm_mcp_server.ingest_contract_handler import ingest_contract
from clm_mcp_server.ingest_payload import (
    ContractCandidate,
    ExtractedClause,
    ExtractedKeyDates,
    ExtractedObligation,
    ExtractedParty,
    ExtractedRenewalTerms,
    ExtractedSigner,
    ExtractedTerminationTerms,
)
from contract_lifecycle.domain.value_objects import ContractId


def _base_candidate(source_hash: str) -> ContractCandidate:
    return ContractCandidate(
        source_document_hash=source_hash,
        source_uri=f"file:///contracts/{source_hash}.pdf",
        source_media_type="application/pdf",
        source_content_base64=base64.b64encode(f"fake pdf bytes for {source_hash}".encode()).decode("ascii"),
        source_original_filename=f"{source_hash}.pdf",
        title="Affiliate Agreement",
        contract_type="affiliate-agreement",
        parties=[
            ExtractedParty(legal_name="Acme Corp", roles=["customer"]),
            ExtractedParty(legal_name="Widgets Inc", roles=["affiliate"]),
        ],
        clauses=[
            ExtractedClause(heading="Governing Law", page_location="page 1", text="New York law applies."),
        ],
        key_dates=ExtractedKeyDates(effective_date=date(2020, 1, 1)),
    )


class IngestContractHandlerTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        self.deps = build_dependencies(self.db_path)

    def tearDown(self) -> None:
        os.remove(self.db_path)

    def test_complete_candidate_reaches_active(self) -> None:
        candidate = _base_candidate("hash-complete")
        candidate.signers = [
            ExtractedSigner(party_legal_name="Acme Corp", signer_role="customer", signed_at=date(2020, 1, 1)),
            ExtractedSigner(party_legal_name="Widgets Inc", signer_role="affiliate", signed_at=date(2020, 1, 1)),
        ]

        result = ingest_contract(candidate, self.deps)

        self.assertFalse(result.already_ingested)
        self.assertEqual(result.lifecycle_status, "active")
        self.assertEqual(result.skipped_stages, [])

    def test_incomplete_candidate_stops_before_signature(self) -> None:
        candidate = _base_candidate("hash-incomplete")
        # no signers extracted at all

        result = ingest_contract(candidate, self.deps)

        self.assertEqual(result.lifecycle_status, "approved")
        stages = {s.stage for s in result.skipped_stages}
        self.assertIn("sign", stages)

    def test_fewer_than_two_parties_stops_before_approval(self) -> None:
        candidate = _base_candidate("hash-one-party")
        candidate.parties = [ExtractedParty(legal_name="Acme Corp", roles=["customer"])]

        result = ingest_contract(candidate, self.deps)

        self.assertEqual(result.lifecycle_status, "in_review")
        stages = {s.stage for s in result.skipped_stages}
        self.assertIn("approve", stages)

    def test_reingesting_same_document_is_idempotent(self) -> None:
        candidate = _base_candidate("hash-repeat")

        first = ingest_contract(candidate, self.deps)
        second = ingest_contract(candidate, self.deps)

        self.assertFalse(first.already_ingested)
        self.assertTrue(second.already_ingested)
        self.assertEqual(first.contract_id, second.contract_id)

    def test_unmapped_party_role_falls_back_to_other(self) -> None:
        candidate = _base_candidate("hash-weird-role")
        candidate.parties = [
            ExtractedParty(legal_name="Acme Corp", roles=["some-exotic-role-nobody-modeled"]),
            ExtractedParty(legal_name="Widgets Inc", roles=["affiliate"]),
        ]

        result = ingest_contract(candidate, self.deps)

        contract = self.deps.repository.get(ContractId(result.contract_id))
        self.assertEqual(contract.parties[0].roles[0].value, "other")

    def test_source_document_is_stored_and_retrievable_by_content_hash(self) -> None:
        candidate = _base_candidate("hash-source-doc")

        result = ingest_contract(candidate, self.deps)

        contract = self.deps.repository.get(ContractId(result.contract_id))
        content_hash = contract.current_version.document.content_hash
        self.assertEqual(content_hash, "hash-source-doc")

        stored = self.deps.blob_store.get(content_hash)
        self.assertIsNotNone(stored)
        self.assertEqual(stored.media_type, "application/pdf")
        self.assertEqual(stored.original_filename, "hash-source-doc.pdf")
        self.assertEqual(stored.data, base64.b64decode(candidate.source_content_base64))

    def test_clause_text_is_persisted_verbatim_not_just_a_reference(self) -> None:
        candidate = _base_candidate("hash-clause-text")

        result = ingest_contract(candidate, self.deps)

        contract = self.deps.repository.get(ContractId(result.contract_id))
        self.assertEqual(len(contract.clauses), 1)
        self.assertEqual(contract.clauses[0].text, "New York law applies.")
        # The reference to the source document is still there too - text
        # supplements it, it doesn't replace it.
        self.assertEqual(contract.clauses[0].text_reference.content_hash, "hash-clause-text")

    def test_renewal_termination_and_obligation_consequence_are_persisted(self) -> None:
        candidate = _base_candidate("hash-terms")
        candidate.renewal_terms = ExtractedRenewalTerms(auto_renew=True, renewal_notice_days=60)
        candidate.termination_terms = ExtractedTerminationTerms(
            notice_period_days=90, termination_for_convenience=True
        )
        candidate.obligations = [
            ExtractedObligation(
                description="Pay the annual fee",
                responsible_party_legal_name="Acme Corp",
                due_date=date(2021, 1, 1),
                trigger_event="on each anniversary",
                consequence_of_failure="10% late fee",
                grace_period_days=15,
            )
        ]

        result = ingest_contract(candidate, self.deps)
        contract = self.deps.repository.get(ContractId(result.contract_id))

        self.assertTrue(contract.renewal_terms.auto_renew)
        self.assertEqual(contract.renewal_terms.renewal_notice.days, 60)
        self.assertTrue(contract.termination_terms.termination_for_convenience)
        self.assertEqual(contract.termination_terms.notice_period.days, 90)
        self.assertEqual(len(contract.obligations), 1)
        self.assertEqual(contract.obligations[0].consequence_of_failure, "10% late fee")
        self.assertEqual(contract.obligations[0].due_date_rule.grace_period_days, 15)

    def test_reingesting_same_document_does_not_error_storing_blob_twice(self) -> None:
        candidate = _base_candidate("hash-source-doc-repeat")

        ingest_contract(candidate, self.deps)
        result = ingest_contract(candidate, self.deps)  # idempotent re-ingest

        self.assertTrue(result.already_ingested)
        stored = self.deps.blob_store.get("hash-source-doc-repeat")
        self.assertIsNotNone(stored)


if __name__ == "__main__":
    unittest.main()
