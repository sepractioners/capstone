"""Value objects for the Contract Lifecycle domain.

Value objects are immutable (frozen dataclasses) and compared by value.
Each validates its own basic invariants in __post_init__ and raises
InvalidValueError on bad input. Each class lives in its own module; this
package re-exports the public names so callers can do
`from contract_lifecycle.domain.value_objects import Money`.
"""
from .access_policy import AccessPolicy
from .actor import Actor
from .address import Address
from .approval_threshold import ApprovalThreshold
from .audit_metadata import AuditMetadata
from .business_calendar import BusinessCalendar
from .change_summary import ChangeSummary
from .clause_reference import ClauseReference
from .commercial_terms import CommercialTerms
from .contact_details import ContactDetails
from .contract_id import ContractId
from .contract_number import ContractNumber
from .contract_type import ContractType
from .date_range import DateRange
from .delivery_method import DeliveryMethod
from .document_reference import DocumentReference
from .due_date import DueDate
from .effective_date import EffectiveDate
from .jurisdiction import Jurisdiction
from .key_dates import KeyDates
from .legal_name import LegalName
from .lifecycle_status import ALLOWED_TRANSITIONS, LifecycleStatus
from .money import Money
from .notice_period import NoticePeriod
from .obligation_id import ObligationId
from .organizational_role import OrganizationalRole
from .party_id import PartyId
from .percentage import Percentage
from .quantity import Quantity
from .reason import Reason
from .recurrence_frequency import RecurrenceFrequency
from .recurrence_rule import RecurrenceRule
from .renewal_terms import RenewalTerms
from .risk_factor import RiskFactor
from .risk_level import RiskLevel
from .risk_rating import RiskRating
from .signature_requirement import SignatureRequirement
from .termination_terms import TerminationTerms
from .version_number import VersionNumber

__all__ = [
    "ALLOWED_TRANSITIONS",
    "AccessPolicy",
    "Actor",
    "Address",
    "ApprovalThreshold",
    "AuditMetadata",
    "BusinessCalendar",
    "ChangeSummary",
    "ClauseReference",
    "CommercialTerms",
    "ContactDetails",
    "ContractId",
    "ContractNumber",
    "ContractType",
    "DateRange",
    "DeliveryMethod",
    "DocumentReference",
    "DueDate",
    "EffectiveDate",
    "Jurisdiction",
    "KeyDates",
    "LegalName",
    "LifecycleStatus",
    "Money",
    "NoticePeriod",
    "ObligationId",
    "OrganizationalRole",
    "PartyId",
    "Percentage",
    "Quantity",
    "Reason",
    "RecurrenceFrequency",
    "RecurrenceRule",
    "RenewalTerms",
    "RiskFactor",
    "RiskLevel",
    "RiskRating",
    "SignatureRequirement",
    "TerminationTerms",
    "VersionNumber",
]
