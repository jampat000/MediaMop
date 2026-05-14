#Requires -Version 5.1
<#
.SYNOPSIS
    Local pre-push checks - same gates as CI, run before every push.

.DESCRIPTION
    Runs ruff, prettier, and an OpenAPI spec/types drift check so formatting
    and sync errors are caught locally rather than burning a CI run.

    Called automatically by .githooks/pre-push.
    Run manually: powershell -ExecutionPolicy Bypass -File scripts/pre-push-check.ps1

.NOTES
    One-time setup to activate the git hook:
        git config core.hooksPath .githooks
#>

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$REPO = (git rev-parse --show-toplevel) -replace "/", "\"

function Step($label) { Write-Host "[pre-push] $label..." -ForegroundColor Cyan }
function Pass($label) { Write-Host "[pre-push] $label OK" -ForegroundColor Green }
function Skip($label) { Write-Host "[pre-push] $label skipped" -ForegroundColor Yellow }
function Fail($msg)   { Write-Host "[pre-push] FAIL: $msg" -ForegroundColor Red; exit 1 }

# ---- ruff -------------------------------------------------------------------
$ruff = "$REPO\apps\backend\.venv\Scripts\ruff.exe"
if (-not (Test-Path $ruff)) {
    Skip "ruff (run: pip install -e '.[dev]' in apps/backend)"
} else {
    Step "ruff"
    Push-Location "$REPO\apps\backend"
    & $ruff check src tests
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "ruff check failed" }
    & $ruff format --check src tests
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host "  Fix: ruff format src tests" -ForegroundColor Yellow
        Fail "ruff format --check failed"
    }
    Pop-Location
    Pass "ruff"
}

# ---- prettier ---------------------------------------------------------------
$prettierBin = "$REPO\apps\web\node_modules\prettier\bin\prettier.cjs"
if (-not (Test-Path $prettierBin)) {
    Skip "prettier (run: npm ci in apps/web)"
} else {
    Step "prettier"
    Push-Location "$REPO\apps\web"
    node $prettierBin --check --end-of-line auto 'src/**/*.{ts,tsx,css}' index.html vite.config.ts
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host "  Fix: node apps/web/node_modules/prettier/bin/prettier.cjs --write --end-of-line auto apps/web/src" -ForegroundColor Yellow
        Fail "prettier check failed"
    }
    Pop-Location
    Pass "prettier"
}

# ---- OpenAPI spec + types drift ---------------------------------------------
$venvPython = "$REPO\apps\backend\.venv\Scripts\python.exe"
if (-not (Test-Path $prettierBin) -or -not (Test-Path $venvPython)) {
    Skip "api:types drift (missing node_modules or venv)"
} else {
    Step "api:types drift check"
    Push-Location "$REPO\apps\web"

    $env:MEDIAMOP_PYTHON = $venvPython
    $env:PYTHONPATH = "$REPO\apps\backend\src"
    npm run api:types:sync

    $diff = git diff -- openapi/mediamop-openapi.json src/lib/api/generated/openapi-types.ts
    if ($diff) {
        Write-Host "[pre-push] OpenAPI spec or types differ - auto-committing the sync." -ForegroundColor Yellow
        Pop-Location
        git -C $REPO add apps/web/openapi/mediamop-openapi.json apps/web/src/lib/api/generated/openapi-types.ts
        git -C $REPO commit -m "chore: sync OpenAPI spec and generated types"
        if ($LASTEXITCODE -ne 0) { Fail "Failed to auto-commit OpenAPI sync" }
    } else {
        Pop-Location
    }
    Pass "api:types drift check"
}

Write-Host ""
Write-Host "[pre-push] All checks passed." -ForegroundColor Green
exit 0
