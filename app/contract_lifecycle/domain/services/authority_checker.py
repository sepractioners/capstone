"""AuthorityChecker: verifies an actor may approve, sign, amend, or terminate.

A Protocol so real authorization (delegated authority tables, an external
IAM system) can be substituted for the default role check without any
caller needing to change (dependency inversion + Liskov substitution: any
implementation must honor this exact contract).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ..value_objects import Actor

if TYPE_CHECKING:
    from ..aggregates import Contract


class AuthorityChecker(Protocol):
    def can_approve(self, actor: Actor, contract: "Contract") -> bool:
        ...

    def can_sign(self, actor: Actor, contract: "Contract") -> bool:
        ...

    def can_amend(self, actor: Actor, contract: "Contract") -> bool:
        ...

    def can_terminate(self, actor: Actor, contract: "Contract") -> bool:
        ...
