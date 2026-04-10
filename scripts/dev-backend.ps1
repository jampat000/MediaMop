# Run the API from repo root (or any cwd). Sets PYTHONPATH for apps/backend/src.
# Default bind is scripts/dev-ports.json (development.apiHost / development.apiPort).
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot "apps\backend"
$portsPath = Join-Path $PSScriptRoot "dev-ports.json"

if (-not (Test-Path $backend)) {
    Write-Error "Expected apps/backend under $repoRoot"
}
if (-not (Test-Path $portsPath)) {
    Write-Error "Missing scripts/dev-ports.json (repo dev port registry)."
}

$sec = if ($env:MEDIAMOP_SESSION_SECRET) { $env:MEDIAMOP_SESSION_SECRET.Trim() } else { "" }
if (-not $sec) {
    Write-Warning "MEDIAMOP_SESSION_SECRET is empty; set a long random value before using login/bootstrap."
}
Write-Host "SQLite: data under MEDIAMOP_HOME (see apps/backend/.env.example). Run .\scripts\dev-migrate.ps1 once before first API use." -ForegroundColor DarkGray
Write-Host ""

$ports = Get-Content $portsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$apiHost = $ports.development.apiHost
$apiPort = [int]$ports.development.apiPort
if ($env:MEDIAMOP_DEV_API_PORT -and $env:MEDIAMOP_DEV_API_PORT.Trim()) {
    $apiPort = [int]$env:MEDIAMOP_DEV_API_PORT.Trim()
}

$env:PYTHONPATH = "src"
Set-Location $backend

$venvPython = Join-Path $backend '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    $pyExe = $venvPython
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $py) {
        Write-Error 'Python not on PATH. From apps/backend run: py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -e .'
    }
    $pyExe = $py.Source
}

& $pyExe -m uvicorn mediamop.api.main:app --host $apiHost --port $apiPort --reload
