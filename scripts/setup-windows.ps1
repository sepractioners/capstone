#Requires -Version 5.1
<#
.SYNOPSIS
    Capstone Project Setup Script for Windows

.DESCRIPTION
    Prepares the complete Capstone development environment by:
    1. Creating .env from .env.example (if missing) and telling you it did
    2. Verifying Python 3.11+ and installing uv (fast package manager)
    3. Creating Python virtual environment and syncing dependencies
    4. Installing mkcert and generating HTTPS certificates for local development
    5. Initializing and seeding the SQLite database (web + domain schema)
    6. Setting up Ollama (local LLM) with required models
    7. Downloading sample contracts from CUAD dataset
    8. Building RAG knowledge index for extraction agent
    9. Installing Node.js dependencies for frontend and admin console (bun/npm)

    CREATES:
    - .venv/              Python virtual environment
    - .certs/             HTTPS certificates for local development
    - .env                Configuration file (copied from .env.example)
    - clm.sqlite3         SQLite database (web + domain schema, seeded tenant/admin)
    - synthetic_data_loader/rag_knowledge.sqlite3  RAG vector index
    - web/*/node_modules  Node.js dependencies

.PARAMETER NoOllama
    Skip Ollama installation check (use if you have cloud LLM like OpenRouter)

.PARAMETER NoSampleData
    Skip downloading sample contracts from CUAD dataset

.PARAMETER NoFrontend
    Skip frontend dependency installation

.EXAMPLE
    .\scripts\setup-windows.ps1
    Run full setup with all features

.EXAMPLE
    .\scripts\setup-windows.ps1 -NoOllama
    Skip Ollama setup (for cloud LLM providers)

.EXAMPLE
    .\scripts\setup-windows.ps1 -NoOllama -NoSampleData
    Minimal setup: only dependencies, no LLM or sample data

.NOTES
    Requires: PowerShell 5.1+, Administrator access (for package managers)

    PREREQUISITES:
    - Python 3.11 or higher
    - Internet connection (to download dependencies and sample data)

    NEXT STEP AFTER SETUP:
    Run: .\scripts\run-all.ps1
#>

[CmdletBinding()]
param(
    [switch]$NoOllama,           # Skip Ollama setup
    [switch]$NoSampleData,       # Skip sample contract download
    [switch]$NoFrontend          # Skip frontend dependency installation
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPath = Join-Path $Root ".venv"
$CertsPath = Join-Path $Root ".certs"

# Color output helpers
function Write-Step   { param([string]$msg); Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok     { param([string]$msg); Write-Host "    [OK] $msg" -ForegroundColor Green }
function Write-Warn   { param([string]$msg); Write-Host "    [WARN] $msg" -ForegroundColor Yellow }
function Write-Error2 { param([string]$msg); Write-Host "    [ERROR] $msg" -ForegroundColor Red }

# Check if command exists
function Test-Command {
    param([string]$cmd)
    $null = Get-Command $cmd -ErrorAction SilentlyContinue
    return $?
}

Write-Step "Capstone Project Setup for Windows"
Write-Host ""

# === 1. Create .env configuration file ===
# Done first so the developer can review/edit it before the rest of setup
# runs, and so CLM_DATABASE_PATH / EXTRACTION_RAG_DB resolve to the same
# values the app uses at runtime.
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Write-Ok ".env already exists - leaving it untouched"
} else {
    Copy-Item (Join-Path $Root ".env.example") $EnvFile
    Write-Host ""
    Write-Host "  ----------------------------------------------------------------" -ForegroundColor Yellow
    Write-Host "  Created .env from .env.example" -ForegroundColor Yellow
    Write-Host "  Defaults: local Ollama (LLM_PROVIDER=ollama, model gemma4:latest)." -ForegroundColor Yellow
    Write-Host "  Edit .env now if you want Anthropic/OpenRouter or a different model" -ForegroundColor Yellow
    Write-Host "  or database path - then re-run this script." -ForegroundColor Yellow
    Write-Host "  ----------------------------------------------------------------" -ForegroundColor Yellow
    Write-Host ""
}

# === 2. Verify Python installation ===
Write-Step "Checking Python installation..."
if (Test-Command python) {
    $pythonVersion = python --version 2>&1
    Write-Ok "$pythonVersion"
} else {
    Write-Error2 "Python not found. Install Python 3.12+ from https://www.python.org/downloads/"
    Write-Host "   Or use Chocolatey: choco install python"
    exit 1
}

# === 3. Verify or install uv ===
Write-Step "Checking uv (Python package manager)..."
if (Test-Command uv) {
    $uvVersion = uv --version
    Write-Ok "$uvVersion"
} else {
    Write-Step "Installing uv..."
    $ProgressPreference = 'SilentlyContinue'
    $null = Invoke-WebRequest https://astral.sh/uv/install.ps1 -UseBasicParsing | Invoke-Expression
    Write-Ok "uv installed"
    Write-Warn "Please restart PowerShell and run this script again"
    exit 1
}

# === 4. Create Python virtual environment ===
Write-Step "Setting up Python virtual environment..."
cd $Root

if (Test-Path $VenvPath) {
    Write-Ok "Virtual environment already exists"
} else {
    Write-Step "Creating virtual environment..."
    uv venv
    Write-Ok "Virtual environment created"
}

# === 5. Install Python dependencies ===
Write-Step "Installing Python dependencies..."
uv sync --all-packages
Write-Ok "Python dependencies installed"

# === 6. Check for mkcert ===
Write-Step "Checking mkcert (HTTPS certificate tool)..."
if (Test-Command mkcert) {
    Write-Ok "mkcert installed"
} else {
    Write-Error2 "mkcert not found"
    Write-Host ""
    Write-Host "Install mkcert using one of these methods:"
    Write-Host "  1. Chocolatey:  choco install mkcert"
    Write-Host "  2. Download:    https://github.com/FiloSottile/mkcert/releases"
    Write-Host "  3. Scoop:       scoop install mkcert"
    Write-Host ""
    Write-Warn "Please install mkcert, then run this script again"
    exit 1
}

# === 7. Generate HTTPS certificates ===
if (Test-Path (Join-Path $CertsPath "localhost.pem")) {
    Write-Ok "HTTPS certificates already exist"
} else {
    Write-Step "Generating local HTTPS certificates..."
    New-Item -ItemType Directory -Path $CertsPath -Force | Out-Null
    mkcert -cert-file (Join-Path $CertsPath "localhost.pem") -key-file (Join-Path $CertsPath "localhost-key.pem") localhost 127.0.0.1 ::1
    Write-Ok "HTTPS certificates generated"
}

# === 8. Initialize and seed the SQLite database ===
Write-Step "Initializing SQLite database..."
# Read CLM_DATABASE_PATH from .env or use default
$DbPath = "./clm.sqlite3"
$EnvDbLine = Get-Content $EnvFile | Select-String "^CLM_DATABASE_PATH="
if ($EnvDbLine) {
    $DbPath = $EnvDbLine.Line.Split("=", 2)[1].Trim()
}
$DbFile = Join-Path $Root $DbPath

# Schema creation and seeding are both idempotent (CREATE TABLE IF NOT EXISTS /
# seed script self-skips when a tenant already exists). Run them every time:
# the database file is often created as a side effect of importing the app
# before the tenant/admin user has ever been seeded, so gating on the file's
# existence would silently leave the platform unusable (no org, no login).
.\.venv\Scripts\Activate.ps1
$env:CLM_DATABASE_PATH = $DbPath
Write-Step "Creating database schema at $DbFile..."
python -m clm_web.db --init
if ($LASTEXITCODE -ne 0) { deactivate; Write-Error2 "Database initialization failed"; exit 1 }

Write-Step "Seeding database with default tenant and admin user..."
uv run python seed_database.py --skip-cuad --skip-faiss
if ($LASTEXITCODE -ne 0) { deactivate; Write-Error2 "Database seeding failed"; exit 1 }
deactivate
Write-Ok "SQLite database ready at $DbFile"

# === 9. Set up Ollama (optional) ===
if (-not $NoOllama) {
    Write-Step "Checking Ollama installation..."

    if (Test-Command ollama) {
        Write-Ok "Ollama installed"

        # Check if service is running
        try {
            $null = Invoke-WebRequest http://127.0.0.1:11434/api/tags -UseBasicParsing
            Write-Ok "Ollama service is running"

            # Pull required models
            Write-Step "Ensuring Ollama models are available..."
            $models = ollama list

            if (-not ($models -match "gemma4")) {
                Write-Step "Pulling gemma4:latest model (may take a few minutes)..."
                ollama pull gemma4:latest
                Write-Ok "gemma4:latest model ready"
            } else {
                Write-Ok "gemma4:latest already available"
            }

            if (-not ($models -match "nomic-embed-text")) {
                Write-Step "Pulling nomic-embed-text:latest model..."
                ollama pull nomic-embed-text:latest
                Write-Ok "nomic-embed-text:latest model ready"
            } else {
                Write-Ok "nomic-embed-text:latest already available"
            }
        } catch {
            Write-Warn "Ollama is installed but not running. Start it with: ollama serve"
        }
    } else {
        Write-Warn "Ollama not found - skip with -NoOllama if using cloud LLM"
        Write-Host "   Download from: https://ollama.ai/download"
    }
}

# === 10. Download sample contracts (optional) ===
if (-not $NoSampleData) {
    Write-Step "Setting up sample contracts..."

    $SampleDir = Join-Path $Root "synthetic_data_loader" "data"
    $ManifestFile = Join-Path $SampleDir "cuad_subset_manifest.txt"

    if (-not (Test-Path $ManifestFile)) {
        Write-Step "Downloading CUAD contract samples (may take a few minutes)..."
        New-Item -ItemType Directory -Path $SampleDir -Force | Out-Null

        .\.venv\Scripts\Activate.ps1
        python -m synthetic_data_loader.download_cuad_subset
        deactivate

        Write-Ok "Sample contracts downloaded"
    } else {
        Write-Ok "Sample contracts already downloaded"
    }
}

# === 11. Build RAG index ===
Write-Step "Building RAG knowledge index..."
# Read EXTRACTION_RAG_DB from .env or use default
$RagPath = "synthetic_data_loader/rag_knowledge.sqlite3"
$EnvRagLine = Get-Content $EnvFile | Select-String "^EXTRACTION_RAG_DB="
if ($EnvRagLine) {
    $RagPath = $EnvRagLine.Line.Split("=", 2)[1].Trim()
}
$RagDbFile = Join-Path $Root $RagPath

if (-not (Test-Path $RagDbFile)) {
    Write-Step "Building RAG index at $RagDbFile (first run, may take a minute)..."
    .\.venv\Scripts\Activate.ps1
    $env:EXTRACTION_RAG_DB = $RagPath
    python -m extraction_agent.build_rag_index
    if ($LASTEXITCODE -ne 0) { deactivate; Write-Error2 "RAG index build failed"; exit 1 }
    deactivate
    Write-Ok "RAG index built"
} else {
    Write-Ok "RAG index already exists at $RagDbFile"
}

# === 12. Install frontend and admin console dependencies ===
foreach ($dir in @("web\frontend", "web\admin")) {
    $dirPath = Join-Path $Root $dir
    if (Test-Command bun) {
        Write-Step "Installing dependencies in $dir with bun..."
        cd $dirPath
        bun install
        cd $Root
        Write-Ok "Dependencies installed in $dir"
    } else {
        Write-Warn "bun not found - using npm instead"
        if (Test-Command npm) {
            Write-Step "Installing dependencies in $dir with npm..."
            cd $dirPath
            npm install
            cd $Root
            Write-Ok "Dependencies installed in $dir"
        } else {
            Write-Warn "Neither bun nor npm found - dependencies setup skipped"
            Write-Warn "Install with: npm install -g bun"
            break
        }
    }
}

# === Summary ===
Write-Host ""
Write-Ok "Setup complete!"
Write-Host ""
Write-Step "Next steps:"
Write-Host ""
Write-Host "1. Start Ollama (if using local LLM):"
Write-Host "   ollama serve"
Write-Host ""
Write-Host "2. Start the applications:"
Write-Host "   .\scripts\run-all.ps1 -Bootstrap"
Write-Host ""
Write-Host "3. Access the portal:"
Write-Host "   Contract Portal:    https://localhost:5173"
Write-Host "   Agent Console:      https://localhost:5174"
Write-Host "   API:                https://localhost:8443"
Write-Host ""
Write-Host "4. Login with:"
Write-Host "   Email:    admin@capstone.local"
Write-Host "   Password: CapstoneAdmin!2026"
Write-Host ""
Write-Host "5. Test extraction:"
Write-Host "   .\scripts\agent.ps1 ask ""Which contracts expire this quarter?"""
Write-Host ""
