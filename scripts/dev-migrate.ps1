# Run Alembic migrations. Resolves repo root from this script's location.
# Loads apps/backend/.env into the process (keys only if not already set in the shell), same as the API.
#
# Default: MEDIAMOP_DATABASE_URL must be set (shell or uncommented line in apps/backend/.env).
# Optional Docker Compose Postgres (host 127.0.0.1:5433) is opt-in only:
#   .\scripts\dev-migrate.ps1 -UseComposeDevDb
#
# See docs/local-development.md.
param(
    [switch] $UseComposeDevDb
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\mediamop-env.ps1"
$repoRoot = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $repoRoot "apps\backend"

if (-not (Test-Path $backend)) {
    Write-Error "Expected apps/backend under $repoRoot"
}

Import-MediaMopBackendDotEnv -BackendDir $backend

$dbRaw = $env:MEDIAMOP_DATABASE_URL
$dbUrl = if ($dbRaw -and $dbRaw.Trim()) { $dbRaw.Trim() } else { $null }

if (-not $dbUrl) {
    if ($UseComposeDevDb) {
        $dbUrl = "postgresql+psycopg://mediamop:mediamop@127.0.0.1:5433/mediamop"
        Write-Host "Using optional Compose dev DB URL (127.0.0.1:5433) because -UseComposeDevDb was set." -ForegroundColor Cyan
        Write-Host "Ensure 'docker compose up -d' has been run from repo root if you rely on this database." -ForegroundColor DarkGray
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $tcp.Connect("127.0.0.1", 5433)
            $tcp.Close()
        } catch {
            Write-Error (
                "Cannot reach PostgreSQL at 127.0.0.1:5433. Start optional Compose Postgres from repo root " +
                "(docker compose up -d) or set MEDIAMOP_DATABASE_URL (native Windows Postgres is usually port 5432). " +
                "See docs/local-development.md."
            )
        }
    } else {
        Write-Error (
            "MEDIAMOP_DATABASE_URL is not set. Set it in apps/backend/.env (uncomment and edit the URL) or in this shell. " +
            "Native Windows PostgreSQL typically uses 127.0.0.1:5432. " +
            "To migrate against the optional Docker Compose database on 127.0.0.1:5433, run: " +
            ".\scripts\dev-migrate.ps1 -UseComposeDevDb. See docs/local-development.md."
        )
    }
}

$env:MEDIAMOP_DATABASE_URL = $dbUrl
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
    Write-Host 'Migrations failed. Confirm PostgreSQL is running and MEDIAMOP_DATABASE_URL matches it. See docs/local-development.md.' -ForegroundColor Yellow
    exit $LASTEXITCODE
}
Write-Host 'Migrations complete.' -ForegroundColor Green
