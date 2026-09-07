"""Contract.record_extracted_terms: fold source-derived terms in during drafting."""
import unittest
from datetime import date

from contract_lifecycle.domain.aggregates import Contract
from contract_lifecycle.domain.exceptions import InvariantViolation
from contract_lifecycle.domain.value_objects import (
    Actor,
    ContractNumber,
    ContractType,
    KeyDates,
    LifecycleStatus,
    NoticePeriod,
    OrganizationalRole,
    RenewalTerms,
    TerminationTerms,
)


def _contract() -> Contract:
    return Contract.create_contract(
        contract_number=ContractNumber("IMPORT-abc123"),
        contract_type=ContractType("nda"),
        title="Test",
        actor=Actor(actor_id="u1", display_name="u1", role=OrganizationalRole("contract-owner")),
        correlation_id="corr-1",
    )


class RecordExtractedTermsTest(unittest.TestCase):
    def test_fills_empty_terms(self) -> None:
        contract = _contract()
        contract.record_extracted_terms(
            key_dates=KeyDates(renewal_deadline=date(2027, 1, 1)),
            renewal_terms=RenewalTerms(auto_renew=True, renewal_notice=NoticePeriod(60)),
            termination_terms=TerminationTerms(termination_for_convenience=True),
        )
        self.assertEqual(contract.key_dates.renewal_deadline, date(2027, 1, 1))
        self.assertTrue(contract.renewal_terms.auto_renew)
        self.assertEqual(contract.renewal_terms.renewal_notice, NoticePeriod(60))
        self.assertTrue(contract.termination_terms.termination_for_convenience)

    def test_never_overwrites_an_already_set_value(self) -> None:
        contract = _contract()
        contract.record_extracted_terms(renewal_terms=RenewalTerms(auto_renew=True))
        # a second, different reading must not replace the first
        contract.record_extracted_terms(renewal_terms=RenewalTerms(renewal_term_length_months=24))
        self.assertTrue(contract.renewal_terms.auto_renew)
        self.assertIsNone(contract.renewal_terms.renewal_term_length_months)

    def test_partial_key_dates_are_merged_field_by_field(self) -> None:
        contract = _contract()
        contract.record_extracted_terms(key_dates=KeyDates(renewal_deadline=date(2027, 1, 1)))
        contract.record_extracted_terms(
            key_dates=KeyDates(termination_notice_deadline=date(2026, 12, 1))
        )
        self.assertEqual(contract.key_dates.renewal_deadline, date(2027, 1, 1))
        self.assertEqual(contract.key_dates.termination_notice_deadline, date(2026, 12, 1))

    def test_empty_call_is_a_no_op(self) -> None:
        contract = _contract()
        contract.record_extracted_terms()
        self.assertEqual(contract.renewal_terms, RenewalTerms())

    def test_rejected_outside_drafting(self) -> None:
        contract = _contract()
        contract.lifecycle_status = LifecycleStatus.ACTIVE
        with self.assertRaises(InvariantViolation):
            contract.record_extracted_terms(renewal_terms=RenewalTerms(auto_renew=True))


if __name__ == "__main__":
    unittest.main()
