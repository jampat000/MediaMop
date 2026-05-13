param(
  [switch]$SkipWebBuild,
  [switch]$SkipDotnetPublish
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$backendDir = Join-Path $repoRoot "apps\\backend"
$webDir = Join-Path $repoRoot "apps\\web"
$trayDir = Join-Path $repoRoot "apps\\tray\\MediaMop.Tray"
$serverSpecPath = Join-Path $PSScriptRoot "mediamop-server.spec"
$distRoot = Join-Path $repoRoot "dist\\windows"
$velopackOut = Join-Path $distRoot "releases"
$ffmpegVendorDir = Join-Path $PSScriptRoot "vendor\\ffmpeg"
$venvScriptsDir = Join-Path $backendDir ".venv\\Scripts"
$py = Join-Path $venvScriptsDir "python.exe"
$ffmpegArchiveName = "ffmpeg-N-124254-g397c7c7524-win64-lgpl.zip"
$ffmpegArchiveUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-04-29-13-28/$ffmpegArchiveName"
$ffmpegArchiveSha256 = "42f9457901fcc1928834ded69f0fc4903bd16c9a41c185234a40490060bda9fb"

function Resolve-VenvExecutable {
  param(
    [Parameter(Mandatory = $true)]
    [string]$ScriptsDir,

    [Parameter(Mandatory = $true)]
    [string]$NamePattern,

    [Parameter(Mandatory = $true)]
    [string]$MissingMessage
  )

  $matches = Get-ChildItem -Path $ScriptsDir -Filter $NamePattern -ErrorAction SilentlyContinue | Sort-Object Name
  if (-not $matches -or $matches.Count -eq 0) {
    throw $MissingMessage
  }
  return $matches[0].FullName
}

function Resolve-SystemPython {
  $candidates = @()
  $pyLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
  if ($pyLauncher -and $pyLauncher.Source) {
    $candidates += $pyLauncher.Source
  }
  $pythonExe = Get-Command python.exe -ErrorAction SilentlyContinue
  if ($pythonExe -and $pythonExe.Source) {
    $candidates += $pythonExe.Source
  }

  foreach ($candidate in $candidates) {
    try {
      if ($candidate -like '*\WindowsApps\*') {
        continue
      }

      if ($candidate -match '\\py(?:thon)?(?:\.exe)?$') {
        & $candidate -3 -c "import sys" *> $null
        if ($LASTEXITCODE -eq 0) {
          return @{
            FilePath = $candidate
            Arguments = @('-3')
          }
        }
        continue
      }

      & $candidate -c "import sys" *> $null
      if ($LASTEXITCODE -eq 0) {
        return @{
          FilePath = $candidate
          Arguments = @()
        }
      }
    } catch {
      continue
    }
  }

  throw "No usable system Python was found. Install Python 3 or ensure py.exe is available."
}

function Invoke-Native {
  param(
    [Parameter(Mandatory = $true)]
    [string]$FilePath,

    [Parameter()]
    [string[]]$ArgumentList
  )

  & $FilePath @ArgumentList
  if ($LASTEXITCODE -ne 0) {
    throw ("Command failed with exit code {0}: {1} {2}" -f $LASTEXITCODE, $FilePath, ($ArgumentList -join " "))
  }
}

function Ensure-WindowsFfmpegRuntime {
  $ffmpegExe = Join-Path $ffmpegVendorDir "ffmpeg.exe"
  $ffprobeExe = Join-Path $ffmpegVendorDir "ffprobe.exe"
  if ((Test-Path -LiteralPath $ffmpegExe) -and (Test-Path -LiteralPath $ffprobeExe)) {
    return
  }

  $downloadRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mediamop-ffmpeg-" + [System.Guid]::NewGuid().ToString("N"))
  $archivePath = Join-Path $downloadRoot $ffmpegArchiveName
  $extractRoot = Join-Path $downloadRoot "extract"
  try {
    New-Item -ItemType Directory -Path $downloadRoot | Out-Null
    New-Item -ItemType Directory -Path $extractRoot | Out-Null
    Write-Host "Downloading Windows FFmpeg runtime..."
    Invoke-WebRequest -Uri $ffmpegArchiveUrl -OutFile $archivePath -UseBasicParsing
    $actualSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $ffmpegArchiveSha256) {
      throw "Downloaded FFmpeg archive hash mismatch. Expected $ffmpegArchiveSha256 but got $actualSha256."
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
    $binDir = Get-ChildItem -Path $extractRoot -Recurse -Directory |
      Where-Object {
        (Test-Path (Join-Path $_.FullName "ffmpeg.exe")) -and
        (Test-Path (Join-Path $_.FullName "ffprobe.exe"))
      } |
      Select-Object -First 1
    if (-not $binDir) {
      throw "Downloaded FFmpeg archive did not contain ffmpeg.exe and ffprobe.exe."
    }
    if (Test-Path $ffmpegVendorDir) {
      Remove-Item -LiteralPath $ffmpegVendorDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $ffmpegVendorDir | Out-Null
    foreach ($name in @("ffmpeg.exe", "ffprobe.exe")) {
      $src = Join-Path $binDir.FullName $name
      if (-not (Test-Path -LiteralPath $src)) {
        throw "Expected $name was not found in the downloaded FFmpeg archive at $src"
      }
      Copy-Item -LiteralPath $src -Destination (Join-Path $ffmpegVendorDir $name) -Force
    }
  } finally {
    if (Test-Path $downloadRoot) {
      Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

# ── Resolve version from backend pyproject.toml ──
$backendProjectVersion = ((Get-Content -Path (Join-Path $backendDir "pyproject.toml")) | Where-Object { $_ -match '^version = ' } | Select-Object -First 1).Split('"')[1]
$buildVersion = if ($env:MEDIAMOP_BUILD_VERSION) {
  $env:MEDIAMOP_BUILD_VERSION
} else {
  $backendProjectVersion
}
if ($buildVersion.StartsWith("v")) {
  $buildVersion = $buildVersion.Substring(1)
}
if ($buildVersion -ne $backendProjectVersion) {
  throw "MEDIAMOP_BUILD_VERSION '$buildVersion' does not match backend project version '$backendProjectVersion'."
}

# ── Python venv ──
if (-not (Test-Path $py)) {
  $systemPython = Resolve-SystemPython
  Push-Location $backendDir
  try {
    Invoke-Native -FilePath $systemPython.FilePath -ArgumentList @($systemPython.Arguments + @("-m", "venv", ".venv"))
  } finally {
    Pop-Location
  }
}

# ── Web build ──
if (-not $SkipWebBuild) {
  $webBuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mediamop-web-build-" + [System.Guid]::NewGuid().ToString("N"))
  $webBuildWebDir = Join-Path $webBuildRoot "apps\\web"
  $webBuildScriptsDir = Join-Path $webBuildRoot "scripts"
  try {
    New-Item -ItemType Directory -Path $webBuildWebDir | Out-Null
    New-Item -ItemType Directory -Path $webBuildScriptsDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $repoRoot "scripts\\dev-ports.json") -Destination (Join-Path $webBuildScriptsDir "dev-ports.json") -Force
    $copyArgs = @(
      $webDir,
      $webBuildWebDir,
      "/MIR",
      "/XD",
      "node_modules",
      "dist",
      ".vite",
      "tmp",
      "/XF",
      "*.log"
    )
    & robocopy @copyArgs | Out-Host
    if ($LASTEXITCODE -gt 7) {
      throw ("Command failed with exit code {0}: robocopy {1}" -f $LASTEXITCODE, ($copyArgs -join " "))
    }

    Push-Location $webBuildWebDir
    Invoke-Native -FilePath npm.cmd -ArgumentList @("ci")
    Invoke-Native -FilePath npm.cmd -ArgumentList @("run", "build")

    $sourceDist = Join-Path $webBuildWebDir "dist"
    $targetDist = Join-Path $webDir "dist"
    if (Test-Path $targetDist) {
      Remove-Item -LiteralPath $targetDist -Recurse -Force
    }
    Copy-Item -LiteralPath $sourceDist -Destination $targetDist -Recurse -Force
  } finally {
    if ((Get-Location).Path -eq $webBuildRoot) {
      Pop-Location
    }
    if (Test-Path $webBuildRoot) {
      Remove-Item -LiteralPath $webBuildRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

# ── Backend install + PyInstaller (server-only) ──
Push-Location $backendDir
try {
  Invoke-Native -FilePath $py -ArgumentList @("-m", "ensurepip", "--upgrade")
  $pip = Resolve-VenvExecutable -ScriptsDir $venvScriptsDir -NamePattern "pip*.exe" -MissingMessage "pip launcher was not created in the backend virtual environment."
  Invoke-Native -FilePath $py -ArgumentList @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-Native -FilePath $pip -ArgumentList @("install", "--upgrade", "--force-reinstall", "-e", ".")
  $installedBackendVersion = (& $py -c "import importlib.metadata as m; print(m.version('mediamop-backend'))").Trim()
  if (-not $installedBackendVersion) {
    throw "Could not resolve installed mediamop-backend version after editable install."
  }
  if ($installedBackendVersion -ne $backendProjectVersion) {
    throw "Installed mediamop-backend version '$installedBackendVersion' does not match backend project version '$backendProjectVersion'."
  }
  Invoke-Native -FilePath $pip -ArgumentList @("install", "pillow>=11.0.0", "pyinstaller>=6.12.0")
  $pyinstaller = Resolve-VenvExecutable -ScriptsDir $venvScriptsDir -NamePattern "pyinstaller*.exe" -MissingMessage "pyinstaller launcher was not installed in the backend virtual environment."
} finally {
  Pop-Location
}

# ── Clean dist ──
if (Test-Path $distRoot) {
  Remove-Item -LiteralPath $distRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $distRoot | Out-Null

# ── FFmpeg ──
if (Test-Path -LiteralPath $ffmpegVendorDir) {
  Write-Host "Cleaning stale FFmpeg vendor folder..."
  Remove-Item -LiteralPath $ffmpegVendorDir -Recurse -Force
}
Ensure-WindowsFfmpegRuntime

# ── PyInstaller: server-only ──
Push-Location $repoRoot
try {
  Invoke-Native -FilePath $py -ArgumentList @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $distRoot, "--workpath", (Join-Path $distRoot "build"), $serverSpecPath)
} finally {
  Pop-Location
}

$serverOutputDir = Join-Path $distRoot "MediaMopServer"
$serverExe = Join-Path $serverOutputDir "MediaMopServer.exe"
if (-not (Test-Path -LiteralPath $serverExe)) {
  throw "Expected packaged executable was not found: $serverExe"
}
$serverVersion = (& $serverExe --version).Trim()
if ($serverVersion -ne $buildVersion) {
  throw "Packaged MediaMopServer.exe reports version '$serverVersion' but expected build version is '$buildVersion'."
}

# ── .NET tray app publish ──
$trayPublishDir = Join-Path $distRoot "tray-publish"
if (-not $SkipDotnetPublish) {
  Write-Host "Publishing .NET tray app..."
  Invoke-Native -FilePath dotnet -ArgumentList @(
    "publish", $trayDir,
    "-c", "Release",
    "--self-contained",
    "-r", "win-x64",
    "-o", $trayPublishDir,
    "-p:Version=$buildVersion"
  )
}

# ── Assemble Velopack pack directory ──
$packDir = Join-Path $distRoot "pack"
if (Test-Path $packDir) {
  Remove-Item -LiteralPath $packDir -Recurse -Force
}
New-Item -ItemType Directory -Path $packDir | Out-Null

Write-Host "Assembling Velopack pack directory..."
Copy-Item -Path (Join-Path $trayPublishDir "*") -Destination $packDir -Recurse -Force

$serverDestDir = Join-Path $packDir "server"
New-Item -ItemType Directory -Path $serverDestDir | Out-Null
Copy-Item -Path (Join-Path $serverOutputDir "*") -Destination $serverDestDir -Recurse -Force

# ── vpk pack ──
Write-Host "Running vpk pack..."
$vpk = Get-Command vpk -ErrorAction SilentlyContinue
if (-not $vpk) {
  Write-Host "Installing Velopack CLI tool..."
  Invoke-Native -FilePath dotnet -ArgumentList @("tool", "install", "-g", "vpk")
  $vpk = Get-Command vpk -ErrorAction SilentlyContinue
  if (-not $vpk) {
    $dotnetToolsPath = Join-Path $env:USERPROFILE ".dotnet\\tools"
    $vpkPath = Join-Path $dotnetToolsPath "vpk.exe"
    if (-not (Test-Path $vpkPath)) {
      throw "vpk CLI was not found after install. Ensure dotnet tools path is on PATH."
    }
    $vpk = Get-Item $vpkPath
  }
}

$vpkExe = if ($vpk -is [System.Management.Automation.ApplicationInfo]) { $vpk.Source } else { $vpk.FullName }

Invoke-Native -FilePath $vpkExe -ArgumentList @(
  "pack",
  "--packId", "MediaMop",
  "--packVersion", $buildVersion,
  "--packDir", $packDir,
  "--mainExe", "MediaMop.exe",
  "--outputDir", $velopackOut,
  "--icon", (Join-Path $PSScriptRoot "assets\\mediamop-tray-icon.ico")
)

Write-Host ""
Write-Host "Velopack packaging output:"
Get-ChildItem -Path $velopackOut | Select-Object Name, Length
