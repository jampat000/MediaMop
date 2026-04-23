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
$py = Join-Path $backendDir ".venv\\Scripts\\python.exe"
$pip = Join-Path $backendDir ".venv\\Scripts\\pip.exe"
$pyinstaller = Join-Path $backendDir ".venv\\Scripts\\pyinstaller.exe"
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
  Push-Location $backendDir
  try {
    Invoke-Native -FilePath python -ArgumentList @("-m", "venv", ".venv")
  } finally {
    Pop-Location
  }
}

if (-not $SkipWebBuild) {
  Push-Location $webDir
  try {
    Invoke-Native -FilePath npm.cmd -ArgumentList @("ci")
    Invoke-Native -FilePath npm.cmd -ArgumentList @("run", "build")
  } finally {
    Pop-Location
  }
}

Push-Location $backendDir
try {
  Invoke-Native -FilePath $py -ArgumentList @("-m", "pip", "install", "--upgrade", "pip")
  Invoke-Native -FilePath $py -ArgumentList @("-m", "pip", "install", "-e", ".")
  Invoke-Native -FilePath $py -ArgumentList @("-m", "pip", "install", "pillow>=11.0.0", "pyinstaller>=6.12.0", "pystray>=0.19.5")
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
