# Capstone Project Setup Guide

A complete guide to setting up the Contract Lifecycle Management Platform on your local machine.

## Quick Start

### macOS
```bash
bash scripts/setup-mac.sh       # Setup everything
ollama serve                    # Start LLM (new terminal)
bash scripts/run-mac.sh         # Start apps
```

### Windows
```powershell
.\scripts\setup-windows.ps1     # Setup everything
ollama serve                    # Start LLM (new terminal)
.\scripts\run-all.ps1           # Start apps
```

**That's it!** Portal available at https://localhost:5173

## Prerequisites

See [system-requirements.toml](system-requirements.toml) for all dependencies and install commands.

**Minimum:**
- Python 3.12+
- Git
- SQLite
- OpenSSL
- ~10GB disk space
- 8GB RAM (16GB recommended for Ollama + web app)

## What the Setup Scripts Do

- ✅ Install system dependencies (Python, Git, SQLite, OpenSSL, mkcert, uv)
- ✅ Create Python virtual environment and install packages
- ✅ Generate HTTPS certificates for localhost
- ✅ Initialize SQLite database
- ✅ Create `.env` configuration file
- ✅ Download sample CUAD contracts (optional)
- ✅ Build RAG knowledge index
- ✅ Install frontend dependencies (bun or npm)
- ✅ Pull Ollama models (optional)

No manual steps needed - the scripts handle everything!

## Manual Setup (if not using setup scripts)

If you prefer to set things up manually, follow the detailed steps for your platform:

- **macOS**: See `scripts/setup-mac.sh` for exact commands
- **Windows**: See `scripts/setup-windows.ps1` for exact commands
- **Linux**: Create similar script based on macOS version (apt-get instead of brew)

Or just check [system-requirements.toml](system-requirements.toml) for all dependencies and run the setup scripts!

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

### Windows-Specific Issues

#### PowerShell ExecutionPolicy Error
If you get "cannot be loaded because running scripts is disabled on this system":
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# Then re-run the activation command: .\.venv\Scripts\Activate.ps1
```

#### System Dependencies Not Found
If you get "command not found" for `mkcert`, `uv`, `bun`, or other tools:
- Check [system-requirements.toml](system-requirements.toml) for your platform's install commands
- Ensure the tool is installed and in PATH
- For Chocolatey tools: restart PowerShell after install to refresh PATH
- For command-line installers: may need to add to PATH manually

#### bun not found (frontend dependencies)
If bun is not available and you prefer npm:
```powershell
cd web\frontend
npm install
cd ..\..
```

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
