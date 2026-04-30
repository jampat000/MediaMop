param(
  [switch]$SkipWebBuild,
  [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$backendDir = Join-Path $repoRoot "apps\\backend"
$webDir = Join-Path $repoRoot "apps\\web"
$specPath = Join-Path $PSScriptRoot "mediamop-tray.spec"
$distRoot = Join-Path $repoRoot "dist\\windows"
$ffmpegVendorDir = Join-Path $PSScriptRoot "vendor\\ffmpeg"
$winswVendorDir = Join-Path $PSScriptRoot "vendor\\winsw"
$venvScriptsDir = Join-Path $backendDir ".venv\\Scripts"
$py = Join-Path $venvScriptsDir "python.exe"
$ffmpegArchiveName = "ffmpeg-N-124254-g397c7c7524-win64-lgpl.zip"
$ffmpegArchiveUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/autobuild-2026-04-29-13-28/$ffmpegArchiveName"
$ffmpegArchiveSha256 = "42f9457901fcc1928834ded69f0fc4903bd16c9a41c185234a40490060bda9fb"
$winswArchiveName = "WinSW-x64.exe"
$winswArchiveUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
$winswArchiveSha256 = "05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da"

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

function Resolve-IsccPath {
  $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
  $programFiles = [Environment]::GetEnvironmentVariable('ProgramFiles')
  $rawCandidates = @(
    $(if ($programFilesX86) { Join-Path $programFilesX86 'Inno Setup 6\\ISCC.exe' }),
    $(if ($programFiles) { Join-Path $programFiles 'Inno Setup 6\\ISCC.exe' })
  )
  $candidates = @($rawCandidates | Where-Object { $_ -and (Test-Path $_) })
  if ($candidates.Count -gt 0) {
    return [string](Resolve-Path -LiteralPath $candidates[0]).Path
  }
  return $null
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
    Copy-Item -Path (Join-Path $binDir.FullName "*") -Destination $ffmpegVendorDir -Recurse -Force
  } finally {
    if (Test-Path $downloadRoot) {
      Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

function Ensure-WindowsServiceWrapper {
  $winswExe = Join-Path $winswVendorDir "WinSW-x64.exe"
  if (Test-Path -LiteralPath $winswExe) {
    return
  }

  $downloadRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("mediamop-winsw-" + [System.Guid]::NewGuid().ToString("N"))
  $archivePath = Join-Path $downloadRoot $winswArchiveName
  try {
    New-Item -ItemType Directory -Path $downloadRoot | Out-Null
    Write-Host "Downloading WinSW runtime..."
    Invoke-WebRequest -Uri $winswArchiveUrl -OutFile $archivePath -UseBasicParsing
    $actualSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $winswArchiveSha256) {
      throw "Downloaded WinSW binary hash mismatch. Expected $winswArchiveSha256 but got $actualSha256."
    }
    if (Test-Path $winswVendorDir) {
      Remove-Item -LiteralPath $winswVendorDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $winswVendorDir | Out-Null
    Copy-Item -LiteralPath $archivePath -Destination $winswExe -Force
  } finally {
    if (Test-Path $downloadRoot) {
      Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

$iscc = Resolve-IsccPath
$buildVersion = if ($env:MEDIAMOP_BUILD_VERSION) {
  $env:MEDIAMOP_BUILD_VERSION
} else {
  ((Get-Content -Path (Join-Path $backendDir "pyproject.toml")) | Where-Object { $_ -match '^version = ' } | Select-Object -First 1).Split('"')[1]
}

if (-not (Test-Path $py)) {
  $systemPython = Resolve-SystemPython
  Push-Location $backendDir
  try {
    Invoke-Native -FilePath $systemPython.FilePath -ArgumentList @($systemPython.Arguments + @("-m", "venv", ".venv"))
  } finally {
    Pop-Location
  }
}

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

Push-Location $backendDir
try {
  Invoke-Native -FilePath $py -ArgumentList @("-m", "ensurepip", "--upgrade")
  $pip = Resolve-VenvExecutable -ScriptsDir $venvScriptsDir -NamePattern "pip*.exe" -MissingMessage "pip launcher was not created in the backend virtual environment."
  Invoke-Native -FilePath $py -ArgumentList @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-Native -FilePath $pip -ArgumentList @("install", "-e", ".")
  Invoke-Native -FilePath $pip -ArgumentList @("install", "pillow>=11.0.0", "pyinstaller>=6.12.0", "pystray>=0.19.5")
  $pyinstaller = Resolve-VenvExecutable -ScriptsDir $venvScriptsDir -NamePattern "pyinstaller*.exe" -MissingMessage "pyinstaller launcher was not installed in the backend virtual environment."
} finally {
  Pop-Location
}

if (Test-Path $distRoot) {
  Remove-Item -LiteralPath $distRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $distRoot | Out-Null

Ensure-WindowsFfmpegRuntime
Ensure-WindowsServiceWrapper

Push-Location $repoRoot
try {
  Invoke-Native -FilePath $pyinstaller -ArgumentList @("--noconfirm", "--clean", "--distpath", $distRoot, "--workpath", (Join-Path $distRoot "build"), $specPath)
} finally {
  Pop-Location
}

if (-not $SkipInstaller) {
  if (-not $iscc) {
    throw "Inno Setup 6 was not found. Install it or rerun with -SkipInstaller."
  }
  Invoke-Native -FilePath ([string]$iscc) -ArgumentList @("/DRepoRoot=$repoRoot", "/DOutputRoot=$distRoot", "/DAppVersion=$buildVersion", (Join-Path $PSScriptRoot "MediaMop.iss"))
}

Write-Host "Windows packaging output:"
Get-ChildItem -Path $distRoot -Recurse | Select-Object FullName
