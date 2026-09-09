"""SQLite persistence for web identity, tenancy, and client credentials."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class WebDatabase:
    """Create and access the web application's tables in the CLM database."""

    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        connection = self.connect()
        try:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS organizations (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memberships (
                    user_id TEXT NOT NULL REFERENCES users(id),
                    organization_id TEXT NOT NULL REFERENCES organizations(id),
                    role TEXT NOT NULL,
                    PRIMARY KEY (user_id, organization_id)
                );
                CREATE TABLE IF NOT EXISTS oauth_clients (
                    client_id TEXT PRIMARY KEY,
                    client_secret_hash TEXT NOT NULL,
                    name TEXT NOT NULL,
                    organization_id TEXT NOT NULL REFERENCES organizations(id),
                    scopes TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contract_tenants (
                    contract_id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL REFERENCES organizations(id),
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memberships_org ON memberships(organization_id);
                CREATE INDEX IF NOT EXISTS idx_contract_tenants_org ON contract_tenants(organization_id);
                CREATE TABLE IF NOT EXISTS clause_templates (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT REFERENCES organizations(id),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    clause_type TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    contract_types TEXT NOT NULL DEFAULT '',
                    jurisdiction TEXT NOT NULL DEFAULT '',
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'draft',
                    current_version INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS clause_template_versions (
                    template_id TEXT NOT NULL REFERENCES clause_templates(id),
                    version INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (template_id, version)
                );
                CREATE TABLE IF NOT EXISTS clause_template_reviews (
                    id TEXT PRIMARY KEY,
                    template_id TEXT NOT NULL REFERENCES clause_templates(id),
                    version INTEGER NOT NULL,
                    reviewer_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    comments TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS contract_clause_provenance (
                    contract_id TEXT NOT NULL,
                    clause_id TEXT NOT NULL,
                    template_id TEXT NOT NULL REFERENCES clause_templates(id),
                    template_version INTEGER NOT NULL,
                    PRIMARY KEY (contract_id, clause_id)
                );
                CREATE INDEX IF NOT EXISTS idx_clause_templates_org ON clause_templates(organization_id, status);
                CREATE INDEX IF NOT EXISTS idx_clause_reviews_template ON clause_template_reviews(template_id);
                CREATE TABLE IF NOT EXISTS extraction_traces (
                    contract_id TEXT PRIMARY KEY,
                    trace_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_conversations (
                    id TEXT PRIMARY KEY,
                    organization_id TEXT NOT NULL REFERENCES organizations(id),
                    created_by TEXT NOT NULL REFERENCES users(id),
                    title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES agent_conversations(id),
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    mode TEXT NOT NULL CHECK (mode IN ('analysis', 'extraction')),
                    text TEXT NOT NULL DEFAULT '',
                    attachment_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES agent_conversations(id),
                    message_id TEXT NOT NULL REFERENCES agent_messages(id),
                    organization_id TEXT NOT NULL REFERENCES organizations(id),
                    mode TEXT NOT NULL CHECK (mode IN ('analysis', 'extraction')),
                    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS agent_run_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES agent_runs(id),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_debug_traces (
                    run_id TEXT PRIMARY KEY REFERENCES agent_runs(id),
                    steps_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_agent_conversations_org ON agent_conversations(organization_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_messages_conversation ON agent_messages(conversation_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_runs_org ON agent_runs(organization_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_agent_run_events_run ON agent_run_events(run_id, id);
                """
            )
            # Additive migrations (SQLite raises OperationalError if the column exists).
            for statement in (
                "ALTER TABLE agent_conversations ADD COLUMN summary TEXT NOT NULL DEFAULT ''",
            ):
                try:
                    connection.execute(statement)
                except sqlite3.OperationalError:
                    pass
            now = datetime.now(timezone.utc).isoformat()
            builtins = (
                ("global_confidentiality", "Confidentiality", "Protect confidential information.", "obligation", "Each party shall protect the other party's confidential information and use it only to perform this agreement."),
                ("global_payment", "Payment", "Standard invoice payment obligation.", "obligation", "Customer shall pay all undisputed invoices within thirty days of receipt."),
                ("global_termination", "Termination", "Termination for uncured material breach.", "condition", "Either party may terminate this agreement for material breach if the breach is not cured within thirty days after written notice."),
            )
            for template_id, name, description, clause_type, text in builtins:
                connection.execute(
                    "INSERT OR IGNORE INTO clause_templates VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, 'approved', 1, 'system', ?, ?)",
                    (template_id, name, description, clause_type, "", "", "", "medium", now, now),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO clause_template_versions VALUES (?, 1, ?, 'system', ?)",
                    (template_id, text, now),
                )
            connection.commit()
        finally:
            connection.close()


def initialize_database(database_path: str) -> None:
    """Create every table the platform needs in ``database_path``.

    This covers both the web/identity/agent tables owned by
    :class:`WebDatabase` and the contract_lifecycle *domain* tables
    (``contracts``, ``domain_events``, ``document_blobs``). The domain
    tables are otherwise only created lazily the first time the API
    process imports its dependencies, so a fresh checkout that inspects
    or seeds the database before the server has ever run would find them
    missing. Every statement is ``CREATE TABLE IF NOT EXISTS`` /
    ``INSERT OR IGNORE``, so this is safe to run repeatedly.
    """
    WebDatabase(database_path)

    # Import lazily so this module keeps working even if the domain
    # package layout changes; the web package depends on it at runtime.
    from contract_lifecycle.infrastructure.sqlite import (
        ContractSchema,
        DocumentBlobSchema,
        SqliteConnectionFactory,
    )

    connection = SqliteConnectionFactory(database_path).connect()
    try:
        ContractSchema().create_all(connection)
        DocumentBlobSchema().create_all(connection)
    finally:
        connection.close()


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import os

    parser = argparse.ArgumentParser(
        prog="python -m clm_web.db",
        description="Initialize the CLM SQLite database (web + domain schema).",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create all tables if they do not already exist.",
    )
    parser.add_argument(
        "--database",
        default=os.environ.get("CLM_DATABASE_PATH", "clm.sqlite3"),
        help="Path to the SQLite database (default: $CLM_DATABASE_PATH or clm.sqlite3).",
    )
    args = parser.parse_args(argv)

    # --init is the only mode today; treat a bare invocation the same way
    # so the command is never a silent no-op.
    initialize_database(args.database)
    print(f"[OK] Database schema ready at {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
