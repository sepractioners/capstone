# Capstone Dependency Management Guide

This document explains how the Capstone project manages dependencies across system tools, Python packages, and development workflows.

## Overview

The project now has three layers of dependency management:

```
system-requirements.toml
    ↓ (declarative source of truth)
    ├─ tools/setup/main.py (validation & orchestration)
    └─ setup-mac.sh, run-all.ps1 (reference implementations)

pyproject.toml (root)
    ├─ [tool.uv.workspace] — 8 Python packages
    └─ [dependency-groups] — shared deps + feature groups

Individual pyproject.toml files
    └─ Package-specific dependencies
```

---

## 1. System Dependencies (system-requirements.toml)

### Purpose
Declare all OS-level tools needed for development and runtime:
- Runtime: python, git, sqlite3, openssl
- Development: uv, mkcert, bun
- Platform-specific: build-essential (Linux), Xcode CLT (macOS), etc.

### File Location
`system-requirements.toml` (at project root)

### Structure
```toml
[required]           # Must have before setup
[dev-tools]          # Needed for development
[platform-specific]  # OS-specific requirements
[optional-features]  # Ollama, Docker, PostgreSQL, etc.
[constraints]        # Known version conflicts
[validation]         # Checklist to verify
```

### Example: Viewing Requirements
```bash
# See what's required
cat system-requirements.toml | grep -A5 "\[required\]"

# Check the validation checklist
python -m tools.setup --validate-only
```

### Updating System Requirements
When you need to change a version (e.g., upgrading Python from 3.12 to 3.13):

1. **Edit `system-requirements.toml`**:
   ```toml
   [required.python]
   version = ">=3.13"
   ```

2. **Update setup scripts** to match (they reference the TOML):
   ```bash
   # setup-mac.sh
   brew install python@3.13  # instead of python@3.12
   ```

3. **Document the change** in the file as a comment:
   ```toml
   # 2026-09-07: Bumped to 3.13 for async/await improvements
   ```

---

## 2. Python Dependencies (pyproject.toml)

### Root Workspace (pyproject.toml)

Declares **workspace members** and **shared dependency groups**:

```toml
[tool.uv.workspace]
members = [
    "app",                      # contract-lifecycle
    "mcp",                      # clm-mcp-server
    "agents",                   # extraction-agent
    "web",                      # clm-web
    "platform_testing",         # clm-platform-testing
    "tools/contract_calc",      # contract-calc
    "tools/clm_agent_cli",      # clm-agent-cli
    "synthetic_data_loader",     # synthetic-data-loader
]

[dependency-groups]
# Core shared dependencies
llm = ["any-llm-sdk[anthropic,ollama]"]
rag = ["faiss-cpu>=1.8", "numpy<2"]
config = ["pyyaml>=6", "python-dotenv>=1.0"]

# Feature combinations
eval = ["dep:llm", "clm-platform-testing"]
all = ["dep:dev", "dep:llm", "dep:rag", "dep:config", "dep:eval"]
```

### Installing with Groups

```bash
# Minimal (only runtime packages)
uv sync

# Development + testing
uv sync --group dev

# With LLM support
uv sync --group llm

# With RAG (FAISS + embeddings)
uv sync --group rag

# Everything
uv sync --all-groups
```

### Individual Package pyproject.toml Files

Each workspace member declares its **direct dependencies**:

```toml
# agents/pyproject.toml
[project]
name = "extraction-agent"
dependencies = [
    "langgraph",
    "llama-index-core",
    # ... other direct deps
    "pyyaml>=6",             # Now available from root group
    "python-dotenv>=1.0",    # Now available from root group
]

[project.optional-dependencies]
rag = ["faiss-cpu>=1.8", "numpy<2"]  # For semantic search
```

### Adding a New Dependency

**If it's used by multiple packages:**
1. Add it to `[dependency-groups]` in root `pyproject.toml`
2. Reference it in individual packages via `[dependency-groups]` in the package

**If it's package-specific:**
1. Add it directly to the package's `pyproject.toml`

Example: Adding `requests` for HTTP calls in `clm-agent-cli`:
```toml
# tools/clm_agent_cli/pyproject.toml
[project]
dependencies = [
    "httpx>=0.27",    # ← already declared
    "requests>=2.31",  # ← new, add it here
]
```

---

## 3. Setup Orchestration (tools/setup/)

### Purpose
Cross-platform setup that reads `system-requirements.toml` and automates:
- Validating system requirements
- Creating Python venv
- Installing Python dependencies
- Database initialization
- HTTPS certificate generation
- Optional: sample data, RAG index, frontend

### Usage

```bash
# Validate system requirements only (no installation)
python -m tools.setup --validate-only

# Standard setup (venv + Python deps + DB + certs)
python -m tools.setup

# Full setup including RAG and sample data
python -m tools.setup --all

# Skip optional features
python -m tools.setup --no-sample-data --skip-rag
```

### How It Works

1. **Loads system-requirements.toml**
2. **Validates required tools** (python, git, sqlite3, openssl, uv, mkcert, bun)
3. **Creates venv** with `uv venv`
4. **Syncs dependencies** with `uv sync --all-groups`
5. **Initializes database** with `python -m web.clm_web.db --init`
6. **Generates HTTPS certs** with `mkcert`
7. **(Optional) Downloads sample contracts** and **builds RAG index**
8. **(Optional) Installs frontend deps** with `bun install`

### Output
```
Capstone Setup
==================================================
Platform: macos

==> Validating system requirements for macos
✓ python 3.12.0
✓ git 2.46.0
✓ sqlite3 3.46.0
✓ openssl 3.3.0
✓ uv 0.5.1
✓ mkcert 1.4.4
✓ bun 1.1.4

==> Setting up Python virtual environment
✓ Virtual environment created

==> Installing Python dependencies
✓ Dependencies synced

==> Initializing SQLite database
✓ Database initialized

==> Generating HTTPS certificates
✓ HTTPS certificates generated

==> Installing frontend dependencies
✓ Frontend dependencies installed

==================================================
✓ Setup complete!

Next steps:
1. Start Ollama (if using local LLM): ollama serve
2. Start all services: python -m tools.setup start
3. Access: https://localhost:5173
```

---

## 4. Lock File (uv.lock)

### Purpose
Reproducible builds: `uv.lock` pins **all** transitive dependencies across all platforms.

### When It's Updated
```bash
# Any of these create/update uv.lock:
uv add some-package                    # Add a dependency
uv remove some-package                 # Remove a dependency
uv sync                                # Sync if lock is stale
uv lock --upgrade                      # Upgrade all transitive deps
```

### Committing Changes
Always commit `uv.lock` to git:
```bash
git add uv.lock
git commit -m "Pin dependency versions"
```

**Why**: Ensures every developer and CI/CD runs the same versions.

---

## Common Workflows

### Adding a New Package

```bash
# 1. Create the package in tools/my_package/pyproject.toml
mkdir -p tools/my_package/my_package
cat > tools/my_package/pyproject.toml << 'EOF'
[project]
name = "my-package"
version = "0.1.0"
dependencies = ["requests>=2.31"]
EOF

# 2. Update workspace root
# In pyproject.toml, add to [tool.uv.workspace].members:
# "tools/my_package"

# 3. Sync to generate uv.lock
uv sync

# 4. Commit
git add -A
git commit -m "Add my-package workspace member"
```

### Upgrading a Shared Dependency

```bash
# 1. Update pyproject.toml
# Change [dependency-groups].llm from:
#   llm = ["any-llm-sdk[anthropic,ollama]>=1.0"]
# To:
#   llm = ["any-llm-sdk[anthropic,ollama]>=1.1"]

# 2. Sync
uv sync --all-groups

# 3. Test
pytest

# 4. Commit
git add uv.lock pyproject.toml
git commit -m "Upgrade any-llm-sdk to >=1.1"
```

### Adding Optional RAG Support

User wants extraction agent with FAISS but not everyone needs it:

```toml
# agents/pyproject.toml
[project.optional-dependencies]
rag = ["faiss-cpu>=1.8", "numpy<2"]

# Then use:
# uv sync --group rag
# to install RAG extras
```

### Setting Up New Developer Machine

```bash
# 1. Clone repo
git clone <repo-url>
cd capstone

# 2. Run setup (reads system-requirements.toml)
python -m tools.setup --all

# 3. Verify
pytest

# Done! All system and Python deps are set up.
```

### Fixing Version Conflicts

Example: `numpy<2` conflicts with something else.

1. **Document in system-requirements.toml**:
   ```toml
   [constraints.numpy]
   version = "<2"
   why = "faiss-cpu has not updated for NumPy 2.0"
   ```

2. **Reference in pyproject.toml**:
   ```toml
   [dependency-groups]
   rag = ["faiss-cpu>=1.8", "numpy<2"]  # See constraints in system-requirements.toml
   ```

3. **Document in PR**: Explain why the constraint exists and when it can be removed.

---

## Troubleshooting

### "Command not found: uv"
```bash
# Install uv (see system-requirements.toml)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (macOS/Linux)
export PATH="$HOME/.cargo/bin:$PATH"
```

### "ModuleNotFoundError: No module named 'faiss'"
```bash
# FAISS is optional - install RAG group
uv sync --group rag
```

### "sqlite3 version too old"
Check the system requirement:
```bash
sqlite3 --version
cat system-requirements.toml | grep -A3 "sqlite3"
```

If yours is < 3.35, upgrade via package manager:
```bash
brew install sqlite3              # macOS
apt-get install sqlite3           # Linux
choco install sqlite              # Windows
```

### "uv.lock is stale"
```bash
# Regenerate lock file
uv lock

# Or use sync (also updates lock)
uv sync --all-groups
```

---

## Best Practices

1. **Always commit uv.lock**: Ensures reproducible builds
2. **Group related deps**: Use `[dependency-groups]` for features (llm, rag, eval)
3. **Update system-requirements.toml**: Keep it as the single source of truth
4. **Use optional-dependencies**: Let users install only what they need
5. **Document constraints**: Explain why `numpy<2` exists (in comments + constraint section)
6. **Pin transitive deps**: `uv.lock` does this automatically
7. **Test after upgrades**: Run full test suite after updating dependencies

---

## References

- **System Requirements**: See `system-requirements.toml`
- **Python Workspace**: See `pyproject.toml` and individual member `pyproject.toml`
- **Setup Automation**: See `tools/setup/main.py`
- **Original Analysis**: See `DEPENDENCY_ANALYSIS.md`
