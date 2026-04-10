# Run Alembic migrations. Resolves repo root from this script's location.
# Loads apps/backend/.env into the process (keys only if not already set in the shell), same as the API.
#
# SQLite-first: database path comes from MEDIAMOP_HOME (default OS data dir) and optional MEDIAMOP_DB_PATH.
# See docs/local-development.md (being updated for SQLite).
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\mediamop-env.ps1"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot "apps\backend"

if (-not (Test-Path $backend)) {
    Write-Error "Expected apps/backend under $repoRoot"
}

Import-MediaMopBackendDotEnv -BackendDir $backend

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

Write-Host 'Running: alembic upgrade head' -ForegroundColor Gray
& $pyExe -m alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Migrations failed. Confirm MEDIAMOP_HOME / MEDIAMOP_DB_PATH and that the DB file parent directory is writable.' -ForegroundColor Yellow
    exit $LASTEXITCODE
}
Write-Host 'Migrations complete.' -ForegroundColor Green
