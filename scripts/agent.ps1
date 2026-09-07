#Requires -Version 5.1
<#
.SYNOPSIS
    Run the orchestrator CLI (clm-agent) against the local API, logging in first
    so you don't have to paste a bearer token.

.EXAMPLE
    .\scripts\agent.ps1 ask "Which contracts expire this quarter?"
    .\scripts\agent.ps1 task "extract this and compare to our vendor contracts" --file .\vendor.pdf
    .\scripts\agent.ps1 chat
    .\scripts\agent.ps1 -Email me@org.test -Password 'secret' ask "..."

.NOTES
    Needs the API running (scripts\run-all.ps1). clm-agent is a client, not a
    daemon - it is installed by `uv sync --all-packages`.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Command,
    [string]$ApiUrl = "https://localhost:8443",
    [string]$Email = "admin@capstone.local",
    [string]$Password = "CapstoneAdmin!2026"
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $Command) {
    Write-Host "Usage: .\scripts\agent.ps1 <ask|extract|task|watch|chat> [args...]" -ForegroundColor Yellow
    return
}

# --- log in ---------------------------------------------------------------

[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

try {
    $resp = Invoke-RestMethod -Uri "$ApiUrl/auth/token" -Method Post `
        -ContentType "application/x-www-form-urlencoded" `
        -Body @{ grant_type = "password"; username = $Email; password = $Password }
} catch {
    throw "Login to $ApiUrl failed for $Email. Is the API running (scripts\run-all.ps1)? $($_.Exception.Message)"
}

$env:CLM_AGENT_TOKEN = $resp.access_token
$env:CLM_API_URL = $ApiUrl

# --- resolve uv and dispatch --------------------------------------------------
# clm-agent streams progress to stderr by design; keep that from becoming a
# terminating error under Windows PowerShell, and pass its exit code through.

$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
$ErrorActionPreference = "Continue"
Push-Location $Root
try {
    if ($uvCmd) { & uv run clm-agent @Command }
    else { & python -m uv run clm-agent @Command }
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
