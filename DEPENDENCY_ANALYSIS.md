# Capstone Project Dependency Analysis

## Current State

### System vs. Python Dependencies

**Currently scattered**:
- **System tools** (openssl, sqlite3, git, uv, mkcert, bun) — declared only in bash/PowerShell setup scripts
- **Python packages** — declared in individual `pyproject.toml` files
- **No unified source of truth** for the complete dependency graph

**Current setup flow**:
```
setup-mac.sh (manual system installs)
    ↓
pyproject.toml (workspace + members)
    ↓
uv sync --all-packages (resolve + install Python)
    ↓
More manual steps (DB init, cert generation, data download, frontend setup)
```

### Workspace Structure
The project uses a **uv workspace** with 8 member packages:
- `app` — domain layer (contract-lifecycle)
- `mcp` — MCP servers (clm-mcp-server)
- `agents` — extraction/query/orchestrator agents (extraction-agent)
- `web` — FastAPI backend + React frontend (clm-web)
- `platform_testing` — YAML scenario runner + evaluator (clm-platform-testing)
- `tools/contract_calc` — contract calculations (contract-calc)
- `tools/clm_agent_cli` — CLI tool (clm-agent-cli)
- `synthetic_data_loader` — CUAD dataset downloader (sythetic-data-loader)

**Root workspace file**: `pyproject.toml` — contains member list and shared dev dependencies.

### Current Dependency Model

**Direct Python dependencies** (declared in individual `pyproject.toml`):
```
contract-lifecycle (app)
├── (no dependencies)

clm-mcp-server (mcp)
├── contract-lifecycle
├── extraction-agent
└── mcp>=1.29,<2

extraction-agent (agents)
├── any-llm-sdk[anthropic,ollama]
├── langgraph
├── llama-index-core
├── llama-index-readers-file
├── mcp>=1.29,<2
├── pydantic>=2
├── pyyaml>=6
└── python-dotenv>=1.0
    └── (optional) faiss-cpu, numpy<2 [rag]

clm-web (web)
├── contract-lifecycle
├── clm-mcp-server
├── extraction-agent
├── any-llm-sdk[anthropic,ollama]
├── fastapi>=0.115
├── hypercorn>=0.17
├── PyJWT>=2.9
└── python-multipart>=0.0.20

clm-platform-testing (platform_testing)
├── any-llm-sdk[anthropic,ollama]
├── clm-web
├── extraction-agent
├── PyYAML>=6
└── python-dotenv>=1.0

sythetic-data-loader (synthetic_data_loader)
├── extraction-agent
└── kagglehub

clm-agent-cli (tools/clm_agent_cli)
├── httpx>=0.27
└── typer>=0.12

contract-calc (tools/contract_calc)
└── (not shown - check pyproject.toml)
```

**Lock file**: `uv.lock` (3948 lines) — ensures reproducible builds across all platforms.

### Setup Script Dependencies (setup-mac.sh)

The setup script **manually orchestrates** Python installation and ancillary tasks:

1. **System dependencies** (via Homebrew):
   - python@3.12, openssl@3, sqlite3, git
   - uv (Python package manager)
   - mkcert (TLS certificate generation)
   - bun (frontend package manager)

2. **Python environment & packages**:
   - Creates `.venv` virtual environment
   - Runs `uv sync --all-packages` to install workspace dependencies
   - No error handling if `uv.lock` is stale

3. **Database**:
   - Initializes SQLite schema (`python -m web.clm_web.db --init`)
   - Creates `capstone.db` (gitignored)

4. **Configuration**:
   - Generates `.env` file with LLM defaults
   - Hard-coded provider, model, and timeout values

5. **HTTPS/TLS**:
   - Generates self-signed certificates with `mkcert`
   - Stores in `.certs/` (gitignored)

6. **Ollama** (optional local LLM):
   - Pulls `gemma4:latest` and `nomic-embed-text:latest` models
   - Creates `~10GB` disk footprint

7. **Sample data**:
   - Downloads CUAD subset (~500 contracts)
   - Runs `python -m synthetic_data_loader.download_cuad_subset`

8. **RAG index**:
   - Builds `synthetic_data_loader/rag_knowledge.sqlite3`
   - Runs `python -m extraction_agent.build_rag_index`

9. **Frontend**:
   - Installs Bun dependencies (`web/frontend`, `web/admin`)

---

## Issues

### 1. **Scattered Setup Logic**
- Python setup is split between:
  - `setup-mac.sh` (system + environment + optional features)
  - `scripts/run-all.ps1` (Windows-specific orchestration)
  - Individual `pyproject.toml` files (package dependencies)
- Result: Hard to understand full dependency tree at a glance.

### 2. **Optional Dependencies Are Implicit**
- RAG feature requires `faiss-cpu` + `numpy<2` but the setup script doesn't enforce this.
- Ollama setup is optional but not reflected in `pyproject.toml` extras.
- Sample data is downloaded during setup, not as a dev dependency.

### 3. **Configuration Hardcoded in Setup Script**
- `.env` defaults are baked into `setup-mac.sh` instead of committed as `.env.example` (which exists separately).
- If default values change, multiple files must be updated.

### 4. **Transitive Dependencies Not Declared**
- Many indirect dependencies (e.g., `FastAPI` → `starlette`, `pydantic`, etc.) are not explicitly declared.
- `uv.lock` captures them, but there's no audit trail of why they're needed.

### 5. **Platform-Specific Scripts**
- Two separate scripts: `scripts/setup-mac.sh` and `scripts/run-all.ps1`.
- No unified way to express setup requirements across OSes.
- Linux setup relies on manual steps documented in `SETUP.md`.

### 6. **Dependency Duplication**
- `any-llm-sdk[anthropic,ollama]` is declared in 3+ packages independently.
- `pyyaml` and `python-dotenv` declared in multiple places.
- Could be deduplicated at workspace level.

---

## System Dependencies

The setup script currently installs these **outside** of Python's dependency system:

| Tool | Version | Purpose | Used by |
|------|---------|---------|----------|
| `python` | 3.12+ | Runtime | All packages |
| `git` | 2.20+ | Version control | Dev workflows |
| `openssl` | 3.x | TLS libraries | hypercorn, FastAPI |
| `sqlite3` | 3.35+ | Database | clm-web, sythetic-data-loader |
| `uv` | 0.5+ | Python package manager | Setup/CI |
| `mkcert` | 1.4+ | Local CA + cert generation | HTTPS setup |
| `bun` | 1.0+ | Frontend package manager | web/frontend, web/admin |

**Problem**: These are documented only in the bash script, not in the project configuration.

### Declaring System Dependencies in pyproject.toml

Modern approaches to express system-level requirements:

#### **Option A: PEP 735 (Explicit Environment Markers)**
```toml
# In root pyproject.toml - requires PEP 735 support (Python 3.13+)
[project]
requires-system = [
    { name = "python", version = ">=3.12" },
    { name = "git", version = ">=2.20" },
    { name = "openssl", version = ">=3.0", platforms = ["linux", "darwin"] },
    { name = "sqlite3", version = ">=3.35" },
]

[tool.uv.requires-system]
uv = ">=0.5"
mkcert = ">=1.4"
bun = ">=1.0"
```

**Status**: PEP 735 is still in discussion; not yet standard.

---

#### **Option B: Tool-Specific Metadata (Recommended Now)**

**For `uv` (Astral's approach)**:
```toml
# pyproject.toml (root)
[tool.uv]
python-version = "3.12"

[tool.uv.requires-system]
# uv can express system dependencies
git = ">=2.20"
openssl = ">=3.0"
sqlite3 = ">=3.35"
mkcert = ">=1.4"
bun = ">=1.0"

# Platform-specific system deps
[tool.uv.requires-system.linux]
build-essential = "*"
python3-dev = "*"
libssl-dev = "*"

[tool.uv.requires-system.macos]
# Homebrew manages these

[tool.uv.requires-system.windows]
# Chocolatey or Windows Package Manager
```

**For `pixi` (cross-platform conda-based)**:
```toml
# pixi.toml
[project]
name = "capstone"
version = "0.1.0"
channels = ["conda-forge"]
platforms = ["linux-64", "linux-aarch64", "osx-64", "osx-arm64", "win-64"]

[dependencies]
python = "3.12.*"
git = ">=2.20"
openssl = "3.*"
sqlite = "3.35.*"
uv = ">=0.5"
mkcert = "1.4.*"
bun = "1.0.*"

[pypi-dependencies]
# Python packages...
```

This is **production-ready** and handles macOS/Linux/Windows system deps automatically.

---

#### **Option C: Declarative Manifest (Self-Documenting)**

Create a `system-requirements.toml` file:
```toml
# system-requirements.toml - source of truth for all system deps
[dependencies]
python = { version = ">=3.12", required = true }
git = { version = ">=2.20", required = true }
sqlite3 = { version = ">=3.35", required = true }
openssl = { version = ">=3.0", required = false, note = "For HTTPS; Homebrew/apt provides" }

[dev-dependencies]
uv = { version = ">=0.5", note = "Python package manager" }
mkcert = { version = ">=1.4", note = "Local HTTPS certificate generation" }
bun = { version = ">=1.0", note = "Frontend package manager for Vite" }

[platform-specific.linux]
build-essential = { note = "For compiling C extensions (numpy, faiss)" }
python3-dev = {}
libssl-dev = {}

[platform-specific.macos]
# Installed via Homebrew

[platform-specific.windows]
# Installed via Chocolatey / Windows Package Manager
```

Then reference in `setup.py` or `setup.ps1`:
```python
import toml

config = toml.load("system-requirements.toml")
for tool, spec in config["dependencies"].items():
    print(f"Requires {tool} {spec['version']}")
```

---

#### **Option D: Docker + Multi-Stage Build (Cleanest Segregation)**

```dockerfile
# Dockerfile (root)
FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    git \
    sqlite3 \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy project
COPY . /app
WORKDIR /app

# Install Python deps + build
RUN uv sync --all-packages
RUN uv run python -m web.clm_web.db --init
```

Then for local dev:
```bash
# Using Docker - no system deps needed on host except Docker
docker run -it --rm -v $(pwd):/app capstone bash

# Or traditional setup - consults Dockerfile for what's needed
bash scripts/setup-mac.sh
```

---

## Recommendations

### Short Term (Easy Wins)

**1. Create a system requirements declaration**
```toml
# system-requirements.toml (new file at root)
[required]
python = ">=3.12"
git = ">=2.20"
sqlite3 = ">=3.35"
openssl = ">=3.0"

[dev-tools]
uv = ">=0.5"
mkcert = ">=1.4"
bun = ">=1.0"

[platform-specific.linux]
build-essential = "*"
libssl-dev = "*"

[platform-specific.macos]
# Homebrew handles these

[platform-specific.windows]
# Chocolatey or Windows Package Manager
```

Then document in `setup-mac.sh` / `run-all.ps1`:
```bash
# At the top of setup-mac.sh
if ! command -v git &> /dev/null; then
  log_error "git is required. Install: brew install git"
  log_error "See system-requirements.toml for all required tools."
  exit 1
fi
```

**2. Create a root-level dev dependency group**
```toml
# In pyproject.toml (root)
[dependency-groups]
dev = ["pytest>=8"]
eval = ["any-llm-sdk[anthropic,ollama]", "clm-platform-testing"]
rag = ["faiss-cpu>=1.8", "numpy<2"]
all = ["dep:eval", "dep:rag"]
```

**2. Declare shared dependencies once**
- Move `pyyaml`, `python-dotenv`, `any-llm-sdk` to root `[dependency-groups]`
- Reference from child packages with `[project]dependencies` pointing to root group.
  *(Note: uv doesn't support this pattern directly; consider using poetry or pip-tools for shared deps.)*

**3. Create optional extras in `agents/pyproject.toml`**
```toml
[project.optional-dependencies]
rag = ["faiss-cpu>=1.8", "numpy<2"]
```
Then declare `extraction-agent[rag]` in packages that need RAG.

**4. Document dependency decisions**
- Add `DEPENDENCIES.md` explaining why each transitive dependency is needed.
- List known conflicts (e.g., `numpy<2` for compatibility with older FAISS).

---

### Medium Term (Better Organization)

**1. Separate "runtime" from "setup" Python packages**
Create two installation profiles:
```bash
# Minimal: only packages needed to run the app
uv sync --group runtime

# Full setup: includes dev tools, RAG, Ollama utilities, sample data loaders
uv sync --all-groups
```

**2. Move setup orchestration to Python**
Replace `setup-mac.sh` with a Python setup module (e.g., `tools/setup/__init__.py`):
```bash
python -m tools.setup --platform macos --no-ollama --skip-sample-data
```
Benefits:
- Single codebase for all platforms.
- Can be invoked programmatically by CI/CD.
- Easier to test.

**3. Use pyproject.toml `[project.scripts]`**
```toml
# In web/pyproject.toml
[project.scripts]
clm-init-db = "clm_web.db:init"
```
Then setup becomes:
```bash
uv sync
clm-init-db
clm-gen-certs
clm-download-sample-data
```

**4. Create an explicit setup checklist**
```yaml
# setup.yaml
steps:
  - name: system-deps
    platforms: [macos, linux, windows]
    commands:
      macos: ["brew install python@3.12 openssl@3 sqlite3"]
      linux: ["apt-get install python3.12 libssl-dev sqlite3"]
      windows: ["choco install python openssl sqlite"]
  
  - name: python-venv
    command: "uv venv"
  
  - name: deps
    command: "uv sync --all-groups"
  
  - name: database
    command: "clm-init-db"
  
  - name: tls-certs
    command: "clm-gen-certs"
    optional: true
    note: "Skip if using --insecure"
  
  - name: sample-data
    command: "clm-download-sample-data"
    optional: true
    group: "evaluation"
  
  - name: frontend
    command: "cd web/frontend && bun install"
```

---

### Long Term (Architectural)

**1. Pin all transitive dependencies**
- Use `uv pip compile` to generate pinned requirements files alongside `uv.lock`.
- Publish a `requirements.txt` / `constraints.txt` for downstream consumers.

**2. Separate platform from setup**
- Move OS-level setup (Homebrew, apt, choco) to a separate config or CI/CD step.
- Keep `uv.lock` and Python setup as platform-agnostic.

**3. Split LLM provider support**
```toml
[project.optional-dependencies]
llm-anthropic = ["any-llm-sdk[anthropic]"]
llm-ollama = ["any-llm-sdk[ollama]"]
llm-openai = ["any-llm-sdk[openai]"]
llm-all = [
    "dep:llm-anthropic",
    "dep:llm-ollama",
    "dep:llm-openai",
]
```
Allows users to install only the providers they need.

---

## Action Items

### System Dependencies
- [ ] **Create `system-requirements.toml`** — Declare all OS-level tools (openssl, sqlite3, git, uv, mkcert, bun) in one place.
- [ ] **Add validation to setup scripts** — Check for required system tools before proceeding (fail early with clear instructions).
- [ ] **Document platform-specific installs** — For each OS (Homebrew, apt-get, choco), list exact installation commands.
- [ ] **Consider `pixi.toml`** — If cross-platform system dep management is a long-term goal.

### Python Dependencies
- [ ] **Document actual transitive dependencies** — Add a `DEPENDENCIES.md` file explaining each top-level dependency and its role.
- [ ] **Add optional dependency groups** — Create `[dependency-groups]` in root for `rag`, `eval`, `all`.
- [ ] **Deduplicate shared deps** — Move `pyyaml`, `python-dotenv`, `any-llm-sdk` to workspace-level or dependency groups.
- [ ] **Audit shared deps** — Identify duplicates and consolidate declarations.

### Setup & Automation
- [ ] **Create a Python setup module** — Replace bash scripts with `python -m tools.setup` that reads `system-requirements.toml`.
- [ ] **Add CI/CD integration** — Use setup module in GitHub Actions / local pre-commit hooks.
- [ ] **Write platform matrix** — Document tested platform versions (macOS 12+, Ubuntu 22.04+, Windows 11, etc.).

### Documentation
- [ ] **Update SETUP.md** — Reference `system-requirements.toml` instead of repeating version numbers.
- [ ] **Add troubleshooting guide** — Link version mismatches to `system-requirements.toml`.

