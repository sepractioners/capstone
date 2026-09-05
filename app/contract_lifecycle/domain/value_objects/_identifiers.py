"""Internal helper for generating opaque identifier values.

Not a public value object itself - shared by the identifier value objects
(ContractId, PartyId, ObligationId) so identity generation stays in one
place (DRY) without those classes depending on each other.
"""
import uuid


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"
