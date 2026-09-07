# CLM Web

Local-first React portal and FastAPI backend for authenticated, tenant-scoped contract workflows.

The backend uses the existing SQLite CLM database, bearer JWTs for browser/API access, and Hypercorn TLS with HTTP/2 support. Its global Agent Workspace supports organization-wide analysis and attachment-based extraction over SSE. Analysis is handled by the provider-agnostic `query_agent` through the read-only Query MCP server; extraction uses the write-capable Extraction MCP server.

## Local HTTPS/HTTP2

Install `mkcert`, then from the repository root:

```powershell
mkcert -install
New-Item -ItemType Directory -Force .certs
mkcert -cert-file .certs/localhost.pem -key-file .certs/localhost-key.pem localhost 127.0.0.1 ::1
```

Install the workspace and run:

```powershell
uv sync --all-packages
uv run python -m clm_web.server
```

The API is available at `https://localhost:8443`.

## Test Admin

The local SQLite database is already bootstrapped with this development-only
admin account:

- Username: `admin@capstone.local`
- Password: `CapstoneAdmin!2026`
- Organization: `Capstone`

Do not reuse these credentials outside local development. The bootstrap
endpoint is disabled after the first user is created.

## Bun Frontend

From `web/frontend`:

```powershell
bun install
bun run dev
```

The dev server is served over **HTTPS** at `https://localhost:5173` when
`../../.certs/localhost*.pem` exist (the same mkcert pair the API uses); it falls
back to `http` otherwise. `bun run build` checks the production bundle.

Set `VITE_API_URL` when the API is not running at the default
`https://localhost:8443`.

The portal (`web/frontend`) is the contract reader + Agent Workspace + clause
library. Agent observability is a **separate app** (`web/admin`, port 5174) -
see Agent Console below.

## Agent Integration Boundaries

The Agent Workspace opens as a pop-out panel from the **Ask the agent** button
(a floating launcher, always available) or the header **Agent** link. It is not
tied to an open contract and defaults to **Auto** mode. Three modes:

- **Analysis** (`POST /agent/conversations/{id}/messages`) - a tenant-scoped
  question. The orchestrator passes a read-only conversation `history` (rolling
  summary + recent turns) so follow-ups resolve.
- **Extraction** (`POST /agent/conversations/{id}/extractions`) - one PDF/JSON/CSV
  attachment through the extraction pipeline.
- **Auto** (`POST /agent/conversations/{id}/tasks`, multipart, file optional) -
  `planner.plan()` turns one message into a bounded `extract`/`analyze` sequence
  (`PLANNER_MAX_STEPS`, default 3), threading each step's result into the next
  and emitting `needs_confirmation` when extraction is blocked. A non-actionable
  message returns a single clarification.

Agent runs persist safe status events and stream them to the UI or CLI over SSE.
The extraction agent talks only to `extraction_mcp_server`; the query agent talks
only to `query_mcp_server`. Long conversations get a rolling summary
(`agent_conversations.summary`) written after `AGENT_SUMMARY_MIN_TURNS` turns.

See [Memory and Reasoning](../docs/memory-and-reasoning.md).

## Agent Console (separate app)

Agent observability is its **own application** at `web/admin/` -
`https://localhost:5174`, not part of the contract portal. It is admin-only
(the API gates `/agent-admin/*` on the `admin` role).

For any run it shows end to end:

- **Full trace** - every step in order, each with its system prompt, the exact
  context sent (question / user prompt, evidence, RAG, directive), the reasoning
  (CoT) field, the parsed model output, retrieval pool + scores, per-step memory
  snapshot, model/provider, and timing.
- **Memory** - the episodic conversation the run could see, the context
  assembled at the start, and every working-memory snapshot.
- **Timeline** - the safe SSE event log.
- **Extraction traces** - the per-contract extraction stage record.

The trace is persisted in `agent_debug_traces` - **including the partial trace
of a failed run**, so a failure's reasoning is not lost. `run-all.ps1` starts
the console alongside the portal (`-NoConsole` to skip).

APIs (all `contracts:read` + `admin`): `/agent-admin/runs`,
`/agent-admin/runs/{run_id}`, `/agent-admin/runs/{run_id}/debug`,
`/agent-admin/extraction-traces`.

The ordinary chat and SSE stream still carry only safe events. Provider secrets
are never captured.
