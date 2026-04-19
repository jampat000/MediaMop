# Run Vite dev server (hosts/ports from scripts/dev-ports.json via apps/web/vite.config.ts).
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$web = Join-Path $repoRoot "apps\web"

if (-not (Test-Path $web)) {
    Write-Error "Expected apps/web under $repoRoot"
}

function Ensure-NodeOnPath {
    if (Get-Command npm -ErrorAction SilentlyContinue) { return }
    $candidates = @(
        (Join-Path $env:ProgramFiles "nodejs"),
        (Join-Path ${env:ProgramFiles(x86)} "nodejs"),
        (Join-Path $env:LocalAppData "Programs\nodejs")
    )
    foreach ($dir in $candidates) {
        if ($dir -and (Test-Path (Join-Path $dir "npm.cmd"))) {
            $env:Path = "$dir;$env:Path"
            return
        }
    }
}

Ensure-NodeOnPath

$portsPath = Join-Path $PSScriptRoot "dev-ports.json"
if (Test-Path $portsPath) {
    $ports = Get-Content $portsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $webPort = [int]$ports.development.webPort
    $busy = Get-NetTCPConnection -LocalPort $webPort -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        Write-Error (
            "Port $webPort is already in use (another dev server?). " +
            "Stop it or change scripts/dev-ports.json. " +
            "Otherwise the browser shows ERR_CONNECTION_REFUSED or Vite exits immediately."
        )
    }
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if (-not $npm) {
    Write-Error "npm not on PATH. Install Node.js LTS (winget install OpenJS.NodeJS.LTS), then open a new PowerShell window."
}

Set-Location $web
if (-not (Test-Path "node_modules")) {
    if (Test-Path "package-lock.json") {
        Write-Host "Running npm ci..."
        npm ci
    } else {
        Write-Host "Running npm install..."
        npm install
    }
}
Write-Host "Same-origin dev: browser uses relative /api/v1 via Vite proxy. Run dev-backend.ps1 in another terminal." -ForegroundColor DarkGray
npm run dev
