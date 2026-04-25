param(
  [string]$PackageDir = "",
  [int]$Port = 8799
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $PackageDir) {
  $PackageDir = Join-Path $repoRoot "dist\windows\MediaMop"
}
$packagePath = (Resolve-Path -LiteralPath $PackageDir).Path
$serverExe = Join-Path $packagePath "MediaMopServer.exe"
$webIndex = Join-Path $packagePath "_internal\web-dist\index.html"
$trayIcon = Join-Path $packagePath "_internal\assets\mediamop-tray-icon.png"

if (-not (Test-Path -LiteralPath $serverExe)) {
  throw "Packaged server executable not found: $serverExe"
}
if (-not (Test-Path -LiteralPath $webIndex)) {
  throw "Packaged web index not found: $webIndex"
}
if (-not (Test-Path -LiteralPath $trayIcon)) {
  throw "Packaged tray icon not found: $trayIcon"
}
$indexText = Get-Content -LiteralPath $webIndex -Raw
if ($indexText -notmatch "MediaMop") {
  throw "Packaged web index does not look like MediaMop."
}

$runtimeHome = Join-Path ([System.IO.Path]::GetTempPath()) ("mediamop-package-smoke-" + [System.Guid]::NewGuid().ToString("N"))
$stdout = Join-Path $runtimeHome "server.stdout.log"
$stderr = Join-Path $runtimeHome "server.stderr.log"
New-Item -ItemType Directory -Path $runtimeHome | Out-Null

$oldHome = $env:MEDIAMOP_HOME
$oldSecret = $env:MEDIAMOP_SESSION_SECRET
$oldEnv = $env:MEDIAMOP_ENV
$oldWebDist = $env:MEDIAMOP_WEB_DIST
$oldAlembicRoot = $env:MEDIAMOP_ALEMBIC_ROOT
$proc = $null

try {
  $env:MEDIAMOP_HOME = $runtimeHome
  $env:MEDIAMOP_SESSION_SECRET = "ci-mediamop-session-secret-32chars-min"
  Remove-Item Env:\MEDIAMOP_ENV -ErrorAction SilentlyContinue
  Remove-Item Env:\MEDIAMOP_WEB_DIST -ErrorAction SilentlyContinue
  Remove-Item Env:\MEDIAMOP_ALEMBIC_ROOT -ErrorAction SilentlyContinue

  $proc = Start-Process -FilePath $serverExe `
    -ArgumentList @("--serve", "--port", [string]$Port) `
    -WorkingDirectory $packagePath `
    -RedirectStandardOutput $stdout `
    -RedirectStandardError $stderr `
    -WindowStyle Hidden `
    -PassThru

  $healthUrl = "http://127.0.0.1:$Port/health"
  $deadline = (Get-Date).AddSeconds(45)
  do {
    if ($proc.HasExited) {
      throw "Packaged MediaMop server exited early with code $($proc.ExitCode)."
    }
    try {
      $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 2
      if ($response.status -eq "ok") {
        Write-Host "Packaged MediaMop server health check passed on $healthUrl"
        exit 0
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  throw "Packaged MediaMop server did not become healthy at $healthUrl."
} catch {
  Write-Host "Packaged server smoke failed."
  if (Test-Path -LiteralPath $stdout) {
    Write-Host "--- stdout ---"
    Get-Content -LiteralPath $stdout -Tail 200
  }
  if (Test-Path -LiteralPath $stderr) {
    Write-Host "--- stderr ---"
    Get-Content -LiteralPath $stderr -Tail 200
  }
  $logPath = Join-Path $runtimeHome "logs\mediamop.log"
  if (Test-Path -LiteralPath $logPath) {
    Write-Host "--- mediamop.log ---"
    Get-Content -LiteralPath $logPath -Tail 200
  }
  throw
} finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  }
  if ($null -ne $oldHome) { $env:MEDIAMOP_HOME = $oldHome } else { Remove-Item Env:\MEDIAMOP_HOME -ErrorAction SilentlyContinue }
  if ($null -ne $oldSecret) { $env:MEDIAMOP_SESSION_SECRET = $oldSecret } else { Remove-Item Env:\MEDIAMOP_SESSION_SECRET -ErrorAction SilentlyContinue }
  if ($null -ne $oldEnv) { $env:MEDIAMOP_ENV = $oldEnv } else { Remove-Item Env:\MEDIAMOP_ENV -ErrorAction SilentlyContinue }
  if ($null -ne $oldWebDist) { $env:MEDIAMOP_WEB_DIST = $oldWebDist } else { Remove-Item Env:\MEDIAMOP_WEB_DIST -ErrorAction SilentlyContinue }
  if ($null -ne $oldAlembicRoot) { $env:MEDIAMOP_ALEMBIC_ROOT = $oldAlembicRoot } else { Remove-Item Env:\MEDIAMOP_ALEMBIC_ROOT -ErrorAction SilentlyContinue }
  Remove-Item -LiteralPath $runtimeHome -Recurse -Force -ErrorAction SilentlyContinue
}
