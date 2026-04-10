# Local stabilization verification from repo root.
#
# Phases (fail fast, concrete messages):
#   1) Static/unit — pytest subset; no running API.
#   2) Config presence — apps/backend/.env file hint + required env vars after dotenv load (values never printed).
#   3) Live database — SQLite path + Alembic head via scripts/verify_local_db.py (MEDIAMOP_HOME / MEDIAMOP_DB_PATH).
#   4) Live API — GET /health and GET /api/v1/auth/bootstrap/status (needs dev-backend.ps1 running).
#   5) Static repo check only — vite.config.ts mentions API port and /api (NOT proof Vite is running or proxying).
#
# See docs/local-development.md.
param(
    [switch] $SkipBackendTests,
    [switch] $SkipLiveChecks
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\mediamop-env.ps1"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot "apps\backend"
$portsPath = Join-Path $PSScriptRoot "dev-ports.json"
$viteConfig = Join-Path $repoRoot "apps\web\vite.config.ts"

function Write-Section($title) {
    Write-Host ""
    Write-Host "== $title ==" -ForegroundColor Cyan
}

if (-not (Test-Path $backend)) {
    Write-Error "Expected apps/backend under $repoRoot"
}

# --- Phase 1: static/unit tests (no DB, no API) ---
if (-not $SkipBackendTests) {
    Write-Section "Phase 1: static/unit tests (no live API)"
    Push-Location $backend
    $env:PYTHONPATH = "src"
    try {
        & py -3 -m pytest `
            tests/test_health.py `
            tests/test_sqlite_foundation.py `
            tests/test_bootstrap_status_db_unit.py `
            tests/test_bootstrap_status_router.py `
            tests/test_db_dep.py `
            tests/test_config_env_parsing.py `
            tests/test_password_invalid_hash.py `
            tests/test_csrf_unit.py `
            -q --tb=short
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Pop-Location
    }
}

if ($SkipLiveChecks) {
    Write-Host ""
    Write-Host "SkipLiveChecks: stopped after Phase 1." -ForegroundColor Yellow
    exit 0
}

Write-Section "Phase 2: config presence (.env file + required variables)"
$envFile = Join-Path $backend ".env"
if (Test-Path -LiteralPath $envFile) {
    Write-Host "OK: apps/backend/.env exists (values not shown)." -ForegroundColor Green
} else {
    Write-Host "MISSING: apps/backend/.env — copy apps/backend/.env.example or set MEDIAMOP_* in this shell." -ForegroundColor Yellow
}

Import-MediaMopBackendDotEnv -BackendDir $backend

$sessionSecret = if ($env:MEDIAMOP_SESSION_SECRET -and $env:MEDIAMOP_SESSION_SECRET.Trim()) {
    $env:MEDIAMOP_SESSION_SECRET.Trim()
} else { $null }

if (-not $sessionSecret) {
    Write-Host "FAIL: MEDIAMOP_SESSION_SECRET is not set — auth and CSRF require it." -ForegroundColor Red
    exit 11
}
Write-Host "OK: MEDIAMOP_SESSION_SECRET is set (value not shown)." -ForegroundColor Green
if ($env:MEDIAMOP_HOME -and $env:MEDIAMOP_HOME.Trim()) {
    Write-Host "OK: MEDIAMOP_HOME is set (value not shown)." -ForegroundColor Green
} else {
    Write-Host "Note: MEDIAMOP_HOME unset — default OS data directory will be used for SQLite (see apps/backend/.env.example)." -ForegroundColor DarkGray
}

$venvPython = Join-Path $backend '.venv\Scripts\python.exe'
if (Test-Path $venvPython) {
    $pyExe = $venvPython
} else {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $py) {
        Write-Error 'Python not on PATH. From apps/backend: py -3 -m venv .venv; pip install -e .'
    }
    $pyExe = $py.Source
}

Write-Section "Phase 3: live database + Alembic head"
& $pyExe (Join-Path $PSScriptRoot "verify_local_db.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "FAIL: database / migration check (exit $($LASTEXITCODE))." -ForegroundColor Red
    exit $LASTEXITCODE
}

if (-not (Test-Path $portsPath)) {
    Write-Error "Missing scripts/dev-ports.json"
}
$ports = Get-Content $portsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$apiHost = $ports.development.apiHost
$apiPort = [int]$ports.development.apiPort
$webPort = [int]$ports.development.webPort
$healthUrl = "http://${apiHost}:${apiPort}/health"
$bootstrapUrl = "http://${apiHost}:${apiPort}/api/v1/auth/bootstrap/status"

Write-Section "Phase 4: live API (health + bootstrap status)"
try {
    $health = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 8
    if ($health.StatusCode -ne 200) {
        Write-Host "FAIL: GET /health returned HTTP $($health.StatusCode) (expected 200)." -ForegroundColor Red
        exit 30
    }
    Write-Host "OK: GET /health returned 200 (liveness; does not imply /api/v1 is ready)." -ForegroundColor Green
} catch {
    Write-Host "FAIL: cannot reach API at $healthUrl — start .\scripts\dev-backend.ps1 (see docs/local-development.md)." -ForegroundColor Red
    Write-Host "  $($_.Exception.Message)" -ForegroundColor DarkGray
    exit 31
}

$curl = Get-Command curl.exe -ErrorAction SilentlyContinue
if ($curl) {
    $codeStr = (& curl.exe -s -o NUL -w "%{http_code}" $bootstrapUrl 2>$null).Trim()
    if ($codeStr -notmatch '^\d{3}$') {
        Write-Host "FAIL: could not read HTTP status from bootstrap/status (curl)." -ForegroundColor Red
        exit 32
    }
    $code = [int]$codeStr
} else {
    try {
        $bs = Invoke-WebRequest -Uri $bootstrapUrl -UseBasicParsing -TimeoutSec 8
        $code = [int]$bs.StatusCode
    } catch {
        $resp = $_.Exception.Response
        if ($null -eq $resp) {
            Write-Host "FAIL: bootstrap/status request error: $($_.Exception.Message)" -ForegroundColor Red
            exit 32
        }
        $code = [int]$resp.StatusCode
    }
}

if ($code -eq 500) {
    Write-Host "FAIL: GET bootstrap/status returned HTTP 500 — expected 200 (ready) or 503 (DB/schema not ready), not 500." -ForegroundColor Red
    exit 33
}
if ($code -ne 200 -and $code -ne 503) {
    Write-Host "WARN: GET bootstrap/status returned HTTP $code (expected 200 or 503)." -ForegroundColor Yellow
} else {
    Write-Host "OK: GET bootstrap/status returned $code (readiness under /api/v1; 503 is expected when DB/schema unset)." -ForegroundColor Green
}

Write-Section "Phase 5: static check — Vite proxy config in repo (not a live proxy test)"
if (-not (Test-Path $viteConfig)) {
    Write-Host "FAIL: missing $viteConfig" -ForegroundColor Red
    exit 40
}
$viteText = Get-Content -LiteralPath $viteConfig -Raw -Encoding UTF8
if ($viteText -notmatch [regex]::Escape("$apiPort")) {
    Write-Host "FAIL: apps/web/vite.config.ts should reference API port $apiPort from dev-ports.json." -ForegroundColor Red
    exit 41
}
if ($viteText -notmatch '/api') {
    Write-Host "FAIL: apps/web/vite.config.ts should define a proxy for path /api." -ForegroundColor Red
    exit 42
}
Write-Host "OK: vite.config.ts references port $apiPort and /api (verify dev server separately: npm run dev)." -ForegroundColor Green
Write-Host "OK: Web dev URL from dev-ports.json: http://$($ports.development.webHost):$webPort" -ForegroundColor Green

Write-Host ""
Write-Host "All verification phases passed." -ForegroundColor Green
