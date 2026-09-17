#Requires -Version 5.1
<#
.SYNOPSIS
    Local pre-push checks - same gates as CI, run before every push.

.DESCRIPTION
    Runs the contract suite's ruff lint, prettier,
    the dead-code guard and an OpenAPI types drift check so formatting and sync errors
    are caught locally rather than burning a CI run.

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

# ---- ruff (contract suite) ---------------------------------------------------
$ruff = Get-Command ruff -ErrorAction SilentlyContinue
if (-not $ruff) {
    Skip "ruff (run: python -m pip install --require-hashes -r tests/requirements.txt)"
} else {
    Step "ruff"
    Push-Location $REPO
    & $ruff.Source check tests/contract
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "ruff check failed" }
    & $ruff.Source format --check tests/contract
    if ($LASTEXITCODE -ne 0) {
        Pop-Location
        Write-Host "  Fix: ruff format tests/contract" -ForegroundColor Yellow
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

# ---- dead code ---------------------------------------------------------------
if (-not (Test-Path $prettierBin)) {
    Skip "dead-code guard (run: npm ci in apps/web)"
} else {
    Step "dead-code guard"
    node "$REPO\scripts\check-dead-code.mjs"
    if ($LASTEXITCODE -ne 0) { Fail "dead-code guard failed" }
    Pass "dead-code guard"
}

# ---- OpenAPI types drift -----------------------------------------------------
# apps/web/openapi/weir-openapi.json is the committed API contract (the server embeds it); the web
# app's generated types must match it.
if (-not (Test-Path $prettierBin)) {
    Skip "api:types drift (missing node_modules)"
} else {
    Step "api:types drift check"
    Push-Location "$REPO\apps\web"
    npm run api:types:generate
    $diff = git diff -- src/lib/api/generated/openapi-types.ts
    if ($diff) {
        Write-Host "[pre-push] Generated API types differ - auto-committing the sync." -ForegroundColor Yellow
        Pop-Location
        git -C $REPO add apps/web/src/lib/api/generated/openapi-types.ts
        git -C $REPO commit -m "chore: sync generated OpenAPI types"
        if ($LASTEXITCODE -ne 0) { Fail "Failed to auto-commit OpenAPI types sync" }
    } else {
        Pop-Location
    }
    Pass "api:types drift check"
}

Write-Host ""
Write-Host "[pre-push] All checks passed." -ForegroundColor Green
exit 0
