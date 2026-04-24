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
$venvScriptsDir = Join-Path $backendDir ".venv\\Scripts"
$py = Join-Path $venvScriptsDir "python.exe"

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
