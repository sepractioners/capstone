# Capstone Project Setup Guide

A complete guide to setting up the Contract Lifecycle Management Platform on your local machine.

## Prerequisites

### macOS
- **OS**: macOS 11+ (Intel or Apple Silicon)
- **Disk Space**: ~10GB (for dependencies, models, and sample data)
- **Internet**: Required for initial setup and model downloads
- **Memory**: 8GB minimum (16GB recommended for running Ollama + web app simultaneously)

### Linux
- **OS**: Ubuntu 20.04+ or equivalent
- **Disk Space**: ~10GB
- **Internet**: Required for initial setup
- **Memory**: 8GB minimum

### Windows
- Refer to `scripts/run-all.ps1` for Windows setup

## Quick Start (macOS)

```bash
# 1. Clone or navigate to the repository
cd capstone

# 2. Run the automated setup script
bash scripts/setup-mac.sh

# 3. Start Ollama (in a new terminal)
ollama serve

# 4. Start all applications
bash scripts/run-mac.sh
```

That's it! The portal will be available at https://localhost:5173

## What the Setup Script Does

### 1. System Dependencies
- Installs Homebrew (if needed)
- Installs Python 3.12, Git, SQLite, OpenSSL
- All via `brew install`

### 2. Python Environment
- Installs `uv` (fast Python package manager)
- Creates `.venv` virtual environment
- Installs all Python dependencies across 7 workspace packages
- Single `uv.lock` file ensures reproducible builds

### 3. HTTPS & TLS
- Installs `mkcert` for local CA
- Generates self-signed certificates for localhost
- Enables HTTP/2 via Hypercorn
- Certificates stored in `.certs/` (gitignored)

### 4. Database
- Initializes SQLite database at `capstone.db`
- Creates schema for contracts, obligations, clauses
- Sets up identity/tenant layer
- Gitignored; created fresh per instance

### 5. Environment Configuration
- Creates `.env` file with defaults:
  - LLM provider: `ollama` (local, free), `anthropic` (cloud), or `openrouter` (cloud with API key)
  - Embedding model: `nomic-embed-text:latest`
  - Timeouts, retry counts, feature flags
- User can edit `.env` to switch providers or tune behavior

### 6. Ollama Setup (Optional)
- Checks for Ollama installation
- Pulls required models:
  - `gemma4:latest` — local LLM for extraction and analysis
  - `nomic-embed-text:latest` — local embeddings for RAG
- First pull may take 5-10 minutes depending on bandwidth

### 7. Sample Contracts
- Downloads Kaggle CUAD subset (~500 contracts)
- Stored in `synthetic_data_loader/data/`
- Used for extraction accuracy evaluation and testing

### 8. RAG Knowledge Index
- Builds hybrid retrieval store:
  - **SQLite FTS5**: exact legal terms and headings
  - **Embeddings**: semantic similarity over CUAD examples
- Stored at `synthetic_data_loader/rag_knowledge.sqlite3`
- Enables smart extraction guidance

### 9. Frontend Setup
- Installs Bun package manager (if available)
- Installs React/Vite dependencies in `web/frontend/`
- Enables dev server at https://localhost:5173

## Detailed Setup Steps

### For macOS

```bash
# 1. Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. Install system dependencies
brew install python@3.12 openssl sqlite3 git

# 3. Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# 4. Install mkcert for local HTTPS
brew install mkcert
mkcert -install
mkdir -p .certs
cd capstone
mkcert -cert-file .certs/localhost.pem -key-file .certs/localhost-key.pem localhost 127.0.0.1 ::1

# 5. Create Python virtual environment
uv venv
source .venv/bin/activate

# 6. Install all dependencies
uv sync --all-packages

# 7. Initialize database
python -m web.clm_web.db --init

# 8. Create .env file (or copy .env.example)
cp .env.example .env
# Edit .env to set LLM provider if desired

# 9. Build RAG index
python -m extraction_agent.build_rag_index

# 10. Install frontend dependencies (if bun is available)
brew install bun  # or npm install -g bun
cd web/frontend
bun install
cd ../..
```

### For Linux (Ubuntu)

```bash
# 1. Install system dependencies
sudo apt-get update
sudo apt-get install -y python3.12 python3-pip git sqlite3 libssl-dev

# 2. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# 3. Install mkcert (or use openssl for self-signed certs)
sudo apt-get install -y libnss3-tools
curl -JL https://github.com/FiloSottile/mkcert/releases/download/v1.4.4/mkcert-v1.4.4-linux-amd64 -o mkcert
chmod +x mkcert
sudo mv mkcert /usr/local/bin/

# 4. Follow steps 4-10 from macOS above
```

## Starting the Applications

### Terminal 1: Ollama (LLM Backend)
```bash
ollama serve

# Or if configured for Anthropic:
# - Set LLM_PROVIDER=anthropic in .env
# - Set ANTHROPIC_API_KEY in .env or shell
# - Ollama not needed in that case
```

### Terminal 2: Start All Services
```bash
cd capstone
source .venv/bin/activate

# macOS/Linux
bash scripts/run-mac.sh

# OR Windows
powershell -ExecutionPolicy Bypass -File scripts/run-all.ps1 -Sync -Bootstrap
```

This starts:
- **API Server** (FastAPI + Hypercorn): https://localhost:8443
- **Contract Portal** (React + Vite): https://localhost:5173
- **Agent Console** (Admin observability): https://localhost:5174

## Accessing the Platform

### Login Credentials (Local Development)
- **Email**: `admin@capstone.local`
- **Password**: `CapstoneAdmin!2026`
- **Organization**: `Capstone`

### URLs
- **Contract Portal**: https://localhost:5173 — upload contracts, view clauses, chat with agents
- **Agent Console**: https://localhost:5174 — full extraction/query traces, memory snapshots
- **API**: https://localhost:8443 — programmatic access (requires JWT bearer token)

## Testing the Setup

### Quick Test: Extract and Analyze
```bash
source .venv/bin/activate

# Ask a question about stored contracts
python -m tools.clm_agent_cli ask "Which contracts expire this quarter?"

# Extract and analyze a sample contract
python -m tools.clm_agent_cli task "extract and compare to vendor agreements" --file path/to/contract.pdf
```

### Run Deterministic Scenarios
```bash
# Test domain logic and API workflows
uv run python -m platform_testing.runner platform_testing/scenarios/clause_template_workflow.yaml
```

### Evaluate Extraction Accuracy
```bash
# Score against CUAD ground truth
uv run python -m platform_testing.extraction_eval --limit 8
```

## Environment Variables

### LLM Configuration
```
# Ollama (local, free)
LLM_PROVIDER=ollama
LLM_MODEL=gemma4:latest
OLLAMA_HOST=http://127.0.0.1:11434

# Anthropic (cloud, requires API key)
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=sk-ant-...

# OpenRouter (cloud, requires API key)
LLM_PROVIDER=openrouter
LLM_MODEL=meta-llama/llama-3.1-70b-instruct  # or any OpenRouter model
OPENROUTER_API_KEY=sk-or-...
```

### Embedding Configuration
```
EMBEDDING_MODEL=nomic-embed-text:latest
EMBEDDING_URL=http://127.0.0.1:11434/api/embed
```

### Feature Flags
```
EXTRACTION_RAG_ENABLED=1                # Enable hybrid RAG retrieval
EXTRACTION_REVIEW_ENABLED=1             # Enable document-level review pass
QUERY_PLAN_TOOLS=1                      # Enable LLM planning in query agent
QUERY_INTERPRET=1                       # Enable interpretation step
QUERY_VERIFY=1                          # Enable verification step
PLATFORM_TESTING_EVALUATE=0             # Disable model-based evaluation in tests
```

### Timeouts & Limits
```
LLM_TIMEOUT_SECONDS=300                 # Timeout per LLM call
QUERY_FAST_TIMEOUT_SECONDS=120          # Timeout for best-effort steps
PLANNER_MAX_STEPS=3                     # Max steps in plan-and-execute
```

## Troubleshooting

### Ollama Won't Start
```bash
# Check if already running
curl http://127.0.0.1:11434/api/tags

# Start Ollama
ollama serve

# If not installed, download from https://ollama.ai/download
```

### Models Not Available
```bash
# List available models
ollama list

# Pull required models
ollama pull gemma4:latest
ollama pull nomic-embed-text:latest
```

### HTTPS Certificate Issues
```bash
# Regenerate certificates
rm -rf .certs
mkdir .certs
mkcert -cert-file .certs/localhost.pem -key-file .certs/localhost-key.pem localhost 127.0.0.1 ::1

# Clear browser cache/cookies or open in incognito mode
```

### Database Locked / Connection Errors
```bash
# SQLite database may be locked if another process holds it
# Kill existing processes
pkill -f "python -m clm_web.server"
pkill -f "python -m clm_web.db"

# Optionally reset database (deletes all data)
rm capstone.db
python -m web.clm_web.db --init
```

### Port Already in Use
If ports 5173, 5174, or 8443 are already in use:

```bash
# Check what's using the port (macOS)
lsof -i :8443

# Change ports in scripts/run-mac.sh or run-all.ps1:
# -ApiPort 8444 -FrontendPort 5275 -ConsolePort 5275
```

## Performance Tips

### For Local Llama Models
- **Reduce context size** if running on < 8GB RAM
- **Use quantized models** (`q4`, `q5`) for faster inference
- **Disable RAG retrieval** with `EXTRACTION_RAG_ENABLED=0` for faster extraction

### For Anthropic API
- **Set lower timeout** if you have slow internet
- **Use Haiku model** for extraction (faster, cheaper)
- **Monitor API usage** in the Anthropic dashboard

### For OpenRouter
- **Get API key** from https://openrouter.ai/keys
- **Choose a model** from https://openrouter.ai/models (e.g., Llama 3.1, Qwen, Mistral)
- **No API rate limits** like Anthropic; usage-based billing
- **Set `OPENROUTER_API_KEY`** in `.env` file

## Directory Structure After Setup

```
capstone/
├── .certs/                    # Local HTTPS certificates (gitignored)
├── .venv/                     # Python virtual environment (gitignored)
├── capstone.db                # SQLite database (gitignored)
├── .env                       # Configuration (gitignored)
├── agents/                    # Extraction/Query/Orchestrator agents
├── app/                       # Domain & application layer
├── mcp/                       # MCP servers (extraction + query)
├── web/                       # FastAPI backend + React frontend
├── tools/                     # Shared utilities (contract_calc, CLI)
├── platform_testing/          # YAML scenarios + evaluation
├── synthetic_data_loader/
│   ├── data/                  # Sample contracts (downloaded)
│   └── rag_knowledge.sqlite3  # RAG index (built)
└── scripts/
    ├── setup-mac.sh           # Automated setup for macOS
    ├── run-mac.sh             # Start all apps (macOS)
    └── run-all.ps1            # Start all apps (Windows)
```

## Next Steps

1. **[Read the README](README.md)** for system overview and architecture
2. **[Review the Final Report](CAPSTONE_PLANNING_TEMPLATE_COMPLETED.md)** for detailed design decisions
3. **[Check the Agent Console](https://localhost:5174)** to see full extraction/query traces
4. **[Upload a test contract](https://localhost:5173)** to see extraction in action
5. **[Ask a question](https://localhost:5173)** to test portfolio analysis

## Getting Help

- **For setup issues**: Check the troubleshooting section above or the README
- **For API/integration questions**: See `web/README.md` and `mcp/README.md`
- **For agent design**: See `agents/README.md` and `docs/memory-and-reasoning.md`
- **For domain model**: See `app/README.md` and `docs/contract-lifecycle-ddd.md`

Happy contracting! 🚀
