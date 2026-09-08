#!/usr/bin/env bash
# ============================================================================
# Capstone Project - Start All Services
# ============================================================================
#
# WHAT THIS SCRIPT DOES:
#   Starts the complete Capstone application stack:
#   1. Verifies all required tools (uv, bun, Python, Node)
#   2. Checks LLM provider configuration (Ollama or OpenRouter)
#   3. Syncs Python and Node dependencies (unless --no-sync)
#   4. Starts FastAPI backend (HTTPS on port 8443)
#   5. Starts Vite frontend - Contract Portal (HTTPS on port 5173)
#   6. Starts Vite frontend - Agent Console (HTTPS on port 5174)
#   7. Optionally creates admin account on first run
#
# PREFLIGHT CHECKS:
#   - Verifies uv, bun, Python, mkcert are installed
#   - Checks HTTPS certificates exist (.certs/)
#   - Checks LLM_PROVIDER setting in .env
#   - Verifies Ollama is running (if using local LLM)
#   - Verifies OpenRouter API key (if using cloud LLM)
#
# SERVICES STARTED:
#   - Backend API:         https://localhost:8443  (FastAPI + Hypercorn)
#   - Contract Portal:     https://localhost:5173  (Vite + React)
#   - Agent Console:       https://localhost:5174  (Vite + React, admin only)
#
# OUTPUT:
#   - Logs written to .run/*.log
#   - Service status in .run/services.tsv
#   - Stop with: ./scripts/run-all.sh --stop
#
# USAGE:
#   ./scripts/run-all.sh                      sync deps and start all services
#   ./scripts/run-all.sh --bootstrap          create admin account on first run
#   ./scripts/run-all.sh --no-sync            start without syncing dependencies
#   ./scripts/run-all.sh --stop               stop all running services
#
# OPTIONS:
#   --no-sync                 skip uv sync and bun install (assumes deps installed)
#   --bootstrap               create local admin account (email: admin@capstone.local)
#   --stop                    stop services from a previous run
#   --no-api, --no-frontend, --no-console    skip starting specific services
#   --host HOST               bind to HOST instead of localhost
#   --api-port PORT           API port (default: 8443)
#   --frontend-port PORT      frontend port (default: 5173)
#   --console-port PORT       console port (default: 5174)
#
# LLM CONFIGURATION (from .env):
#   Reads LLM_PROVIDER setting and validates configuration:
#   - ollama:     requires Ollama running on http://127.0.0.1:11434
#   - openrouter: requires OPENROUTER_API_KEY in .env
#   Script will STOP if LLM is not properly configured or not running.
#
# CREDENTIALS (on first run with --bootstrap):
#   - Email:    admin@capstone.local
#   - Password: CapstoneAdmin!2026
#
# MCP SERVERS:
#   Spawned by agents as needed (not started by this script)
set -euo pipefail

SYNC=1; BOOTSTRAP=0; STOP=0
NO_API=0; NO_FRONTEND=0; NO_CONSOLE=0
BIND_HOST="localhost"
API_PORT=8443; FRONTEND_PORT=5173; CONSOLE_PORT=5174
ORG_NAME="Capstone"
ADMIN_EMAIL="admin@capstone.local"
ADMIN_PASSWORD='CapstoneAdmin!2026'
ADMIN_NAME="Capstone Admin"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-sync) SYNC=0 ;;
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
        -h|--help) sed -n '2,56p' "$0"; exit 0 ;;
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

# === Check LLM Provider Configuration ===
ENV_FILE="$ROOT/.env"
LLM_PROVIDER="ollama"
if [[ -f "$ENV_FILE" ]]; then
    LLM_PROVIDER=$(grep -E '^LLM_PROVIDER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' ')
    [[ -z "$LLM_PROVIDER" ]] && LLM_PROVIDER="ollama"
fi

if [[ "$LLM_PROVIDER" == "ollama" ]]; then
    step "Checking Ollama service (LLM_PROVIDER=ollama)..."
    if ! curl -s http://127.0.0.1:11434/api/tags &>/dev/null; then
        log_error "Ollama is not running on http://127.0.0.1:11434"
        echo ""
        echo "Options:"
        echo "  1. Start Ollama: ollama serve"
        echo "  2. Switch to OpenRouter API: edit .env and set LLM_PROVIDER=openrouter"
        echo ""
        exit 1
    fi
    ok "Ollama is running"
elif [[ "$LLM_PROVIDER" == "openrouter" ]]; then
    step "Checking OpenRouter configuration..."
    OPENROUTER_KEY=$(grep -E '^OPENROUTER_API_KEY=' "$ENV_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' ')
    if [[ -z "$OPENROUTER_KEY" ]]; then
        log_error "OpenRouter API key not found in .env"
        echo "Set OPENROUTER_API_KEY in .env file" >&2
        exit 1
    fi
    ok "OpenRouter API key configured"
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
