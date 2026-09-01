param(
  [string]$PackageDir = "",
  [int]$Port = 8799,
  [string]$ExpectedVersion = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $PackageDir) {
  $PackageDir = Join-Path $repoRoot "dist\windows\MediaMopServer"
}
$packagePath = (Resolve-Path -LiteralPath $PackageDir).Path
$backendPyproject = Join-Path $repoRoot "apps\backend\pyproject.toml"
if (-not $ExpectedVersion) {
  $ExpectedVersion = ((Get-Content -Path $backendPyproject) | Where-Object { $_ -match '^version = ' } | Select-Object -First 1).Split('"')[1]
}
$serverExe = Join-Path $packagePath "MediaMopServer.exe"
$internalRoot = Join-Path $packagePath "_internal"
$webIndex = Join-Path $packagePath "_internal\web-dist\index.html"
$trayIcon = Join-Path $packagePath "_internal\assets\mediamop-tray-icon.png"
$alembicIni = Join-Path $packagePath "_internal\alembic.ini"
$ffmpegExe = Join-Path $packagePath "_internal\bin\ffmpeg\ffmpeg.exe"
$ffprobeExe = Join-Path $packagePath "_internal\bin\ffmpeg\ffprobe.exe"

if (-not (Test-Path -LiteralPath $serverExe)) {
  throw "Packaged server executable not found: $serverExe"
}
if (-not (Test-Path -LiteralPath $webIndex)) {
  throw "Packaged web index not found: $webIndex"
}
if (-not (Test-Path -LiteralPath $trayIcon)) {
  throw "Packaged tray icon not found: $trayIcon"
}
if (-not (Test-Path -LiteralPath $alembicIni)) {
  throw "Packaged database migration config not found: $alembicIni"
}
if (-not (Test-Path -LiteralPath $ffmpegExe)) {
  throw "Packaged ffmpeg executable not found: $ffmpegExe"
}
if (-not (Test-Path -LiteralPath $ffprobeExe)) {
  throw "Packaged ffprobe executable not found: $ffprobeExe"
}
$distInfoDirs = Get-ChildItem -Path $internalRoot -Directory -Filter "mediamop_backend-*.dist-info" -ErrorAction SilentlyContinue
if (-not $distInfoDirs -or $distInfoDirs.Count -eq 0) {
  throw "Packaged backend dist-info metadata was not found in $internalRoot"
}
$indexText = Get-Content -LiteralPath $webIndex -Raw
if ($indexText -notmatch "MediaMop") {
  throw "Packaged web index does not look like MediaMop."
}

$serverVersion = (& $serverExe --version).Trim()
if ($serverVersion -ne $ExpectedVersion) {
  throw "Packaged MediaMopServer.exe reports version '$serverVersion' but expected '$ExpectedVersion'."
}

$runtimeHome = Join-Path ([System.IO.Path]::GetTempPath()) ("mediamop-package-smoke-" + [System.Guid]::NewGuid().ToString("N"))
$stdout = Join-Path $runtimeHome "server.stdout.log"
$stderr = Join-Path $runtimeHome "server.stderr.log"
New-Item -ItemType Directory -Path $runtimeHome | Out-Null

$oldHome = $env:MEDIAMOP_HOME
$oldSecret = $env:MEDIAMOP_SESSION_SECRET
$oldCookieSecure = $env:MEDIAMOP_SESSION_COOKIE_SECURE
$oldEnv = $env:MEDIAMOP_ENV
$oldWebDist = $env:MEDIAMOP_WEB_DIST
$oldAlembicRoot = $env:MEDIAMOP_ALEMBIC_ROOT
$proc = $null

try {
  $env:MEDIAMOP_HOME = $runtimeHome
  $env:MEDIAMOP_SESSION_SECRET = "ci-mediamop-session-secret-32chars-min"
  $env:MEDIAMOP_SESSION_COOKIE_SECURE = "false"
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

  $readyUrl = "http://127.0.0.1:$Port/ready"
  $openApiUrl = "http://127.0.0.1:$Port/openapi.json"
  $deadline = (Get-Date).AddSeconds(60)
  $serverReady = $false
  do {
    if ($proc.HasExited) {
      throw "Packaged MediaMop server exited early with code $($proc.ExitCode)."
    }
    try {
      $ready = Invoke-RestMethod -Uri $readyUrl -Method Get -TimeoutSec 2
      if ($ready.ready -eq $true) {
        $openApi = Invoke-RestMethod -Uri $openApiUrl -Method Get -TimeoutSec 2
        $reportedVersion = [string]$openApi.info.version
        if ($reportedVersion -ne $ExpectedVersion) {
          throw "Packaged MediaMop server reported version '$reportedVersion' but expected '$ExpectedVersion'."
        }
        Write-Host "Packaged MediaMop server readiness and version checks passed on $readyUrl"
        $serverReady = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  if (-not $serverReady) {
    throw "Packaged MediaMop server did not become ready at $readyUrl."
  }

  # Prove the exact packaged server can pass an intentional edge-case file
  # through unchanged, publish it to the configured processed tree, and only
  # then remove the watched source. This is a real filesystem lifecycle test,
  # not an API-shape assertion.
  $fixtureRoot = Join-Path $runtimeHome "pass-through-fixture"
  $watchedRoot = Join-Path $fixtureRoot "watch"
  $workRoot = Join-Path $fixtureRoot "work"
  $outputRoot = Join-Path $fixtureRoot "processed"
  $releaseRoot = Join-Path $watchedRoot "ForeignFilm"
  New-Item -ItemType Directory -Path $releaseRoot, $workRoot, $outputRoot | Out-Null
  $sourcePath = Join-Path $releaseRoot "foreign-only.mkv"
  & $ffmpegExe `
    -nostdin -hide_banner -loglevel error `
    -f lavfi -i "color=c=black:s=320x180:d=2" `
    -f lavfi -i "sine=frequency=440:duration=2" `
    -map 0:v -map 1:a -c:v mpeg4 -c:a aac `
    -metadata:s:a:0 language=jpn -y $sourcePath
  if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
    throw "Packaged FFmpeg could not create the pass-through fixture."
  }
  (Get-Item -LiteralPath $sourcePath).LastWriteTime = (Get-Date).AddMinutes(-10)
  $sourceLength = (Get-Item -LiteralPath $sourcePath).Length
  $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourcePath).Hash

  $baseUrl = "http://127.0.0.1:$Port"
  $browserHeaders = @{
    Origin = $baseUrl
    "Content-Type" = "application/json"
    "X-Requested-With" = "XMLHttpRequest"
  }
  $readHeaders = @{ "X-Requested-With" = "XMLHttpRequest" }
  $webSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession

  $csrf = (Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/csrf" -WebSession $webSession -Headers $readHeaders -TimeoutSec 15).csrf_token
  $bootstrapBody = @{
    username = "package-smoke-admin"
    password = "package-smoke-pass-20260901"
    csrf_token = $csrf
  } | ConvertTo-Json -Compress
  Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/auth/bootstrap" -WebSession $webSession -Headers $browserHeaders -Body $bootstrapBody -TimeoutSec 15 | Out-Null

  $csrf = (Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/csrf" -WebSession $webSession -Headers $readHeaders -TimeoutSec 15).csrf_token
  $loginBody = @{
    username = "package-smoke-admin"
    password = "package-smoke-pass-20260901"
    csrf_token = $csrf
    trusted_device = $false
  } | ConvertTo-Json -Compress
  Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/auth/login" -WebSession $webSession -Headers $browserHeaders -Body $loginBody -TimeoutSec 15 | Out-Null

  $csrf = (Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/csrf" -WebSession $webSession -Headers $readHeaders -TimeoutSec 15).csrf_token
  $pathBody = @{
    csrf_token = $csrf
    refiner_watched_folder = $watchedRoot
    refiner_work_folder = $workRoot
    refiner_output_folder = $outputRoot
  } | ConvertTo-Json -Compress
  Invoke-RestMethod -Method Put -Uri "$baseUrl/api/v1/refiner/path-settings" -WebSession $webSession -Headers $browserHeaders -Body $pathBody -TimeoutSec 15 | Out-Null

  $csrf = (Invoke-RestMethod -Uri "$baseUrl/api/v1/auth/csrf" -WebSession $webSession -Headers $readHeaders -TimeoutSec 15).csrf_token
  $enqueueBody = @{
    csrf_token = $csrf
    relative_media_path = "ForeignFilm/foreign-only.mkv"
    media_scope = "movie"
    pass_through_unchanged = $true
  } | ConvertTo-Json -Compress
  $job = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/v1/refiner/jobs/file-remux-pass/enqueue" -WebSession $webSession -Headers $browserHeaders -Body $enqueueBody -TimeoutSec 15
  if (-not $job.job_id) {
    throw "Pass-through enqueue did not return a job id."
  }

  $outputPath = Join-Path $outputRoot "ForeignFilm\foreign-only.mkv"
  $jobDeadline = (Get-Date).AddSeconds(90)
  $jobStatus = ""
  $lastError = ""
  do {
    $inspection = Invoke-RestMethod -Uri "$baseUrl/api/v1/refiner/jobs/inspection?limit=100" -WebSession $webSession -Headers $readHeaders -TimeoutSec 15
    $jobRow = $inspection.jobs | Where-Object { $_.id -eq $job.job_id } | Select-Object -First 1
    if ($jobRow) {
      $jobStatus = [string]$jobRow.status
      $lastError = [string]$jobRow.last_error
      if ($jobStatus -in @("failed", "cancelled")) {
        break
      }
    }
    if ($jobStatus -eq "completed" -and (Test-Path -LiteralPath $outputPath -PathType Leaf) -and -not (Test-Path -LiteralPath $sourcePath)) {
      break
    }
    Start-Sleep -Milliseconds 250
  } while ((Get-Date) -lt $jobDeadline)

  if ($jobStatus -ne "completed") {
    throw "Pass-through job did not complete (status='$jobStatus', error='$lastError')."
  }
  if (Test-Path -LiteralPath $sourcePath) {
    throw "Pass-through source was not removed after successful output validation."
  }
  if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
    throw "Pass-through output was not placed in the configured processed folder."
  }
  $outputLength = (Get-Item -LiteralPath $outputPath).Length
  $outputHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $outputPath).Hash
  if ($outputLength -ne $sourceLength -or $outputHash -ne $sourceHash) {
    throw "Pass-through output is not byte-identical to the source fixture."
  }
  Write-Host "Packaged Refiner pass-through lifecycle passed: source cleaned after byte-identical processed output was validated."
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
  if ($null -ne $oldCookieSecure) { $env:MEDIAMOP_SESSION_COOKIE_SECURE = $oldCookieSecure } else { Remove-Item Env:\MEDIAMOP_SESSION_COOKIE_SECURE -ErrorAction SilentlyContinue }
  if ($null -ne $oldEnv) { $env:MEDIAMOP_ENV = $oldEnv } else { Remove-Item Env:\MEDIAMOP_ENV -ErrorAction SilentlyContinue }
  if ($null -ne $oldWebDist) { $env:MEDIAMOP_WEB_DIST = $oldWebDist } else { Remove-Item Env:\MEDIAMOP_WEB_DIST -ErrorAction SilentlyContinue }
  if ($null -ne $oldAlembicRoot) { $env:MEDIAMOP_ALEMBIC_ROOT = $oldAlembicRoot } else { Remove-Item Env:\MEDIAMOP_ALEMBIC_ROOT -ErrorAction SilentlyContinue }
  Remove-Item -LiteralPath $runtimeHome -Recurse -Force -ErrorAction SilentlyContinue
}
