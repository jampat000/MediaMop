param(
  [string]$PackageDir = "",
  [int]$Port = 8799,
  [string]$ExpectedVersion = ""
)

$ErrorActionPreference = "Stop"

# Smoke test for the assembled Windows package (packaging/windows/build-velopack.ps1): the exact
# server directory the tray app launches (dist\windows\pack\server), started the way the tray starts
# it, then driven through sign-up, a library and a real pass-through job with the bundled ffmpeg.

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $PackageDir) {
  $PackageDir = Join-Path $repoRoot "dist\windows\pack\server"
}
$packagePath = (Resolve-Path -LiteralPath $PackageDir).Path
if (-not $ExpectedVersion) {
  $propsPath = Join-Path $repoRoot "apps\server\Directory.Build.props"
  $propsMatch = [regex]::Match((Get-Content -LiteralPath $propsPath -Raw), '<WeirVersion>([^<]+)</WeirVersion>')
  if (-not $propsMatch.Success) {
    throw "WeirVersion was not found in $propsPath."
  }
  $ExpectedVersion = $propsMatch.Groups[1].Value.Trim()
}
$serverExe = Join-Path $packagePath "WeirServer.exe"
$webDist = Join-Path $packagePath "web-dist"
$webIndex = Join-Path $webDist "index.html"
$ffmpegExe = Join-Path $packagePath "bin\ffmpeg\ffmpeg.exe"
$ffprobeExe = Join-Path $packagePath "bin\ffmpeg\ffprobe.exe"
$trayExe = Join-Path (Split-Path -Parent $packagePath) "Weir.exe"

if (-not (Test-Path -LiteralPath $serverExe)) {
  throw "Packaged server executable not found: $serverExe"
}
if (-not (Test-Path -LiteralPath $trayExe)) {
  throw "Packaged tray executable not found next to the server folder: $trayExe"
}
if (-not (Test-Path -LiteralPath $webIndex)) {
  throw "Packaged web index not found: $webIndex"
}
if (-not (Test-Path -LiteralPath $ffmpegExe)) {
  throw "Packaged ffmpeg executable not found: $ffmpegExe"
}
if (-not (Test-Path -LiteralPath $ffprobeExe)) {
  throw "Packaged ffprobe executable not found: $ffprobeExe"
}
$indexText = Get-Content -LiteralPath $webIndex -Raw
if ($indexText -notmatch "Weir") {
  throw "Packaged web index does not look like Weir."
}

$serverVersion = (& $serverExe --version).Trim()
if ($serverVersion -ne $ExpectedVersion) {
  throw "Packaged WeirServer.exe reports version '$serverVersion' but expected '$ExpectedVersion'."
}

$runtimeHome = Join-Path ([System.IO.Path]::GetTempPath()) ("weir-package-smoke-" + [System.Guid]::NewGuid().ToString("N"))
$stdout = Join-Path $runtimeHome "server.stdout.log"
$stderr = Join-Path $runtimeHome "server.stderr.log"
New-Item -ItemType Directory -Path $runtimeHome | Out-Null

$oldHome = $env:WEIR_HOME
$oldSecret = $env:WEIR_SESSION_SECRET
$oldCookieSecure = $env:WEIR_SESSION_COOKIE_SECURE
$oldEnv = $env:WEIR_ENV
$oldWebDist = $env:WEIR_WEB_DIST
$oldFfmpegDir = $env:WEIR_FFMPEG_DIR
$oldPath = $env:PATH
$proc = $null

try {
  $env:WEIR_HOME = $runtimeHome
  $env:WEIR_SESSION_SECRET = "ci-weir-session-secret-32chars-min"
  $env:WEIR_SESSION_COOKIE_SECURE = "false"
  # The environment the tray app gives the server (apps/tray/Weir.Tray/Program.cs, PrepareEnvironment).
  $env:WEIR_ENV = "production"
  $env:WEIR_WEB_DIST = $webDist
  # The bundled ffmpeg must be found on its own (<app>\bin\ffmpeg), not through a developer's PATH.
  Remove-Item Env:\WEIR_FFMPEG_DIR -ErrorAction SilentlyContinue
  $env:PATH = (($oldPath -split ";") | Where-Object {
      $_ -and -not (Test-Path -LiteralPath (Join-Path $_ "ffprobe.exe")) -and -not (Test-Path -LiteralPath (Join-Path $_ "ffmpeg.exe"))
    }) -join ";"

  $proc = Start-Process -FilePath $serverExe `
    -ArgumentList @("--port", [string]$Port) `
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
      throw "Packaged Weir server exited early with code $($proc.ExitCode)."
    }
    try {
      $ready = Invoke-RestMethod -Uri $readyUrl -Method Get -TimeoutSec 2
      if ($ready.ready -eq $true) {
        $openApi = Invoke-RestMethod -Uri $openApiUrl -Method Get -TimeoutSec 2
        $reportedVersion = [string]$openApi.info.version
        if ($reportedVersion -ne $ExpectedVersion) {
          throw "Packaged Weir server reported version '$reportedVersion' but expected '$ExpectedVersion'."
        }
        Write-Host "Packaged Weir server readiness and version checks passed on $readyUrl"
        $serverReady = $true
        break
      }
    } catch {
      Start-Sleep -Milliseconds 500
    }
  } while ((Get-Date) -lt $deadline)

  if (-not $serverReady) {
    throw "Packaged Weir server did not become ready at $readyUrl."
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
  # The Direct Play device list is a data file; prove the packaged app can read it (#467).
  $devices = Invoke-RestMethod -Uri "$baseUrl/api/v1/refiner/direct-play/devices" -WebSession $webSession -Headers $readHeaders -TimeoutSec 15
  if (-not $devices.devices -or $devices.devices.Count -lt 1) {
    throw "The packaged app could not load its Direct Play device list."
  }

  # The server must find the ffmpeg bundled next to it (<app>\bin\ffmpeg); PATH was stripped of ffmpeg above.
  $hardware = Invoke-RestMethod -Uri "$baseUrl/api/v1/refiner/hardware" -WebSession $webSession -Headers $readHeaders -TimeoutSec 60
  if ([string]$hardware.detail -match "could not find ffmpeg") {
    throw "The packaged server did not find its bundled ffmpeg: $($hardware.detail)"
  }
  Write-Host "Packaged server found its bundled ffmpeg."

  # Configure the seeded Movies library directly (the path-settings route was retired in #460).
  $libraries = Invoke-RestMethod -Uri "$baseUrl/api/v1/refiner/libraries" -WebSession $webSession -Headers $readHeaders -TimeoutSec 15
  $moviesLibrary = $libraries | Where-Object { $_.media_type -eq "movie" } | Select-Object -First 1
  if (-not $moviesLibrary) {
    throw "The packaged install has no Movies library to configure."
  }
  $pathBody = @{
    csrf_token = $csrf
    name = $moviesLibrary.name
    media_type = "movie"
    watched_folder = $watchedRoot
    work_folder = $workRoot
    output_folder = $outputRoot
    manager_connection_ids = @($moviesLibrary.manager_connection_ids)
  } | ConvertTo-Json -Compress
  Invoke-RestMethod -Method Put -Uri "$baseUrl/api/v1/refiner/libraries/$($moviesLibrary.id)" -WebSession $webSession -Headers $browserHeaders -Body $pathBody -TimeoutSec 15 | Out-Null

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
  $logPath = Join-Path $runtimeHome "logs\weir.log"
  if (Test-Path -LiteralPath $logPath) {
    Write-Host "--- weir.log ---"
    Get-Content -LiteralPath $logPath -Tail 200
  }
  throw
} finally {
  if ($proc -and -not $proc.HasExited) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
  }
  if ($null -ne $oldHome) { $env:WEIR_HOME = $oldHome } else { Remove-Item Env:\WEIR_HOME -ErrorAction SilentlyContinue }
  if ($null -ne $oldSecret) { $env:WEIR_SESSION_SECRET = $oldSecret } else { Remove-Item Env:\WEIR_SESSION_SECRET -ErrorAction SilentlyContinue }
  if ($null -ne $oldCookieSecure) { $env:WEIR_SESSION_COOKIE_SECURE = $oldCookieSecure } else { Remove-Item Env:\WEIR_SESSION_COOKIE_SECURE -ErrorAction SilentlyContinue }
  if ($null -ne $oldEnv) { $env:WEIR_ENV = $oldEnv } else { Remove-Item Env:\WEIR_ENV -ErrorAction SilentlyContinue }
  if ($null -ne $oldWebDist) { $env:WEIR_WEB_DIST = $oldWebDist } else { Remove-Item Env:\WEIR_WEB_DIST -ErrorAction SilentlyContinue }
  if ($null -ne $oldFfmpegDir) { $env:WEIR_FFMPEG_DIR = $oldFfmpegDir } else { Remove-Item Env:\WEIR_FFMPEG_DIR -ErrorAction SilentlyContinue }
  $env:PATH = $oldPath
  Remove-Item -LiteralPath $runtimeHome -Recurse -Force -ErrorAction SilentlyContinue
}
