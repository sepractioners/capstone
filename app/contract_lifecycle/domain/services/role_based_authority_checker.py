"""RoleBasedAuthorityChecker: the default AuthorityChecker.

Grants authority purely by the actor's organizational role name. Intended
as a starting point - production systems typically replace this with an
implementation backed by a delegated-authority table.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..value_objects import Actor

if TYPE_CHECKING:
    from ..aggregates import Contract


class RoleBasedAuthorityChecker:
    def __init__(
        self,
        approver_roles: frozenset[str] = frozenset({"legal-approver", "business-approver"}),
        signer_roles: frozenset[str] = frozenset({"authorized-signer"}),
        amender_roles: frozenset[str] = frozenset({"legal-approver"}),
        terminator_roles: frozenset[str] = frozenset({"contract-owner", "legal-approver"}),
    ) -> None:
        self._approver_roles = approver_roles
        self._signer_roles = signer_roles
        self._amender_roles = amender_roles
        self._terminator_roles = terminator_roles

    def can_approve(self, actor: Actor, contract: "Contract") -> bool:
        return actor.role.name in self._approver_roles

    def can_sign(self, actor: Actor, contract: "Contract") -> bool:
        return actor.role.name in self._signer_roles

    def can_amend(self, actor: Actor, contract: "Contract") -> bool:
        return actor.role.name in self._amender_roles

    def can_terminate(self, actor: Actor, contract: "Contract") -> bool:
        return actor.role.name in self._terminator_roles
