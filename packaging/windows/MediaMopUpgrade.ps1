$ErrorActionPreference = "Stop"

$upgradeRoot = Join-Path $env:ProgramData "MediaMop\upgrades"
$logPath = Join-Path $upgradeRoot "upgrade-task.log"
$setupLogPath = Join-Path $upgradeRoot "installer-latest.log"
$releaseApi = "https://api.github.com/repos/jampat000/MediaMop/releases/latest"

function Write-MediaMopUpgradeLog([string]$message) {
  New-Item -ItemType Directory -Path $upgradeRoot -Force | Out-Null
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -LiteralPath $logPath -Value "[$stamp] $message"
}

try {
  Write-MediaMopUpgradeLog "Updater task started."

  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $release = Invoke-RestMethod -Uri $releaseApi -Headers @{ "User-Agent" = "MediaMop Windows Updater" } -TimeoutSec 30
  $tag = [string]$release.tag_name
  if ([string]::IsNullOrWhiteSpace($tag)) {
    throw "GitHub release response did not include a tag name."
  }

  $asset = $release.assets | Where-Object { $_.name -eq "MediaMopSetup.exe" } | Select-Object -First 1
  if (-not $asset -or [string]::IsNullOrWhiteSpace([string]$asset.browser_download_url)) {
    throw "Latest MediaMop release does not include MediaMopSetup.exe."
  }

  $version = $tag.TrimStart("v")
  $installerPath = Join-Path $upgradeRoot ("MediaMopSetup-" + $version + ".exe")
  Write-MediaMopUpgradeLog ("Downloading MediaMop " + $version + " installer.")
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $installerPath -UseBasicParsing -TimeoutSec 120

  $installerArgs = @(
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/CLOSEAPPLICATIONS",
    "/RESTARTAPPLICATIONS",
    "/LOG=`"$setupLogPath`""
  )
  Write-MediaMopUpgradeLog ("Starting installer: " + $installerPath)
  $proc = Start-Process -FilePath $installerPath -ArgumentList $installerArgs -Wait -PassThru
  Write-MediaMopUpgradeLog ("Installer exited with code " + $proc.ExitCode + ".")
  if ($proc.ExitCode -ne 0) {
    throw ("Installer failed with exit code " + $proc.ExitCode + ".")
  }

  $exe = Join-Path $env:ProgramFiles "MediaMop\MediaMop.exe"
  if (Test-Path -LiteralPath $exe) {
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe)
    Write-MediaMopUpgradeLog "MediaMop restart requested."
  } else {
    Write-MediaMopUpgradeLog ("MediaMop executable was not found after upgrade: " + $exe)
  }

  Write-MediaMopUpgradeLog "Updater task completed."
} catch {
  Write-MediaMopUpgradeLog ("Updater task failed: " + $_.Exception.Message)
  throw
}
