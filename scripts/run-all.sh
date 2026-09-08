#!/usr/bin/env bash
# Start every local app in the Capstone workspace: the FastAPI/Hypercorn backend,
# the Bun/Vite contract portal, and the agent observability console.
#
#   ./scripts/run-all.sh --sync --bootstrap   sync deps, create the admin account, start
#   ./scripts/run-all.sh --stop               stop apps from a previous run
#
# MCP servers are not started here - the agents spawn them as stdio subprocesses
# on demand. Local LLM features additionally need Ollama running.
set -euo pipefail

SYNC=0; BOOTSTRAP=0; STOP=0
NO_API=0; NO_FRONTEND=0; NO_CONSOLE=0
BIND_HOST="localhost"
API_PORT=8443; FRONTEND_PORT=5173; CONSOLE_PORT=5174
ORG_NAME="Capstone"
ADMIN_EMAIL="admin@capstone.local"
ADMIN_PASSWORD='CapstoneAdmin!2026'
ADMIN_NAME="Capstone Admin"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sync) SYNC=1 ;;
        --bootstrap) BOOTSTRAP=1 ;;
        --stop) STOP=1 ;;
        --no-api) NO_API=1 ;;
        --no-frontend) NO_FRONTEND=1 ;;
        --no-console) NO_CONSOLE=1 ;;
        --host) BIND_HOST="$2"; shift ;;
        --api-port) API_PORT="$2"; shift ;;
        --frontend-port) FRONTEND_PORT="$2"; shift ;;
        --console-port) CONSOLE_PORT="$2"; shift ;;
        --admin-email) ADMIN_EMAIL="$2"; shift ;;
        --admin-password) ADMIN_PASSWORD="$2"; shift ;;
        --org-name) ORG_NAME="$2"; shift ;;
        -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.run"
STATE_FILE="$RUN_DIR/services.tsv"
FRONTEND_DIR="$ROOT/web/frontend"
CONSOLE_DIR="$ROOT/web/admin"
API_BASE="https://${BIND_HOST}:${API_PORT}"

step() { printf '\033[36m==> %s\033[0m\n' "$1"; }
ok()   { printf '\033[32m    %s\033[0m\n' "$1"; }
warn() { printf '\033[33m    %s\033[0m\n' "$1"; }

stop_port_owner() {
    local port=$1
    command -v lsof >/dev/null 2>&1 || return 0
    # bun/vite reparents node, so killing the launcher can miss the real
    # listener - clean up by port as a backstop.
    local pids
    pids="$(lsof -ti "tcp:${port}" -sTCP:LISTEN 2>/dev/null || true)"
    [[ -n "$pids" ]] && kill -9 $pids 2>/dev/null || true
}

stop_services() {
    if [[ ! -f "$STATE_FILE" ]]; then
        warn "No running apps recorded."
        return 0
    fi
    while IFS=$'\t' read -r name pid port; do
        [[ -z "${name:-}" ]] && continue
        if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
            step "Stopping $name (pid $pid) and children"
            pkill -TERM -P "$pid" 2>/dev/null || true
            kill -TERM "$pid" 2>/dev/null || true
        fi
        [[ -n "${port:-}" && "$port" != "0" ]] && stop_port_owner "$port"
    done < "$STATE_FILE"
    rm -f "$STATE_FILE"
    ok "Stopped."
}

wait_port() {
    local host=$1 port=$2 timeout=${3:-90}
    local deadline=$(( SECONDS + timeout ))
    while (( SECONDS < deadline )); do
        if (exec 3<>"/dev/tcp/${host}/${port}") 2>/dev/null; then
            exec 3>&- 2>/dev/null || true
            return 0
        fi
        sleep 0.5
    done
    return 1
}

start_app() {
    local name=$1 workdir=$2 port=$3; shift 3
    local log="$RUN_DIR/${name}.log"
    ( cd "$workdir" && exec "$@" ) >"$log" 2>&1 &
    printf '%s\t%s\t%s\n' "$name" "$!" "$port" >> "$STATE_FILE"
    ok "$name -> log: ${log#"$ROOT"/}"
}

if (( STOP )); then stop_services; exit 0; fi

step "Preflight"
[[ -f "$ROOT/pyproject.toml" ]] || { echo "Run from the repo (expected $ROOT/pyproject.toml)." >&2; exit 1; }
if [[ -f "$STATE_FILE" ]]; then
    warn "Apps already running per $STATE_FILE. Stopping them first."
    stop_services
fi
mkdir -p "$RUN_DIR"

command -v uv >/dev/null 2>&1 || {
    echo "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/" >&2; exit 1; }
ok "uv: $(command -v uv)"

CERT="$ROOT/.certs/localhost.pem"
KEY="$ROOT/.certs/localhost-key.pem"
if (( ! NO_API )); then
    [[ -f "$CERT" && -f "$KEY" ]] || {
        echo "Missing .certs/localhost.pem / localhost-key.pem. Generate with mkcert (see web/README.md)." >&2; exit 1; }
    ok "TLS cert: $CERT"
fi
if (( ! NO_FRONTEND )) || (( ! NO_CONSOLE )); then
    command -v bun >/dev/null 2>&1 || { echo "bun not found. Install it: https://bun.sh" >&2; exit 1; }
    ok "bun: $(command -v bun)"
fi

if (( SYNC )); then
    step "uv sync --all-packages"
    uv sync --all-packages
    for d in "$FRONTEND_DIR:$((NO_FRONTEND))" "$CONSOLE_DIR:$((NO_CONSOLE))"; do
        dir="${d%:*}"; skip="${d##*:}"
        (( skip )) && continue
        step "bun install (${dir#"$ROOT"/})"
        ( cd "$dir" && bun install )
    done
fi

: > "$STATE_FILE"

if (( ! NO_API )); then
    step "Starting API -> $API_BASE"
    CLM_BIND="127.0.0.1:${API_PORT},[::1]:${API_PORT}" \
    CLM_CERTFILE="$CERT" \
    CLM_KEYFILE="$KEY" \
        start_app "api" "$ROOT" "$API_PORT" uv run python -m clm_web.server
    if ! wait_port "$BIND_HOST" "$API_PORT"; then
        warn "API did not open port $API_PORT. See ${RUN_DIR#"$ROOT"/}/api.log"
        stop_services
        exit 1
    fi
    ok "API port $API_PORT is up."
fi

if (( BOOTSTRAP )) && (( ! NO_API )); then
    step "Bootstrapping admin account"
    body=$(printf '{"organization_name":"%s","email":"%s","password":"%s","display_name":"%s"}' \
        "$ORG_NAME" "$ADMIN_EMAIL" "$ADMIN_PASSWORD" "$ADMIN_NAME")
    code=$(curl -sk -o /dev/null -w '%{http_code}' -X POST "$API_BASE/auth/bootstrap" \
        -H 'Content-Type: application/json' -d "$body" || echo 000)
    case "$code" in
        2*) ok "Created $ADMIN_EMAIL (org '$ORG_NAME')." ;;
        409) warn "Bootstrap already complete - leaving the existing users alone." ;;
        *) echo "Bootstrap failed (HTTP $code)." >&2; exit 1 ;;
    esac
fi

FE_SCHEME="http"; [[ -f "$CERT" ]] && FE_SCHEME="https"

if (( ! NO_FRONTEND )); then
    step "Starting contract portal -> ${FE_SCHEME}://${BIND_HOST}:${FRONTEND_PORT}"
    start_app "frontend" "$FRONTEND_DIR" "$FRONTEND_PORT" bun run dev
    # First run after a dep change pre-bundles; give Vite generous headroom.
    if wait_port "$BIND_HOST" "$FRONTEND_PORT" 180; then ok "Portal port $FRONTEND_PORT is up."
    else warn "Portal port $FRONTEND_PORT not up yet - check ${RUN_DIR#"$ROOT"/}/frontend.log"; fi
fi

if (( ! NO_CONSOLE )); then
    step "Starting agent console -> ${FE_SCHEME}://${BIND_HOST}:${CONSOLE_PORT}"
    start_app "console" "$CONSOLE_DIR" "$CONSOLE_PORT" bun run dev
    if wait_port "$BIND_HOST" "$CONSOLE_PORT" 180; then ok "Console port $CONSOLE_PORT is up."
    else warn "Console port $CONSOLE_PORT not up yet - check ${RUN_DIR#"$ROOT"/}/console.log"; fi
fi

echo
printf '\033[32m  Capstone is running\033[0m\n'
echo "  -------------------"
(( NO_FRONTEND )) || echo "  Portal    ${FE_SCHEME}://${BIND_HOST}:${FRONTEND_PORT}   (contract workspace)"
(( NO_CONSOLE ))  || echo "  Console   ${FE_SCHEME}://${BIND_HOST}:${CONSOLE_PORT}   (agent observability, admin only)"
(( NO_API ))      || echo "  API       ${API_BASE}        (health: ${API_BASE}/health)"
(( NO_API ))      || echo "  Login     ${ADMIN_EMAIL}  /  ${ADMIN_PASSWORD}"
echo
echo "  Logs in ${RUN_DIR#"$ROOT"/}/. Stop everything with:"
echo "      ./scripts/run-all.sh --stop"
if [[ -f "$ROOT/.env" ]]; then
    llm=$(grep -E '^(LLM_PROVIDER|LLM_MODEL|OLLAMA_HOST|EMBEDDING_URL|EMBEDDING_MODEL)=' "$ROOT/.env" | tr '\n' ' ' || true)
    echo
    echo "  LLM config (.env): $llm"
else
    echo
    echo "  Note: no .env found - copy .env.example to .env and set LLM_PROVIDER/LLM_MODEL."
fi
echo
