# applycling MCP Setup for Windows
# Run this in PowerShell (right-click → Run with PowerShell, or paste into a terminal):
#
#   irm https://raw.githubusercontent.com/aommi/applycling/main/scripts/setup_mcp.ps1 | iex
#
# What this does:
#   1. Installs Python 3.12 (if missing)
#   2. Installs Git (if missing)
#   3. Clones applycling
#   4. Creates venv + installs applycling with MCP deps
#   5. Writes Claude Desktop config
#   6. Runs applycling setup (profile, resume, LLM config)

$ErrorActionPreference = "Stop"

Write-Host "→ Finding Python 3.12..." -ForegroundColor Green

$python = $null
if (Get-Command python3.12 -ErrorAction SilentlyContinue) {
    $python = (Get-Command python3.12).Source
}
if (-not $python) {
    Write-Host "→ Installing Python 3.12 via winget..." -ForegroundColor Green
    winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    $python = (Get-Command python3.12 -ErrorAction Stop).Source
}
Write-Host "Python: $python" -ForegroundColor Green

# ── Git ──────────────────────────────────────────────────────────────
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "→ Installing Git via winget..." -ForegroundColor Green
    winget install Git.Git --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# ── Clone repo ───────────────────────────────────────────────────────
$repoDir = "$env:USERPROFILE\applycling"
if (Test-Path "$repoDir\.git") {
    Write-Host "→ Updating existing repo..." -ForegroundColor Green
    Set-Location $repoDir
    git pull
} else {
    Write-Host "→ Cloning applycling..." -ForegroundColor Green
    git clone https://github.com/aommi/applycling.git $repoDir
}
Set-Location $repoDir

# ── Create venv + install ────────────────────────────────────────────
Write-Host "→ Installing applycling + MCP dependencies..." -ForegroundColor Green
& $python -m venv .venv
$venvPython = ".venv\Scripts\python.exe"
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -e ".[mcp]"

Write-Host "Installation complete." -ForegroundColor Green

# ── Write Claude Desktop config ──────────────────────────────────────
$claudeConfig = "$env:APPDATA\Claude\claude_desktop_config.json"
$configDir = Split-Path $claudeConfig -Parent
if (-not (Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

$config = @{}
if (Test-Path $claudeConfig) {
    try {
        $config = Get-Content $claudeConfig -Raw | ConvertFrom-Json -AsHashtable
    } catch {
        $config = @{}
    }
}

if (-not $config.ContainsKey("mcpServers")) {
    $config["mcpServers"] = @{}
}

$config["mcpServers"]["applycling"] = @{
    command = (Resolve-Path $venvPython).Path
    args = @("-m", "applycling.cli", "mcp", "serve")
    env = @{ PYTHONPATH = $repoDir }
    cwd = $repoDir
}

$config | ConvertTo-Json -Depth 4 | Set-Content $claudeConfig

Write-Host "Claude Desktop config written." -ForegroundColor Green

# ── First-time setup ─────────────────────────────────────────────────
Write-Host ""
Write-Host "→ Setting up your profile..." -ForegroundColor Green
Write-Host "  You will be asked for your name, resume, and LLM provider." -ForegroundColor Yellow
Write-Host ""
& $venvPython -m applycling.cli setup

# ── Done ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
Write-Host "✓ applycling MCP is ready!" -ForegroundColor Green
Write-Host ""
Write-Host "  Next steps:"
Write-Host "  1. Restart Claude Desktop"
Write-Host "  2. Look for the hammer icon — applycling tools are ready"
Write-Host "  3. Try: 'Show my recent tracked job applications'"
Write-Host "  4. Try: 'Generate an application for https://...'"
Write-Host ""
Write-Host "  If add_job times out, run it via CLI first:"
Write-Host "    cd $repoDir"
Write-Host "    .venv\Scripts\python.exe -m applycling.cli add --url <url>"
Write-Host "    then inspect via MCP: 'Show the package for job_001'"
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Green
