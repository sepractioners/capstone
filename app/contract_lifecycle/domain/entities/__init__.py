"""Entities that live inside the Contract aggregate (or the clause library).

Entities have identity that persists across attribute changes. They are
mutable, but mutation is expected to happen through the owning aggregate
root (Contract), which enforces invariants and raises domain events. Each
class lives in its own module; this package re-exports the public names.
"""
from .amendment import Amendment
from .approval import Approval
from .approval_decision import ApprovalDecision
from .clause import Clause
from .clause_status import ClauseStatus
from .clause_type import ClauseType
from .contract_party import ContractParty
from .contract_review import ContractReview
from .contract_version import ContractVersion
from .notice import Notice
from .notice_type import NoticeType
from .obligation import Obligation
from .obligation_occurrence import ObligationOccurrence
from .obligation_status import ObligationStatus
from .occurrence_status import OccurrenceStatus
from .party_role import PartyRole
from .party_type import PartyType
from .policy_exception import PolicyException
from .review_decision import ReviewDecision
from .signature_package import SignaturePackage
from .signature_status import SignatureStatus
from .signer import Signer
from .version_status import VersionStatus

__all__ = [
    "Amendment",
    "Approval",
    "ApprovalDecision",
    "Clause",
    "ClauseStatus",
    "ClauseType",
    "ContractParty",
    "ContractReview",
    "ContractVersion",
    "Notice",
    "NoticeType",
    "Obligation",
    "ObligationOccurrence",
    "ObligationStatus",
    "OccurrenceStatus",
    "PartyRole",
    "PartyType",
    "PolicyException",
    "ReviewDecision",
    "SignaturePackage",
    "SignatureStatus",
    "Signer",
    "VersionStatus",
]
