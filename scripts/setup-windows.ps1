#Requires -Version 5.1
<#
.SYNOPSIS
    Capstone Project Setup Script for Windows

.DESCRIPTION
    Prepares the complete Capstone development environment by:
    1. Verifying Python 3.11+ and installing uv (fast package manager)
    2. Creating Python virtual environment and syncing dependencies
    3. Installing mkcert and generating HTTPS certificates for local development
    4. Initializing SQLite database with schema
    5. Creating .env configuration file with default LLM settings
    6. Setting up Ollama (local LLM) with required models
    7. Downloading sample contracts from CUAD dataset
    8. Building RAG knowledge index for extraction agent
    9. Installing Node.js dependencies for frontend and admin console (bun/npm)

    CREATES:
    - .venv/              Python virtual environment
    - .certs/             HTTPS certificates for local development
    - .env                Configuration file with LLM and database settings
    - capstone.db         SQLite database
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

# === 1. Verify Python installation ===
Write-Step "Checking Python installation..."
if (Test-Command python) {
    $pythonVersion = python --version 2>&1
    Write-Ok "$pythonVersion"
} else {
    Write-Error2 "Python not found. Install Python 3.12+ from https://www.python.org/downloads/"
    Write-Host "   Or use Chocolatey: choco install python"
    exit 1
}

# === 2. Verify or install uv ===
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

# === 3. Create Python virtual environment ===
Write-Step "Setting up Python virtual environment..."
cd $Root

if (Test-Path $VenvPath) {
    Write-Ok "Virtual environment already exists"
} else {
    Write-Step "Creating virtual environment..."
    uv venv
    Write-Ok "Virtual environment created"
}

# === 4. Install Python dependencies ===
Write-Step "Installing Python dependencies..."
uv sync --all-packages
Write-Ok "Python dependencies installed"

# === 5. Check for mkcert ===
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

# === 6. Generate HTTPS certificates ===
if (Test-Path (Join-Path $CertsPath "localhost.pem")) {
    Write-Ok "HTTPS certificates already exist"
} else {
    Write-Step "Generating local HTTPS certificates..."
    New-Item -ItemType Directory -Path $CertsPath -Force | Out-Null
    mkcert -cert-file (Join-Path $CertsPath "localhost.pem") -key-file (Join-Path $CertsPath "localhost-key.pem") localhost 127.0.0.1 ::1
    Write-Ok "HTTPS certificates generated"
}

# === 7. Initialize SQLite database ===
Write-Step "Initializing SQLite database..."
$DbFile = Join-Path $Root "capstone.db"

if (Test-Path $DbFile) {
    Write-Ok "SQLite database already exists"
} else {
    Write-Step "Creating database..."
    .\.venv\Scripts\Activate.ps1
    python -m web.clm_web.db --init
    deactivate
    Write-Ok "SQLite database initialized"
}

# === 8. Create .env file ===
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Write-Ok ".env already exists"
} else {
    Write-Step "Creating .env configuration file..."
    $EnvContent = @(
        "# LLM Provider Configuration",
        "# Options: anthropic, ollama, openrouter",
        "LLM_PROVIDER=ollama",
        "LLM_MODEL=gemma4:latest",
        "",
        "# Ollama Configuration (for local LLM)",
        "OLLAMA_HOST=http://127.0.0.1:11434",
        "",
        "# Embedding Configuration",
        "EMBEDDING_MODEL=nomic-embed-text:latest",
        "EMBEDDING_URL=http://127.0.0.1:11434/api/embed",
        "",
        "# Extraction Agent Configuration",
        "EXTRACTION_RAG_ENABLED=1",
        "EXTRACTION_RAG_DB=synthetic_data_loader/rag_knowledge.sqlite3",
        "EXTRACTION_RAG_VECTOR_BACKEND=sqlite",
        "",
        "# Query Agent Configuration",
        "QUERY_PLAN_TOOLS=1",
        "QUERY_INTERPRET=1",
        "QUERY_VERIFY=1",
        "",
        "# Platform Testing",
        "PLATFORM_TESTING_EVALUATE=0",
        "",
        "# Timeouts (seconds)",
        "LLM_TIMEOUT_SECONDS=300",
        "QUERY_FAST_TIMEOUT_SECONDS=120",
        "",
        "# Maximum steps",
        "PLANNER_MAX_STEPS=3",
        "",
        "# Database",
        "DATABASE_URL=sqlite:///./capstone.db"
    ) -join "`n"
    $EnvContent | Out-File -FilePath $EnvFile -Encoding UTF8
    Write-Ok ".env created with default values"
}

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
$RagDbFile = Join-Path $Root "synthetic_data_loader" "rag_knowledge.sqlite3"

if (-not (Test-Path $RagDbFile)) {
    Write-Step "Building RAG index (first run, may take a minute)..."
    .\.venv\Scripts\Activate.ps1
    python -m extraction_agent.build_rag_index
    deactivate
    Write-Ok "RAG index built"
} else {
    Write-Ok "RAG index already exists"
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
Write-Host "   .\scripts\run-all.ps1 -Sync -Bootstrap"
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
