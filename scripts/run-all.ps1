#Requires -Version 5.1
<#
.SYNOPSIS
    Capstone Project - Start All Services (Windows)

.DESCRIPTION
    Starts the complete Capstone application stack on Windows:
    1. Verifies all required tools (uv, bun, Python, Node)
    2. Checks LLM provider configuration (Ollama or OpenRouter)
    3. Syncs Python and Node dependencies (unless -NoSync)
    4. Starts FastAPI backend (HTTPS on port 8443)
    5. Starts Vite frontend - Contract Portal (HTTPS on port 5173)
    6. Starts Vite frontend - Agent Console (HTTPS on port 5174)
    7. Optionally creates admin account on first run

    PREFLIGHT CHECKS:
    - Verifies uv, bun, Python, mkcert are installed
    - Checks HTTPS certificates exist (.certs/)
    - Checks LLM_PROVIDER setting in .env
    - Verifies Ollama is running (if using local LLM)
    - Verifies OpenRouter API key (if using cloud LLM)

    SERVICES STARTED:
    - Backend API:         https://localhost:8443  (FastAPI + Hypercorn)
    - Contract Portal:     https://localhost:5173  (Vite + React)
    - Agent Console:       https://localhost:5174  (Vite + React, admin only)

    OUTPUT:
    - Logs written to .run/*.log
    - Service status in .run/services.json
    - Stop with: .\scripts\run-all.ps1 -Stop

.PARAMETER NoSync
    Skip uv sync and bun install (assumes dependencies are already installed).

.PARAMETER Bootstrap
    Create the local admin account via /auth/bootstrap on first run.
    Credentials: Email: admin@capstone.local, Password: CapstoneAdmin!2026

.PARAMETER Stop
    Stop all services from a previous run and exit (all other parameters ignored).

.PARAMETER NoApi
    Skip starting the backend API service.

.PARAMETER NoFrontend
    Skip starting the frontend (contract portal) service.

.PARAMETER NoConsole
    Skip starting the admin console service.

.PARAMETER BindHost
    Bind to this host instead of localhost (default: localhost).

.PARAMETER ApiPort, FrontendPort, ConsolePort
    Port numbers for each service (defaults: 8443, 5173, 5174).

.PARAMETER OrgName
    Organization name for bootstrap (default: Capstone).

.PARAMETER AdminEmail, AdminPassword, AdminName
    Admin account credentials for bootstrap (only used with -Bootstrap).

.EXAMPLE
    .\scripts\run-all.ps1
    Sync dependencies and start all services.

.EXAMPLE
    .\scripts\run-all.ps1 -Bootstrap
    Sync dependencies, create admin account, then start (use on first run).

.EXAMPLE
    .\scripts\run-all.ps1 -NoSync
    Start without syncing dependencies (assumes they are already installed).

.EXAMPLE
    .\scripts\run-all.ps1 -NoFrontend
    Start API and Console, skip Contract Portal.

.EXAMPLE
    .\scripts\run-all.ps1 -Stop
    Stop all services from a previous run.

.NOTES
    LLM CONFIGURATION (from .env):
    - LLM_PROVIDER=ollama (default): requires Ollama running on http://127.0.0.1:11434
    - LLM_PROVIDER=openrouter: requires OPENROUTER_API_KEY in .env
    Script will STOP if LLM is not properly configured or not running.

    MCP SERVERS:
    Spawned by agents as needed (not started by this script).
#>
[CmdletBinding()]
param(
    [switch]$NoSync,        # skip uv sync --all-packages + bun install
    [switch]$Bootstrap,     # create the local admin account via /auth/bootstrap
    [switch]$Stop,          # stop apps from a previous run and exit
    [switch]$NoApi,         # skip the backend
    [switch]$NoFrontend,    # skip the contract portal
    [switch]$NoConsole,     # skip the agent observability console
    [string]$BindHost = "localhost",
    [int]$ApiPort = 8443,
    [int]$FrontendPort = 5173,
    [int]$ConsolePort = 5174,
    [string]$OrgName = "Capstone",
    [string]$AdminEmail = "admin@capstone.local",
    [string]$AdminPassword = "CapstoneAdmin!2026",
    [string]$AdminName = "Capstone Admin"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RunDir = Join-Path $Root ".run"
$StateFile = Join-Path $RunDir "services.json"
$FrontendDir = Join-Path $Root "web\frontend"
$ConsoleDir = Join-Path $Root "web\admin"
$ApiBase = "https://${BindHost}:${ApiPort}"

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn2($msg){ Write-Host "    $msg" -ForegroundColor Yellow }

# --- shell + tool resolution -------------------------------------------------

$PwshExe = (Get-Command pwsh -ErrorAction SilentlyContinue)
if ($PwshExe) { $PwshExe = $PwshExe.Source } else { $PwshExe = (Get-Command powershell).Source }

function Resolve-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return @{ Exe = $cmd.Source; Pre = @() } }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py -and (& $py.Source -m uv --version 2>$null)) { return @{ Exe = $py.Source; Pre = @("-m", "uv") } }
    throw "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
}

function Resolve-Bun {
    $cmd = Get-Command bun -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $fallback = Join-Path $env:USERPROFILE ".bun\bin\bun.exe"
    if (Test-Path $fallback) { return $fallback }
    throw "bun not found. Install it: https://bun.sh"
}

# --- lifecycle -------------------------------------------------------------

function Stop-Services {
    if (-not (Test-Path $StateFile)) { Write-Warn2 "No running apps recorded."; return }
    $state = Get-Content $StateFile -Raw | ConvertFrom-Json
    foreach ($svc in $state.services) {
        if ($svc.pid -and (Get-Process -Id $svc.pid -ErrorAction SilentlyContinue)) {
            Write-Step "Stopping $($svc.name) (pid $($svc.pid)) and children"
            & taskkill.exe /PID $svc.pid /T /F 2>&1 | Out-Null
        }
        # bun/vite reparents node, so a tree kill on the launcher window can
        # miss the real listener - clean up by port as a backstop.
        if ($svc.port) { Stop-PortOwner -Port $svc.port }
    }
    Remove-Item $StateFile -Force
    Write-Ok "Stopped."
}

function Stop-PortOwner([int]$Port) {
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($pidNum in ($conns.OwningProcess | Select-Object -Unique)) {
        $cim = Get-CimInstance Win32_Process -Filter "ProcessId=$pidNum" -ErrorAction SilentlyContinue
        if ($cim -and ($cim.CommandLine -match [regex]::Escape($Root) -or $cim.CommandLine -match "clm_web\.server|vite|hypercorn")) {
            & taskkill.exe /PID $pidNum /T /F 2>&1 | Out-Null
        }
    }
}

function Wait-Port([string]$h, [int]$p, [int]$timeoutSec = 90) {
    # Prefer the OS listener table (address-family agnostic, no connect race);
    # fall back to a socket probe where Get-NetTCPConnection is unavailable.
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        if (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue) { return $true }
        foreach ($t in @("127.0.0.1", "::1")) {
            try {
                $c = New-Object System.Net.Sockets.TcpClient
                $iar = $c.BeginConnect($t, $p, $null, $null)
                if ($iar.AsyncWaitHandle.WaitOne(300) -and $c.Connected) { $c.EndConnect($iar); $c.Close(); return $true }
                $c.Close()
            } catch {}
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Start-App([string]$name, [string]$title, [string]$workDir, [string]$command, [int]$port = 0) {
    $inner = "`$host.UI.RawUI.WindowTitle = '$title'; Set-Location '$workDir'; $command"
    $proc = Start-Process -FilePath $PwshExe -PassThru -WorkingDirectory $workDir `
        -ArgumentList @("-NoExit", "-Command", $inner)
    return [pscustomobject]@{ name = $name; pid = $proc.Id; title = $title; port = $port }
}

# --- -Stop short-circuit ---------------------------------------------------

if ($Stop) { Stop-Services; return }

# --- preflight -----------------------------------------------------------------

Write-Step "Preflight"
if (-not (Test-Path (Join-Path $Root "pyproject.toml"))) { throw "Run from the repo (expected $Root/pyproject.toml)." }
if (Test-Path $StateFile) {
    Write-Warn2 "Apps already running per $StateFile. Stopping them first."
    Stop-Services
}
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$uv = Resolve-Uv
Write-Ok "uv: $($uv.Exe) $($uv.Pre -join ' ')"

if (-not $NoApi) {
    $cert = Join-Path $Root ".certs\localhost.pem"
    $key  = Join-Path $Root ".certs\localhost-key.pem"
    if (-not (Test-Path $cert) -or -not (Test-Path $key)) {
        throw "Missing .certs\localhost.pem / localhost-key.pem. Generate with mkcert (see web/README.md)."
    }
    Write-Ok "TLS cert: $cert"
}
if (-not $NoFrontend) {
    $bun = Resolve-Bun
    Write-Ok "bun: $bun"
}

# --- LLM provider check -------------------------------------------------------

$envFile = Join-Path $Root ".env"
$llmProvider = "ollama"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    if ($envContent -match '^\s*LLM_PROVIDER\s*=\s*(\S+)') {
        $llmProvider = $matches[1].Trim()
    }
}

if ($llmProvider -eq "ollama") {
    Write-Step "Checking Ollama service (LLM_PROVIDER=ollama)..."
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -ErrorAction Stop -TimeoutSec 2
        Write-Ok "Ollama is running"
    } catch {
        Write-Host "Ollama is not running on http://127.0.0.1:11434" -ForegroundColor Red
        Write-Host ""
        Write-Host "Options:"
        Write-Host "  1. Start Ollama: ollama serve"
        Write-Host "  2. Switch to OpenRouter API: edit .env and set LLM_PROVIDER=openrouter"
        Write-Host ""
        exit 1
    }
} elseif ($llmProvider -eq "openrouter") {
    Write-Step "Checking OpenRouter configuration..."
    if (Test-Path $envFile) {
        $envContent = Get-Content $envFile -Raw
        if ($envContent -match '^\s*OPENROUTER_API_KEY\s*=\s*(\S+)') {
            Write-Ok "OpenRouter API key configured"
        } else {
            throw "OpenRouter API key not found in .env"
        }
    } else {
        throw "OpenRouter API key not configured in .env"
    }
}

# --- optional sync -----------------------------------------------------------

if (-not $NoSync) {
    Write-Step "uv sync --all-packages"
    & $uv.Exe @($uv.Pre) sync --all-packages
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed." }
    foreach ($dir in @(
        @{ skip = $NoFrontend; path = $FrontendDir; name = "web/frontend" },
        @{ skip = $NoConsole; path = $ConsoleDir; name = "web/admin" }
    )) {
        if ($dir.skip) { continue }
        Write-Step "bun install ($($dir.name))"
        Push-Location $dir.path
        try { & $bun install } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { throw "bun install failed in $($dir.name)." }
    }
}

# --- start the apps --------------------------------------------------------

$services = @()

if (-not $NoApi) {
    Write-Step "Starting API -> $ApiBase"
    $bind = "127.0.0.1:${ApiPort},[::1]:${ApiPort}"
    $uvInvoke = ("& '{0}' {1} run python -m clm_web.server" -f $uv.Exe, (($uv.Pre | ForEach-Object { "'$_'" }) -join ' ')).Trim()
    $apiCmd = @(
        "`$env:CLM_BIND = '$bind'"
        "`$env:CLM_CERTFILE = '$(Join-Path $Root ".certs\localhost.pem")'"
        "`$env:CLM_KEYFILE = '$(Join-Path $Root ".certs\localhost-key.pem")'"
        $uvInvoke
    ) -join '; '
    $services += Start-App -name "api" -title "CLM API :$ApiPort" -workDir $Root -command $apiCmd -port $ApiPort

    if (-not (Wait-Port $BindHost $ApiPort)) { Stop-Services; throw "API did not open port $ApiPort. Check its window." }
    Write-Ok "API port $ApiPort is up."
}

if ($Bootstrap -and -not $NoApi) {
    Write-Step "Bootstrapping admin account"
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
    [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
    $body = @{
        organization_name = $OrgName; email = $AdminEmail
        password = $AdminPassword; display_name = $AdminName
    } | ConvertTo-Json
    try {
        Invoke-RestMethod -Uri "$ApiBase/auth/bootstrap" -Method Post -Body $body -ContentType "application/json" | Out-Null
        Write-Ok "Created $AdminEmail (org '$OrgName')."
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
        if ($code -eq 409) { Write-Warn2 "Bootstrap already complete - leaving the existing users alone." }
        else { throw }
    }
}

$feScheme = if (Test-Path (Join-Path $Root ".certs\localhost.pem")) { "https" } else { "http" }

if (-not $NoFrontend) {
    Write-Step "Starting contract portal -> ${feScheme}://${BindHost}:${FrontendPort}"
    $services += Start-App -name "frontend" -title "CLM Portal :$FrontendPort" -workDir $FrontendDir -command "& '$bun' run dev" -port $FrontendPort
    # First run after a dep change pre-bundles; give Vite generous headroom.
    if (-not (Wait-Port $BindHost $FrontendPort 180)) { Write-Warn2 "Portal port $FrontendPort not up yet - it may still be starting; check its window." }
    else { Write-Ok "Portal port $FrontendPort is up." }
}

if (-not $NoConsole) {
    Write-Step "Starting agent console -> ${feScheme}://${BindHost}:${ConsolePort}"
    $services += Start-App -name "console" -title "Agent Console :$ConsolePort" -workDir $ConsoleDir -command "& '$bun' run dev" -port $ConsolePort
    if (-not (Wait-Port $BindHost $ConsolePort 180)) { Write-Warn2 "Console port $ConsolePort not up yet - it may still be starting; check its window." }
    else { Write-Ok "Console port $ConsolePort is up." }
}

# --- record + report -----------------------------------------------------------

@{ started = (Get-Date).ToString("o"); services = $services } | ConvertTo-Json -Depth 4 | Set-Content -Path $StateFile -Encoding utf8

Write-Host ""
Write-Host "  Capstone is running" -ForegroundColor Green
Write-Host "  -------------------"
if (-not $NoFrontend) { Write-Host "  Portal    ${feScheme}://${BindHost}:${FrontendPort}   (contract workspace)" }
if (-not $NoConsole)  { Write-Host "  Console   ${feScheme}://${BindHost}:${ConsolePort}   (agent observability, admin only)" }
if (-not $NoApi)      { Write-Host "  API       $ApiBase        (health: $ApiBase/health)" }
if (-not $NoApi)      { Write-Host "  Login     $AdminEmail  /  $AdminPassword" }
Write-Host ""
Write-Host "  Each app runs in its own window. Stop everything with:" -ForegroundColor DarkGray
Write-Host "      .\scripts\run-all.ps1 -Stop" -ForegroundColor DarkGray
$envFile = Join-Path $Root ".env"
if (Test-Path $envFile) {
    $llm = (Select-String -Path $envFile -Pattern '^(LLM_PROVIDER|LLM_MODEL|OLLAMA_HOST|EMBEDDING_URL|EMBEDDING_MODEL)=' -ErrorAction SilentlyContinue | ForEach-Object { $_.Line }) -join "  "
    Write-Host ""
    Write-Host "  LLM config (.env): $llm" -ForegroundColor DarkGray
} else {
    Write-Host ""
    Write-Host "  Note: no .env found - copy .env.example to .env and set LLM_PROVIDER/LLM_MODEL." -ForegroundColor DarkGray
    Write-Host "  Local/LAN Ollama is slow (minutes per run); LLM_PROVIDER=anthropic + ANTHROPIC_API_KEY is fast." -ForegroundColor DarkGray
}
Write-Host ""
