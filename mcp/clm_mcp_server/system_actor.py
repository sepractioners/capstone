"""The fixed system actor attributed to everything the MCP server creates.

The server never trusts a caller-supplied identity for provenance -
every contract, review, approval, and signature record created through
`ingest_contract` is attributed to this actor, so the audit trail always
shows what came from automated ingestion versus a real user.
"""
from contract_lifecycle.domain.value_objects import Actor, OrganizationalRole

AUTOMATED_IMPORT_ROLE = OrganizationalRole("automated-import")

SYSTEM_ACTOR = Actor(
    actor_id="extraction-agent",
    display_name="Extraction Agent",
    role=AUTOMATED_IMPORT_ROLE,
    is_system=True,
)
