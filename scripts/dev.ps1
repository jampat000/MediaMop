# Launcher: opens two new windows for API (uvicorn) and web (Vite).
# This script does NOT run migrations. It performs lightweight preflight
# checks only — fix anything reported as MISSING before expecting a working app.
#
# Intended order: apps/backend/.env → .\scripts\dev-migrate.ps1 → this script.
# See docs/local-development.md.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\mediamop-env.ps1"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot "dev-backend.ps1"
$webScript = Join-Path $PSScriptRoot "dev-web.ps1"
$backendDir = Join-Path $repoRoot "apps\backend"

if (-not (Test-Path $backendScript) -or -not (Test-Path $webScript)) {
    Write-Error "Expected dev-backend.ps1 and dev-web.ps1 next to this script."
}

Write-Host "== dev.ps1 (launcher only) ==" -ForegroundColor Cyan
Write-Host "Opening API + web in new windows. This does not verify migrations or DB readiness." -ForegroundColor DarkGray

$issues = 0
$envFile = Join-Path $backendDir ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Host "MISSING: apps/backend/.env - copy .env.example; shell-only env is still possible." -ForegroundColor Yellow
    $issues++
}

Import-MediaMopBackendDotEnv -BackendDir $backendDir

if (-not ($env:MEDIAMOP_SESSION_SECRET -and $env:MEDIAMOP_SESSION_SECRET.Trim())) {
    Write-Host "MISSING: MEDIAMOP_SESSION_SECRET - auth/CSRF will not work until set." -ForegroundColor Yellow
    $issues++
}

if ($issues -gt 0) {
    Write-Host ""
    Write-Host ('Preflight: {0} issue(s) above - app is not fully ready until resolved. Run .\scripts\verify-local.ps1 when API is up.' -f $issues) -ForegroundColor Yellow
} else {
    Write-Host "Preflight: .env and SESSION_SECRET present (values not verified here). Run dev-migrate if the DB is new." -ForegroundColor Green
}

$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }

Start-Process $shell -WorkingDirectory $repoRoot -ArgumentList @(
    "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $backendScript
)
Start-Process $shell -WorkingDirectory $repoRoot -ArgumentList @(
    "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $webScript
)

$portsPath = Join-Path $PSScriptRoot "dev-ports.json"
$ports = Get-Content $portsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$d = $ports.development
Write-Host ""
Write-Host "Started API and web dev in new windows (launcher only - not a full stack guarantee)." -ForegroundColor Gray
Write-Host ("  API: http://{0}:{1}" -f $d.apiHost, $d.apiPort)
Write-Host ("  Web: http://{0}:{1}" -f $d.webHost, $d.webPort)
Write-Host "First-time: .\scripts\dev-migrate.ps1, then use this launcher." -ForegroundColor DarkGray
