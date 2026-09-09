#!/bin/bash
set -euo pipefail

# ============================================================================
# Capstone Project Setup Script for macOS
# ============================================================================
#
# WHAT THIS SCRIPT DOES:
#   Prepares the complete Capstone development environment by:
#   1. Creating .env from .env.example (if missing) and telling you it did
#   2. Verifying Python 3.11+ and installing uv (fast package manager)
#   3. Creating Python virtual environment and syncing dependencies
#   4. Installing mkcert and generating HTTPS certificates for local development
#   5. Initializing and seeding the SQLite database (web + domain schema)
#   6. Seeding a synthetic validation portfolio (40 contracts) so the query
#      agent has data to answer against straight after setup
#   7. Setting up Ollama (local LLM) with required models
#   8. Downloading sample contracts from CUAD dataset
#   9. Building RAG knowledge index for extraction agent
#   10. Installing Node.js dependencies for frontend and admin console (bun/npm)
#
# PREREQUISITES:
#   - Python 3.11 or higher
#   - Homebrew (for installing tools like mkcert)
#   - Internet connection (to download dependencies and sample data)
#
# WHAT IT CREATES:
#   - .venv/              Python virtual environment
#   - .certs/             HTTPS certificates for local development
#   - .env                Configuration file (copied from .env.example)
#   - clm.sqlite3         SQLite database (web + domain schema, seeded tenant/admin)
#   - synthetic_data_loader/rag_knowledge.sqlite3  RAG vector index
#   - web/*/node_modules  Node.js dependencies
#
# NEXT STEP AFTER SETUP:
#   Run: bash scripts/run-all.sh

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_NAME="capstone"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_step() { echo -e "${BLUE}==> $1${NC}"; }
log_ok() { echo -e "${GREEN}✓ $1${NC}"; }
log_warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
log_error() { echo -e "${RED}✗ $1${NC}"; }

# Parse arguments
SETUP_OLLAMA=true
SETUP_SAMPLE_DATA=true
SETUP_VALIDATION_DATA=true

while [[ $# -gt 0 ]]; do
  case $1 in
    --no-ollama) SETUP_OLLAMA=false; shift ;;
    --no-sample-data) SETUP_SAMPLE_DATA=false; shift ;;
    --no-validation-data) SETUP_VALIDATION_DATA=false; shift ;;
    -h|--help) sed -n '4,46p' "$0"; cat << 'EOF'

OPTIONS:
  --no-ollama            Skip Ollama installation check (use if you have cloud LLM)
  --no-sample-data       Skip downloading sample contracts
  --no-validation-data   Skip seeding the synthetic validation portfolio
  -h, --help             Show this help message

EXAMPLES:
  bash scripts/setup-mac.sh
  bash scripts/setup-mac.sh --no-ollama
  bash scripts/setup-mac.sh --no-ollama --no-sample-data

For more details, see: https://github.com/anthropics/capstone
EOF
exit 0 ;;
    *) log_error "Unknown option: $1"; exit 1 ;;
  esac
done

# Check macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
  log_error "This script is designed for macOS. Use setup-linux.sh for Linux."
  exit 1
fi

log_step "Capstone Project Setup for macOS"
echo ""

# === 1. Create .env configuration file ===
# Done first so you can review/edit it before the rest of setup runs, and so
# CLM_DATABASE_PATH / EXTRACTION_RAG_DB resolve to the values the app uses.
if [ -f "$ROOT/.env" ]; then
  log_ok ".env already exists - leaving it untouched"
else
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo ""
  log_warn "----------------------------------------------------------------"
  log_warn "Created .env from .env.example"
  log_warn "Defaults: local Ollama (LLM_PROVIDER=ollama, model gemma4:latest)."
  log_warn "Edit .env now for Anthropic/OpenRouter or a different model/db path,"
  log_warn "then re-run this script."
  log_warn "----------------------------------------------------------------"
  echo ""
fi

# === 2. Check and install Homebrew ===
if ! command -v brew &> /dev/null; then
  log_step "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  log_ok "Homebrew installed"
else
  log_ok "Homebrew already installed"
fi

# === 3. Install system dependencies ===
log_step "Installing system dependencies via Homebrew..."

BREW_PACKAGES=(
  "git"
  "python@3.12"
  "openssl@3"
  "sqlite3"
)

for pkg in "${BREW_PACKAGES[@]}"; do
  if brew list "$pkg" &> /dev/null; then
    log_ok "$pkg already installed"
  else
    log_step "Installing $pkg..."
    brew install "$pkg"
    log_ok "$pkg installed"
  fi
done

# === 4. Install uv (Python package manager) ===
if ! command -v uv &> /dev/null; then
  log_step "Installing uv (Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Add to PATH for this session
  export PATH="$HOME/.cargo/bin:$PATH"
  log_ok "uv installed"
else
  log_ok "uv already installed"
fi

# === 5. Set up Python environment ===
log_step "Setting up Python virtual environment..."
cd "$ROOT"

if [ ! -d ".venv" ]; then
  uv venv
  log_ok "Virtual environment created"
else
  log_ok "Virtual environment already exists"
fi

# === 6. Install Python dependencies ===
log_step "Installing Python dependencies..."
uv sync --all-packages
log_ok "Python dependencies installed"

# === 7. Install mkcert for HTTPS ===
if ! command -v mkcert &> /dev/null; then
  log_step "Installing mkcert for local HTTPS certificates..."
  brew install mkcert
  mkcert -install
  log_ok "mkcert installed"
else
  log_ok "mkcert already installed"
fi

# === 8. Generate HTTPS certificates ===
if [ ! -d ".certs" ]; then
  log_step "Generating local HTTPS certificates..."
  mkdir -p .certs
  mkcert -cert-file .certs/localhost.pem -key-file .certs/localhost-key.pem localhost 127.0.0.1 ::1
  log_ok "HTTPS certificates generated"
else
  log_ok "HTTPS certificates already exist"
fi

# === 9. Initialize and seed the SQLite database ===
log_step "Initializing SQLite database..."
DB_PATH=$(grep "^CLM_DATABASE_PATH=" .env | cut -d= -f2- | tr -d '[:space:]')
DB_PATH="${DB_PATH:-./clm.sqlite3}"
DB_FILE="$ROOT/$DB_PATH"

# Schema creation and seeding are both idempotent (CREATE TABLE IF NOT EXISTS /
# the seed script self-skips when a tenant already exists). Run them every time:
# the database file is often created as a side effect of importing the app
# before the tenant/admin user has ever been seeded, so gating on the file's
# existence would silently leave the platform unusable (no org, no login).
source .venv/bin/activate
export CLM_DATABASE_PATH="$DB_PATH"
log_step "Creating database schema at $DB_FILE..."
python -m clm_web.db --init
log_step "Seeding database with default tenant and admin user..."
# --skip-rag: the RAG knowledge base needs an embedding endpoint (Ollama). Keep
# it out of this step so tenant + admin + the validation portfolio always land
# even when Ollama is not running; the RAG index is built best-effort below.
uv run python seed_database.py --skip-cuad --skip-faiss --skip-rag

# Seed the synthetic validation portfolio: deterministic, offline, no LLM.
# seed_contracts.py builds ContractCandidate objects from a fixed seed and
# ingests them through the real handler, then binds them to the Capstone org so
# the query agent has data to answer against the moment setup finishes.
# Idempotent per --seed, so re-running setup is safe.
if [ "$SETUP_VALIDATION_DATA" = true ]; then
  log_step "Seeding synthetic validation portfolio (40 contracts, offline)..."
  if uv run python synthetic_data_loader/seed_contracts.py --seed capstone-review-2026 --count 40 --database-path "$DB_FILE"; then
    log_ok "Validation portfolio seeded (seed: capstone-review-2026)"
  else
    log_warn "Validation portfolio seeding failed - the platform is still usable; seed later with:"
    log_warn "  uv run python synthetic_data_loader/seed_contracts.py --seed capstone-review-2026 --count 40"
  fi
fi
deactivate
log_ok "SQLite database ready at $DB_FILE"

# === 10. Set up Ollama (optional) ===
if [ "$SETUP_OLLAMA" = true ]; then
  log_step "Checking Ollama installation..."

  if ! command -v ollama &> /dev/null; then
    log_step "Installing Ollama..."
    log_warn "Ollama requires manual installation from https://ollama.ai/download"
    log_warn "Please download and install Ollama, then run this script again with --no-ollama if you skip it"

    # Try to open the download page
    open "https://ollama.ai/download" 2>/dev/null || true

    read -p "Press Enter once Ollama is installed, or skip with --no-ollama: "
  else
    log_ok "Ollama installed"
  fi

  # Check if Ollama service is running
  if ! curl -s http://127.0.0.1:11434/api/tags &> /dev/null; then
    log_warn "Ollama is not running. Start it with: ollama serve"
  else
    log_ok "Ollama service is running"

    # Pull required models
    log_step "Ensuring Ollama models are available..."
    if ! ollama list | grep -q "gemma4"; then
      log_step "Pulling gemma4:latest model (this may take a few minutes)..."
      ollama pull gemma4:latest
      log_ok "gemma4:latest model ready"
    else
      log_ok "gemma4:latest already available"
    fi

    if ! ollama list | grep -q "nomic-embed-text"; then
      log_step "Pulling nomic-embed-text:latest model..."
      ollama pull nomic-embed-text:latest
      log_ok "nomic-embed-text:latest model ready"
    else
      log_ok "nomic-embed-text:latest already available"
    fi
  fi
fi

# === 11. Download sample contracts (optional) ===
if [ "$SETUP_SAMPLE_DATA" = true ]; then
  log_step "Setting up sample contracts..."

  SAMPLE_DIR="$ROOT/synthetic_data_loader/data"

  if [ ! -d "$SAMPLE_DIR" ]; then
    mkdir -p "$SAMPLE_DIR"
    log_ok "Sample data directory created"
  fi

  # Download CUAD subset if not present
  if [ ! -f "$SAMPLE_DIR/cuad_subset_manifest.txt" ]; then
    log_step "Downloading CUAD contract samples (may take a few minutes)..."
    source .venv/bin/activate
    python -m synthetic_data_loader.download_cuad_subset
    deactivate
    log_ok "Sample contracts downloaded"
  else
    log_ok "Sample contracts already downloaded"
  fi
fi

# === 12. Build RAG index ===
log_step "Building RAG knowledge index..."
# Read EXTRACTION_RAG_DB from .env or use default
RAG_DB=$(grep "^EXTRACTION_RAG_DB=" .env | cut -d= -f2- | tr -d '[:space:]')
RAG_DB="${RAG_DB:-synthetic_data_loader/rag_knowledge.sqlite3}"

source .venv/bin/activate
export EXTRACTION_RAG_DB="$RAG_DB"

if [ ! -f "$RAG_DB" ]; then
  log_step "Building RAG index at $RAG_DB (first run, may take a minute)..."
  # Best-effort: the RAG index is for the extraction agent only - the query
  # agent (and the reviewer tour) never read it. Needs Ollama nomic-embed-text.
  if python -m extraction_agent.build_rag_index; then
    log_ok "RAG index built"
  else
    log_warn "RAG index build failed (Ollama not running?) - extraction agent will"
    log_warn "fall back to deterministic profiles. Build later with:"
    log_warn "  uv run python -m extraction_agent.build_rag_index"
  fi
else
  log_ok "RAG index already exists at $RAG_DB"
fi

deactivate

# === 13. Install frontend and admin console dependencies ===
for dir in "$ROOT/web/frontend" "$ROOT/web/admin"; do
  if command -v bun &> /dev/null; then
    log_step "Installing dependencies in ${dir#"$ROOT"/} with bun..."
    cd "$dir"
    bun install
    cd "$ROOT"
    log_ok "Dependencies installed in ${dir#"$ROOT"/}"
  else
    log_warn "bun not found - dependencies setup skipped"
    log_warn "Install with: npm install -g bun"
    break
  fi
done

# === Summary ===
echo ""
log_ok "Setup complete!"
echo ""
log_step "Next steps:"
echo ""
echo "1. Start Ollama (if using local LLM):"
echo "   ollama serve"
echo ""
echo "2. Start the applications:"
echo "   bash scripts/run-all.sh --bootstrap  (or scripts/run-all.ps1 -Bootstrap on Windows)"
echo ""
echo "3. Access the portal:"
echo "   Contract Portal:    https://localhost:5173"
echo "   Agent Console:      https://localhost:5174"
echo "   API:                https://localhost:8443"
echo ""
echo "4. Login with:"
echo "   Email:    admin@capstone.local"
echo "   Password: CapstoneAdmin!2026"
echo ""
echo "5. Test extraction:"
echo "   bash scripts/agent.sh ask 'Which contracts expire this quarter?'"
echo ""
