"""MCP server exposing the Contract Lifecycle Management domain.

This package is the only sanctioned way for an external agent to write
contract data into the CLM database: every write goes through
`contract_lifecycle`'s real application services, so aggregate invariants
are always enforced. See ingest_contract_handler.py for the orchestration
and app/contract-lifecycle-ddd.md for the domain model itself.
"""
