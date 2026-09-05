# CLM Web

Local-first React portal and FastAPI backend for authenticated, tenant-scoped contract workflows.

The backend uses the existing SQLite CLM database, bearer JWTs for browser/API access, and Hypercorn TLS with HTTP/2 support. See the repository's extraction-agent documentation for the pipeline architecture.

## Local HTTPS/HTTP2

Install `mkcert`, then from the repository root:

```powershell
mkcert -install
New-Item -ItemType Directory -Force .certs
mkcert -cert-file .certs/localhost.pem -key-file .certs/localhost-key.pem localhost 127.0.0.1 ::1
```

Install the package and run:

```powershell
python -m pip install -e .\app
python -m pip install -e .\mcp
python -m pip install -e .\web
python -m clm_web.server
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

The production bundle can be checked with:

```powershell
bun run build
```

Set `VITE_API_URL` when the API is not running at the default
`https://localhost:8443`.

## Agent Integration Boundaries

Contract uploads use the existing `extraction_agent` pipeline and persist
through the CLM domain. Contract questions are reserved for a separate
`query_agent` package, which is not implemented yet; the portal shows the
integration surface but the API returns `501` until that agent is connected.
