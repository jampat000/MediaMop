# Launcher: opens two new windows for the API (the .NET server, dotnet watch) and web (Vite).
# The server creates or migrates its own database on start. This script performs lightweight
# preflight checks only — fix anything reported as MISSING before expecting a working app.
#
# Intended order: copy .env.example to .env (repository root) → this script.
# See docs/local-development.md.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\weir-env.ps1"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendScript = Join-Path $PSScriptRoot "dev-backend.ps1"
$webScript = Join-Path $PSScriptRoot "dev-web.ps1"

if (-not (Test-Path $backendScript) -or -not (Test-Path $webScript)) {
    Write-Error "Expected dev-backend.ps1 and dev-web.ps1 next to this script."
}

Write-Host "== dev.ps1 (launcher only) ==" -ForegroundColor Cyan
Write-Host "Opening API + web in new windows. This does not verify DB readiness." -ForegroundColor DarkGray
Write-Host "Single-terminal alternative: cd apps\web && npm run dev  (stops default dev ports, then API + Vite)." -ForegroundColor DarkGray

$issues = 0
$envFile = Join-Path $repoRoot ".env"
if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Host "MISSING: .env at the repository root - copy .env.example; shell-only env is still possible." -ForegroundColor Yellow
    $issues++
}
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Host "MISSING: dotnet (the .NET 10 SDK) - the API cannot start without it." -ForegroundColor Yellow
    $issues++
}

Import-WeirDotEnv -RepoRoot $repoRoot

if (-not ($env:WEIR_SESSION_SECRET -and $env:WEIR_SESSION_SECRET.Trim())) {
    Write-Host "MISSING: WEIR_SESSION_SECRET - auth/CSRF will not work until set." -ForegroundColor Yellow
    $issues++
}

if ($issues -gt 0) {
    Write-Host ""
    Write-Host ('Preflight: {0} issue(s) above - app is not fully ready until resolved. Run .\scripts\verify-local.ps1 when API is up.' -f $issues) -ForegroundColor Yellow
} else {
    Write-Host "Preflight: .env, SESSION_SECRET and dotnet present (values not verified here)." -ForegroundColor Green
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
