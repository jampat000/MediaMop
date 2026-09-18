param(
  [switch]$SkipWebBuild,
  [switch]$SkipDotnetPublish,
  [switch]$SkipSmoke
)

$ErrorActionPreference = "Stop"

# Builds the Weir Windows package (Velopack): the web app, the .NET server
# (apps/server/src/Weir.Host, self-contained single-file win-x64), the tray app (apps/tray/Weir.Tray)
# and a checksum-verified ffmpeg and mkvmerge, packed as packId Weir with Weir.exe (the tray) as the
# main exe.
# Output: dist\windows\releases\{Weir-win-Setup.exe, Weir-win-Portable.zip, *.nupkg, RELEASES, ...}.
#
# Layout of the pack directory (dist\windows\pack), which is what gets installed:
#   Weir.exe                          the tray app; it starts and watches the server
#   server\WeirServer.exe             the server (Weir.Host publishes as Weir.exe, renamed so it does
#                                     not collide with the tray's own Weir.exe; the tray's
#                                     FindServerExeDirectory looks for this name)
#   server\web-dist\                  the built web app (the tray sets WEIR_WEB_DIST to it)
#   server\bin\ffmpeg\{ffmpeg,ffprobe}.exe
#                                     found by the server's MediaToolResolver as <app>\bin\ffmpeg
#   server\bin\mkvtoolnix\mkvmerge.exe
#                                     found by MediaToolResolver.ResolveMkvmerge as
#                                     <app>\bin\mkvtoolnix (#548)
#
# scripts/smoke-windows-package.ps1 then proves the assembled server works end to end.

# ── Phase timing ──
$script:PhaseTimings = [ordered]@{}
$script:PhaseStopwatch = $null
$script:PhaseName = $null

function Start-BuildPhase {
  param([Parameter(Mandatory)][string]$Name)
  Stop-BuildPhase
  $script:PhaseName = $Name
  $script:PhaseStopwatch = [System.Diagnostics.Stopwatch]::StartNew()
  Write-Host "--- $Name ---"
}

function Stop-BuildPhase {
  if ($null -eq $script:PhaseStopwatch) { return }
  $script:PhaseStopwatch.Stop()
  $seconds = [math]::Round($script:PhaseStopwatch.Elapsed.TotalSeconds, 1)
  $script:PhaseTimings[$script:PhaseName] = $seconds
  Write-Host ("--- {0}: {1}s ---" -f $script:PhaseName, $seconds)
  $script:PhaseStopwatch = $null
  $script:PhaseName = $null
}

function Write-BuildPhaseSummary {
  Stop-BuildPhase
  if ($script:PhaseTimings.Count -eq 0) { return }
  $total = ($script:PhaseTimings.Values | Measure-Object -Sum).Sum
  Write-Host ""
  Write-Host "=== Windows .NET package build timings ==="
  foreach ($entry in $script:PhaseTimings.GetEnumerator()) {
    $share = if ($total -gt 0) { [math]::Round(100 * $entry.Value / $total) } else { 0 }
    Write-Host ("  {0,-38} {1,7}s  {2,3}%" -f $entry.Key, $entry.Value, $share)
  }
  Write-Host ("  {0,-38} {1,7}s" -f "TOTAL", [math]::Round($total, 1))
  if ($env:GITHUB_ACTIONS -eq "true") {
    $parts = $script:PhaseTimings.GetEnumerator() | ForEach-Object { "$($_.Key) $($_.Value)s" }
    Write-Host ("::notice title=Windows .NET package build::" + ($parts -join ", "))
  }
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\..")).Path
$serverProjectDir = Join-Path $repoRoot "apps\\server\\src\\Weir.Host"
$webDir = Join-Path $repoRoot "apps\\web"
$trayDir = Join-Path $repoRoot "apps\\tray\\Weir.Tray"
$distRoot = Join-Path $repoRoot "dist\\windows"
$velopackOut = Join-Path $distRoot "releases"
$trayPublishDir = Join-Path $distRoot "tray-publish"
$serverPublishDir = Join-Path $distRoot "server-publish"
# Ignored by version control and reused between builds: Ensure-WindowsFfmpegRuntime downloads again
# only when the vendored copy no longer matches the upstream checksum (CI caches this folder too).
$ffmpegVendorDir = Join-Path $PSScriptRoot "vendor\\ffmpeg"
$ffmpegArchiveName = "ffmpeg-master-latest-win64-lgpl.zip"
$ffmpegArchiveUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/$ffmpegArchiveName"
$ffmpegChecksumsUrl = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/checksums.sha256"
# #548: MKVToolNix, for the mkvmerge writer (Weir.Infrastructure.Media.MkvmergeRemuxWriter). Vendored
# and cached exactly like ffmpeg above, with one deliberate difference: the version is *pinned* here
# rather than tracked from a "latest" tag. BtbN republishes its `latest` release continuously and
# publishes a checksums.sha256 next to it, so ffmpeg can be verified against whatever upstream says
# today; MKVToolNix publishes immutable per-version directories instead, and the tool that writes the
# user's Matroska output is not something that should change underneath a Weir release without
# somebody choosing it. Bumping means editing both lines below together — the checksum is the one
# upstream publishes at
# https://mkvtoolnix.download/windows/releases/<version>/mkvtoolnix-64-bit-<version>.zip.sha256
# (also listed in that directory's sha256sums.txt). v102.0 is the current stable, released
# 2026-09-14. Note the #503 trial (docs/trials/503-mkvmerge-vs-ffmpeg.md) measured v100.0; Weir uses
# only mkvmerge's long-stable CLI surface (`-o`, `--identification-format json`, per-track
# selection — see Weir.Core.Media.MkvmergeCommands), so the pin is not tied to the trial's build.
$mkvtoolnixVersion = "102.0"
$mkvtoolnixArchiveSha256 = "c02e918900f6d945d9307b426237e456378b79a200589ac6928de39064409a44"
$mkvtoolnixVendorDir = Join-Path $PSScriptRoot "vendor\\mkvtoolnix"
$mkvtoolnixArchiveName = "mkvtoolnix-64-bit-$mkvtoolnixVersion.zip"
$mkvtoolnixArchiveUrl = "https://mkvtoolnix.download/windows/releases/$mkvtoolnixVersion/$mkvtoolnixArchiveName"

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

function Get-ExpectedFfmpegSha256 {
  $checksumsPath = Join-Path ([System.IO.Path]::GetTempPath()) ("weir-ffmpeg-checksums-" + [System.Guid]::NewGuid().ToString("N") + ".sha256")
  try {
    Invoke-WebRequest -Uri $ffmpegChecksumsUrl -OutFile $checksumsPath -UseBasicParsing
    $checksumsText = Get-Content -LiteralPath $checksumsPath -Raw
    $checksumPattern = "(?im)^([a-f0-9]{64})\s+\*?$([regex]::Escape($ffmpegArchiveName))\s*$"
    $checksumMatch = [regex]::Match($checksumsText, $checksumPattern)
    if (-not $checksumMatch.Success) {
      throw "FFmpeg checksum entry for '$ffmpegArchiveName' was not found in checksums.sha256."
    }
    return $checksumMatch.Groups[1].Value.ToLowerInvariant()
  } finally {
    if (Test-Path -LiteralPath $checksumsPath) {
      Remove-Item -LiteralPath $checksumsPath -Force -ErrorAction SilentlyContinue
    }
  }
}

function Ensure-WindowsFfmpegRuntime {
  $ffmpegExe = Join-Path $ffmpegVendorDir "ffmpeg.exe"
  $ffprobeExe = Join-Path $ffmpegVendorDir "ffprobe.exe"
  $stampPath = Join-Path $ffmpegVendorDir ".ffmpeg-archive.sha256"

  Write-Host "Resolving Windows FFmpeg checksum..."
  $expectedSha256 = Get-ExpectedFfmpegSha256

  if ((Test-Path -LiteralPath $ffmpegExe) -and
      (Test-Path -LiteralPath $ffprobeExe) -and
      (Test-Path -LiteralPath $stampPath)) {
    $vendoredSha256 = (Get-Content -LiteralPath $stampPath -Raw).Trim().ToLowerInvariant()
    if ($vendoredSha256 -eq $expectedSha256) {
      Write-Host "Vendored FFmpeg already matches upstream ($expectedSha256); skipping download."
      return
    }
    Write-Host "Vendored FFmpeg is stale (have $vendoredSha256, want $expectedSha256); refreshing."
  }

  $downloadRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("weir-ffmpeg-" + [System.Guid]::NewGuid().ToString("N"))
  $archivePath = Join-Path $downloadRoot $ffmpegArchiveName
  $extractRoot = Join-Path $downloadRoot "extract"
  try {
    New-Item -ItemType Directory -Path $downloadRoot | Out-Null
    New-Item -ItemType Directory -Path $extractRoot | Out-Null
    Write-Host "Downloading Windows FFmpeg runtime..."
    Invoke-WebRequest -Uri $ffmpegArchiveUrl -OutFile $archivePath -UseBasicParsing
    $actualSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $expectedSha256) {
      throw "Downloaded FFmpeg archive hash mismatch. Expected $expectedSha256 but got $actualSha256."
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
    Set-Content -LiteralPath (Join-Path $ffmpegVendorDir ".ffmpeg-archive.sha256") -Value $expectedSha256 -Encoding ascii
  } finally {
    if (Test-Path $downloadRoot) {
      Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

function Ensure-WindowsMkvtoolnixRuntime {
  # #548: the same download / verify / cache shape as Ensure-WindowsFfmpegRuntime, against a pinned
  # version and checksum instead of an upstream checksums file. Only mkvmerge.exe is vendored: the
  # portable archive is ~85 MB because it carries the Qt GUI, mkvinfo, mkvextract, mkvpropedit, the
  # docs and 40-odd locales, none of which Weir ever runs. MKVToolNix's Windows CLI binaries are
  # statically linked — no sibling DLLs, no data directory — verified by copying mkvmerge.exe alone
  # out of an install and running `--version` and an `--identification-format json` identify from the
  # copy, both of which succeeded. That keeps the package's growth to the ~23 MB of mkvmerge itself
  # rather than the ~120 MB the whole archive would expand to.
  $mkvmergeExe = Join-Path $mkvtoolnixVendorDir "mkvmerge.exe"
  $stampPath = Join-Path $mkvtoolnixVendorDir ".mkvtoolnix-archive.sha256"

  if ((Test-Path -LiteralPath $mkvmergeExe) -and (Test-Path -LiteralPath $stampPath)) {
    $vendoredSha256 = (Get-Content -LiteralPath $stampPath -Raw).Trim().ToLowerInvariant()
    if ($vendoredSha256 -eq $mkvtoolnixArchiveSha256) {
      Write-Host "Vendored MKVToolNix already matches the pin ($mkvtoolnixVersion, $mkvtoolnixArchiveSha256); skipping download."
      return
    }
    Write-Host "Vendored MKVToolNix is stale (have $vendoredSha256, want $mkvtoolnixArchiveSha256); refreshing."
  }

  $downloadRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("weir-mkvtoolnix-" + [System.Guid]::NewGuid().ToString("N"))
  $archivePath = Join-Path $downloadRoot $mkvtoolnixArchiveName
  $extractRoot = Join-Path $downloadRoot "extract"
  try {
    New-Item -ItemType Directory -Path $downloadRoot | Out-Null
    New-Item -ItemType Directory -Path $extractRoot | Out-Null
    Write-Host "Downloading MKVToolNix $mkvtoolnixVersion..."
    Invoke-WebRequest -Uri $mkvtoolnixArchiveUrl -OutFile $archivePath -UseBasicParsing
    $actualSha256 = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualSha256 -ne $mkvtoolnixArchiveSha256) {
      throw "Downloaded MKVToolNix archive hash mismatch. Expected $mkvtoolnixArchiveSha256 but got $actualSha256."
    }
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractRoot -Force
    # The archive nests everything under a "mkvtoolnix\" folder, but searching for the directory that
    # actually holds mkvmerge.exe (rather than hard-coding that name) means a future layout change
    # fails loudly on the throw below instead of silently shipping a package without the tool.
    $binDir = Get-ChildItem -Path $extractRoot -Recurse -Directory |
      Where-Object { Test-Path (Join-Path $_.FullName "mkvmerge.exe") } |
      Select-Object -First 1
    if (-not $binDir) {
      throw "Downloaded MKVToolNix archive did not contain mkvmerge.exe."
    }
    if (Test-Path $mkvtoolnixVendorDir) {
      Remove-Item -LiteralPath $mkvtoolnixVendorDir -Recurse -Force
    }
    New-Item -ItemType Directory -Path $mkvtoolnixVendorDir | Out-Null
    Copy-Item -LiteralPath (Join-Path $binDir.FullName "mkvmerge.exe") -Destination $mkvmergeExe -Force
    Set-Content -LiteralPath $stampPath -Value $mkvtoolnixArchiveSha256 -Encoding ascii
  } finally {
    if (Test-Path $downloadRoot) {
      Remove-Item -LiteralPath $downloadRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

# ── Resolve version from apps/server/Directory.Build.props (WeirVersion) ──
# The one product version; the server's own assembly version is stamped from the same line.
$propsPath = Join-Path $repoRoot "apps\\server\\Directory.Build.props"
$propsMatch = [regex]::Match((Get-Content -LiteralPath $propsPath -Raw), '<WeirVersion>([^<]+)</WeirVersion>')
if (-not $propsMatch.Success) {
  throw "WeirVersion was not found in $propsPath."
}
$projectVersion = $propsMatch.Groups[1].Value.Trim()
$buildVersion = if ($env:WEIR_BUILD_VERSION) {
  $env:WEIR_BUILD_VERSION
} else {
  $projectVersion
}
if ($buildVersion.StartsWith("v")) {
  $buildVersion = $buildVersion.Substring(1)
}
if ($buildVersion -ne $projectVersion) {
  throw "WEIR_BUILD_VERSION '$buildVersion' does not match WeirVersion '$projectVersion' in apps/server/Directory.Build.props."
}

# ── Web build ──
Start-BuildPhase "Web build"
if (-not $SkipWebBuild) {
  $webBuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("weir-web-build-" + [System.Guid]::NewGuid().ToString("N"))
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
$webDistDir = Join-Path $webDir "dist"
if (-not (Test-Path -LiteralPath (Join-Path $webDistDir "index.html"))) {
  throw "Expected a built web app at $webDistDir (index.html missing). Re-run without -SkipWebBuild."
}

# ── Clean dist ──
if ($SkipDotnetPublish) {
  if (-not (Test-Path -LiteralPath $trayPublishDir) -or -not (Test-Path -LiteralPath $serverPublishDir)) {
    throw "-SkipDotnetPublish requires existing publish output at $trayPublishDir and $serverPublishDir."
  }
  Get-ChildItem -LiteralPath $distRoot -Force |
    Where-Object { $_.Name -notin @("tray-publish", "server-publish") } |
    Remove-Item -Recurse -Force
} elseif (Test-Path $distRoot) {
  Remove-Item -LiteralPath $distRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $distRoot -Force | Out-Null

# ── FFmpeg ──
Start-BuildPhase "FFmpeg download + vendor"
Ensure-WindowsFfmpegRuntime

# ── MKVToolNix (#548) ──
Start-BuildPhase "MKVToolNix download + vendor"
Ensure-WindowsMkvtoolnixRuntime

# ── .NET server publish (self-contained single-file, via the checked-in win-x64 publish
#    profile — apps/server/src/Weir.Host/Properties/PublishProfiles/win-x64.pubxml — the same
#    way apps/server/README.md documents, NOT by repeating --self-contained/-p:PublishSingleFile
#    etc. as separate command-line switches). That distinction matters: a command-line
#    -p:PublishSingleFile=true is a *global* MSBuild property, applied to every project in the
#    build graph including Weir.Infrastructure, which makes its build fail with error IL3000
#    ("Assembly.Location always returns an empty string in a single-file app") on the
#    Assembly.Location check in Runtime/SystemServices.cs (DetectInstallType) — code that reads
#    that empty string ON PURPOSE, to detect single-file mode. Weir.Host.csproj's own
#    RID-conditioned PropertyGroup (and the .pubxml profiles built on top of it) set the same
#    properties, but scoped to the Weir.Host project only, which is what the analyzer actually
#    expects; publishing this way never triggers IL3000. Verified locally (see
#    apps/server/README.md) — do not "simplify" this back to explicit -p: flags.
Start-BuildPhase ".NET server publish"
if (-not $SkipDotnetPublish) {
  Write-Host "Publishing .NET server..."
  if (Test-Path $serverPublishDir) {
    Remove-Item -LiteralPath $serverPublishDir -Recurse -Force
  }
  Invoke-Native -FilePath dotnet -ArgumentList @(
    "publish", $serverProjectDir,
    "-p:PublishProfile=win-x64",
    "-p:Version=$buildVersion",
    "-p:PublishDir=$serverPublishDir\"
  )
}
$publishedServerExe = Join-Path $serverPublishDir "Weir.exe"
if (-not (Test-Path -LiteralPath $publishedServerExe)) {
  throw "Expected published .NET server executable was not found: $publishedServerExe"
}
$serverVersion = (& $publishedServerExe --version).Trim()
if ($serverVersion -ne $buildVersion) {
  throw "Published Weir.exe (server) reports version '$serverVersion' but expected build version is '$buildVersion'."
}

# ── Smoke: the raw published server exe, before packing (temp WEIR_HOME + the built web dist) ──
if (-not $SkipSmoke) {
  Start-BuildPhase "Server publish smoke"
  $smokeHome = Join-Path ([System.IO.Path]::GetTempPath()) ("weir-dotnet-server-smoke-" + [System.Guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Path $smokeHome | Out-Null
  $smokePort = 8799
  $smokeProc = $null
  $oldHome = $env:WEIR_HOME
  $oldWebDist = $env:WEIR_WEB_DIST
  $oldSecret = $env:WEIR_SESSION_SECRET
  $oldCookieSecure = $env:WEIR_SESSION_COOKIE_SECURE
  try {
    $env:WEIR_HOME = $smokeHome
    $env:WEIR_WEB_DIST = $webDistDir
    $env:WEIR_SESSION_SECRET = "package-build-smoke-session-secret-32chars-min"
    $env:WEIR_SESSION_COOKIE_SECURE = "false"
    $smokeProc = Start-Process -FilePath $publishedServerExe `
      -ArgumentList @("--port", [string]$smokePort) `
      -WorkingDirectory $serverPublishDir `
      -RedirectStandardOutput (Join-Path $smokeHome "server.stdout.log") `
      -RedirectStandardError (Join-Path $smokeHome "server.stderr.log") `
      -WindowStyle Hidden `
      -PassThru
    $healthUrl = "http://127.0.0.1:$smokePort/health"
    $deadline = (Get-Date).AddSeconds(30)
    $healthy = $false
    do {
      if ($smokeProc.HasExited) {
        throw "Published .NET server exited early with code $($smokeProc.ExitCode) during the publish smoke test."
      }
      try {
        $response = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 2
        Write-Host ("Smoke /health responded: {0}" -f ($response | ConvertTo-Json -Compress))
        $healthy = $true
        break
      } catch {
        Start-Sleep -Milliseconds 250
      }
    } while ((Get-Date) -lt $deadline)
    if (-not $healthy) {
      throw "Published .NET server did not answer $healthUrl within 30s."
    }
    Write-Host "Server publish smoke passed: $healthUrl"
  } finally {
    if ($smokeProc -and -not $smokeProc.HasExited) {
      Stop-Process -Id $smokeProc.Id -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $oldHome) { $env:WEIR_HOME = $oldHome } else { Remove-Item Env:\WEIR_HOME -ErrorAction SilentlyContinue }
    if ($null -ne $oldWebDist) { $env:WEIR_WEB_DIST = $oldWebDist } else { Remove-Item Env:\WEIR_WEB_DIST -ErrorAction SilentlyContinue }
    if ($null -ne $oldSecret) { $env:WEIR_SESSION_SECRET = $oldSecret } else { Remove-Item Env:\WEIR_SESSION_SECRET -ErrorAction SilentlyContinue }
    if ($null -ne $oldCookieSecure) { $env:WEIR_SESSION_COOKIE_SECURE = $oldCookieSecure } else { Remove-Item Env:\WEIR_SESSION_COOKIE_SECURE -ErrorAction SilentlyContinue }
    Remove-Item -LiteralPath $smokeHome -Recurse -Force -ErrorAction SilentlyContinue
  }
}

# ── .NET tray app publish ──
Start-BuildPhase ".NET tray publish"
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
Start-BuildPhase "Assemble pack dir"
$packDir = Join-Path $distRoot "pack"
if (Test-Path $packDir) {
  Remove-Item -LiteralPath $packDir -Recurse -Force
}
New-Item -ItemType Directory -Path $packDir | Out-Null

Write-Host "Assembling Velopack pack directory..."
Copy-Item -Path (Join-Path $trayPublishDir "*") -Destination $packDir -Recurse -Force

# The tray app looks for "server\WeirServer.exe" (Program.cs, FindServerExeDirectory). Weir.Host's own
# AssemblyName is "Weir" (it would collide with the tray's own Weir.exe at the pack root if copied under
# its published name), so the publish output is renamed on the way in.
$serverDestDir = Join-Path $packDir "server"
New-Item -ItemType Directory -Path $serverDestDir | Out-Null
Copy-Item -Path (Join-Path $serverPublishDir "*") -Destination $serverDestDir -Recurse -Force
Move-Item -LiteralPath (Join-Path $serverDestDir "Weir.exe") -Destination (Join-Path $serverDestDir "WeirServer.exe") -Force
$serverPdb = Join-Path $serverDestDir "Weir.pdb"
if (Test-Path -LiteralPath $serverPdb) {
  # Not expected (Directory.Build.props sets DebugType=embedded), but if a future change
  # reintroduces a companion .pdb, keep its name aligned with the renamed executable.
  Move-Item -LiteralPath $serverPdb -Destination (Join-Path $serverDestDir "WeirServer.pdb") -Force
}

# Falls back to "server\web-dist" when "server\_internal\web-dist" is absent (Program.cs,
# PrepareEnvironment) — always true here, since a .NET single-file publish has no "_internal".
Copy-Item -Path $webDistDir -Destination (Join-Path $serverDestDir "web-dist") -Recurse -Force

# Matches the <packaged-app-dir>\bin\ffmpeg candidate in
# apps/server/src/Weir.Core/Media/MediaToolLocations.cs.
$serverFfmpegDir = Join-Path $serverDestDir "bin\\ffmpeg"
New-Item -ItemType Directory -Path $serverFfmpegDir -Force | Out-Null
Copy-Item -Path (Join-Path $ffmpegVendorDir "ffmpeg.exe") -Destination $serverFfmpegDir -Force
Copy-Item -Path (Join-Path $ffmpegVendorDir "ffprobe.exe") -Destination $serverFfmpegDir -Force

# #548: matches the <packaged-app-dir>\bin\mkvtoolnix candidate in
# MediaToolLocations.MkvtoolnixCandidateDirectories (MkvtoolnixBundleDirectory). Until this landed,
# MediaToolResolver.ResolveMkvmerge always returned null in a packaged install, so the per-library
# writer setting's "best" default (RemuxWriterChoice) silently fell through to ffmpeg for every
# write and the mkvmerge writer shipped inert.
$serverMkvtoolnixDir = Join-Path $serverDestDir "bin\\mkvtoolnix"
New-Item -ItemType Directory -Path $serverMkvtoolnixDir -Force | Out-Null
Copy-Item -Path (Join-Path $mkvtoolnixVendorDir "mkvmerge.exe") -Destination $serverMkvtoolnixDir -Force

# ── vpk pack (packId Weir, mainExe Weir.exe: the install identity every release keeps) ──
Start-BuildPhase "vpk pack"
Write-Host "Running vpk pack..."
$trayProjectPath = Join-Path $trayDir "Weir.Tray.csproj"
[xml]$trayProject = Get-Content -LiteralPath $trayProjectPath -Raw
$velopackReference = @($trayProject.Project.ItemGroup.PackageReference) |
  Where-Object { $_.Include -eq "Velopack" } |
  Select-Object -First 1
$velopackCliVersion = [string]$velopackReference.Version
if (-not $velopackCliVersion) {
  throw "Velopack package version was not found in $trayProjectPath."
}

$vpkListLine = @(Invoke-Native -FilePath dotnet -ArgumentList @("tool", "list", "-g", "vpk")) |
  Where-Object { $_ -match "^\s*vpk\s+" } |
  Select-Object -First 1
$installedVpkVersion = if ($vpkListLine) { ($vpkListLine.Trim() -split "\s+")[1] } else { $null }
if (-not $installedVpkVersion) {
  Write-Host "Installing Velopack CLI $velopackCliVersion..."
  Invoke-Native -FilePath dotnet -ArgumentList @("tool", "install", "-g", "vpk", "--version", $velopackCliVersion)
} elseif ($installedVpkVersion -ne $velopackCliVersion) {
  Write-Host "Updating Velopack CLI from $installedVpkVersion to $velopackCliVersion..."
  Invoke-Native -FilePath dotnet -ArgumentList @("tool", "update", "-g", "vpk", "--version", $velopackCliVersion)
}

$vpkExe = Join-Path (Join-Path $env:USERPROFILE ".dotnet") "tools\vpk.exe"
if (-not (Test-Path -LiteralPath $vpkExe)) {
  throw "vpk CLI was not found after install. Ensure the .NET global tools directory is available."
}

Invoke-Native -FilePath $vpkExe -ArgumentList @(
  "pack",
  "--packId", "Weir",
  "--packVersion", $buildVersion,
  "--packDir", $packDir,
  "--mainExe", "Weir.exe",
  "--outputDir", $velopackOut,
  "--icon", (Join-Path $PSScriptRoot "assets\\weir-tray-icon.ico")
)

Write-Host ""
Write-Host "Velopack packaging output:"
Get-ChildItem -Path $velopackOut | Select-Object Name, Length

Write-BuildPhaseSummary
