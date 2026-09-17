# Run the .NET server from the repository (any cwd) for local development.
# Loads the repository-root .env (shell variables win), binds to scripts/dev-ports.json
# (development.apiHost / development.apiPort), and serves the built web app when apps/web/dist exists.
# The server creates or migrates its SQLite database under WEIR_HOME on start; there is no separate
# migration step.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\weir-env.ps1"
$repoRoot = Split-Path -Parent $PSScriptRoot
$serverProject = Join-Path $repoRoot "apps\server\src\Weir.Host"
$portsPath = Join-Path $PSScriptRoot "dev-ports.json"

if (-not (Test-Path $serverProject)) {
    Write-Error "Expected apps/server/src/Weir.Host under $repoRoot"
}
if (-not (Test-Path $portsPath)) {
    Write-Error "Missing scripts/dev-ports.json (repo dev port registry)."
}
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Error "The .NET 10 SDK is required (dotnet not on PATH). See docs/local-development.md."
}

Import-WeirDotEnv -RepoRoot $repoRoot

if (-not ($env:WEIR_HOME -and $env:WEIR_HOME.Trim())) {
    $env:WEIR_HOME = Join-Path $repoRoot ".local-dev-home"
}
$sec = if ($env:WEIR_SESSION_SECRET) { $env:WEIR_SESSION_SECRET.Trim() } else { "" }
if (-not $sec) {
    Write-Warning "WEIR_SESSION_SECRET is empty; set a long random value before using login/bootstrap."
}
$webDist = Join-Path $repoRoot "apps\web\dist"
if (-not ($env:WEIR_WEB_DIST -and $env:WEIR_WEB_DIST.Trim()) -and (Test-Path (Join-Path $webDist "index.html"))) {
    $env:WEIR_WEB_DIST = $webDist
}
Write-Host "SQLite and runtime files under WEIR_HOME=$($env:WEIR_HOME) (see .env.example)." -ForegroundColor DarkGray
Write-Host ""

$ports = Get-Content $portsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$apiHost = $ports.development.apiHost
$apiPort = [int]$ports.development.apiPort
if ($env:WEIR_DEV_API_PORT -and $env:WEIR_DEV_API_PORT.Trim()) {
    $apiPort = [int]$env:WEIR_DEV_API_PORT.Trim()
}

$busyApi = Get-NetTCPConnection -LocalPort $apiPort -State Listen -ErrorAction SilentlyContinue
if ($busyApi) {
    Write-Error (
        "Port $apiPort is already in use. Stop the other API or set WEIR_DEV_API_PORT. " +
        "Vite's /api proxy will fail until the correct API is listening here."
    )
}

# `dotnet watch` rebuilds and restarts on source changes, like the old --reload.
& dotnet watch run --project $serverProject -- --host $apiHost --port $apiPort
exit $LASTEXITCODE
