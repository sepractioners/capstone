"""Domain events: facts that have already happened.

Each event type lives in its own module and inherits the common envelope
fields from DomainEvent (event ID, aggregate ID, aggregate version,
occurred-at timestamp, actor, correlation ID, and version reference).
"""
from .amendment_executed import AmendmentExecuted
from .contract_activated import ContractActivated
from .contract_approved import ContractApproved
from .contract_archived import ContractArchived
from .contract_created import ContractCreated
from .contract_executed import ContractExecuted
from .contract_expired import ContractExpired
from .contract_rejected import ContractRejected
from .contract_review_completed import ContractReviewCompleted
from .contract_submitted_for_review import ContractSubmittedForReview
from .contract_terminated import ContractTerminated
from .contract_version_created import ContractVersionCreated
from .domain_event import DomainEvent
from .exception_granted import ExceptionGranted
from .obligation_breached import ObligationBreached
from .obligation_completed import ObligationCompleted
from .obligation_created import ObligationCreated
from .obligation_occurrence_due import ObligationOccurrenceDue
from .renewal_initiated import RenewalInitiated
from .renewal_window_opened import RenewalWindowOpened
from .signature_completed import SignatureCompleted
from .signature_failed import SignatureFailed
from .signature_requested import SignatureRequested
from .termination_initiated import TerminationInitiated

__all__ = [
    "AmendmentExecuted",
    "ContractActivated",
    "ContractApproved",
    "ContractArchived",
    "ContractCreated",
    "ContractExecuted",
    "ContractExpired",
    "ContractRejected",
    "ContractReviewCompleted",
    "ContractSubmittedForReview",
    "ContractTerminated",
    "ContractVersionCreated",
    "DomainEvent",
    "ExceptionGranted",
    "ObligationBreached",
    "ObligationCompleted",
    "ObligationCreated",
    "ObligationOccurrenceDue",
    "RenewalInitiated",
    "RenewalWindowOpened",
    "SignatureCompleted",
    "SignatureFailed",
    "SignatureRequested",
    "TerminationInitiated",
]
