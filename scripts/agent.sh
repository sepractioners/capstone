#!/usr/bin/env bash
# Run the orchestrator CLI (clm-agent) against the local API, logging in first
# so you don't have to paste a bearer token.
#
# USAGE:
#   ./scripts/agent.sh <ask|extract|task|watch|chat> [options]
#
# EXAMPLES:
#   ./scripts/agent.sh ask "Which contracts expire this quarter?"
#   ./scripts/agent.sh ask "Show all clauses" --contract-id <uuid>  # Scope to specific contract
#   ./scripts/agent.sh task "extract this and compare to our vendor contracts" --file ./vendor.pdf
#   ./scripts/agent.sh chat
#   ./scripts/agent.sh --email me@org.test --password 'secret' ask "..."
#
# OPTIONS (for wrapper):
#   --api-url URL       API endpoint (default: https://localhost:8443)
#   --email EMAIL       User email (default: admin@capstone.local)
#   --password PASS     User password (default: CapstoneAdmin!2026)
#
# All other options are passed to clm-agent (e.g., --contract-id, --file, --json)
#
# Needs the API running (scripts/run-all.sh). clm-agent is a client, not a
# daemon - it is installed by `uv sync --all-packages`.
set -euo pipefail

API_URL="https://localhost:8443"
EMAIL="admin@capstone.local"
PASSWORD='CapstoneAdmin!2026'

while [[ $# -gt 0 ]]; do
    case "$1" in
        --api-url) API_URL="$2"; shift 2 ;;
        --email) EMAIL="$2"; shift 2 ;;
        --password) PASSWORD="$2"; shift 2 ;;
        *) break ;;
    esac
done

if [[ $# -eq 0 ]]; then
    echo "Usage: ./scripts/agent.sh <ask|extract|task|watch|chat> [args...]" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# -k: the local API uses a mkcert-issued cert that curl won't chain by default.
token_json=$(curl -sk -X POST "$API_URL/auth/token" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    -d "grant_type=password&username=${EMAIL}&password=${PASSWORD}") || {
        echo "Login to $API_URL failed for $EMAIL. Is the API running (scripts/run-all.sh)?" >&2
        exit 1
    }

token=$(printf '%s' "$token_json" | grep -o '"access_token"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/')
if [[ -z "$token" ]]; then
    echo "Login to $API_URL failed for $EMAIL. Is the API running (scripts/run-all.sh)?" >&2
    echo "Response: $token_json" >&2
    exit 1
fi

export CLM_AGENT_TOKEN="$token"
export CLM_API_URL="$API_URL"

cd "$ROOT"
exec uv run clm-agent "$@"
