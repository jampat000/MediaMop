# Runs MediaMop Docker validation on GitHub-hosted runners instead of requiring
# Docker Desktop on this workstation.
param(
    [string] $Ref,
    [string] $Workflow = "ci.yml",
    [switch] $NoWatch
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    if (-not $Ref -or -not $Ref.Trim()) {
        $Ref = (& git rev-parse --abbrev-ref HEAD).Trim()
        if (-not $Ref -or $Ref -eq "HEAD") {
            $Ref = (& git rev-parse HEAD).Trim()
        }
    }

    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) {
        Write-Error "GitHub CLI is required. Install gh or use GitHub Actions in the browser."
    }

    & gh auth status | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "GitHub CLI is not authenticated. Run: gh auth login"
    }

    $repo = (& gh repo view --json nameWithOwner --jq ".nameWithOwner").Trim()
    $startedAfter = (Get-Date).ToUniversalTime().AddSeconds(-10)

    Write-Host "Triggering remote Docker validation via GitHub Actions." -ForegroundColor Cyan
    Write-Host "Repository: $repo"
    Write-Host "Workflow:   $Workflow"
    Write-Host "Ref:        $Ref"

    & gh workflow run $Workflow --ref $Ref
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    $run = $null
    for ($i = 0; $i -lt 60; $i++) {
        $runsJson = & gh run list `
            --repo $repo `
            --workflow $Workflow `
            --event workflow_dispatch `
            --limit 20 `
            --json databaseId,createdAt,status,conclusion,url,headBranch,headSha,displayTitle

        $runs = $runsJson | ConvertFrom-Json
        $run = $runs |
            Where-Object {
                ([datetime]$_.createdAt).ToUniversalTime() -ge $startedAfter -and
                ($_.headBranch -eq $Ref -or $_.headSha -eq $Ref)
            } |
            Sort-Object createdAt -Descending |
            Select-Object -First 1

        if ($run) {
            break
        }

        Start-Sleep -Seconds 5
    }

    if (-not $run) {
        Write-Error "Workflow was triggered, but the new run could not be located. Check Actions for workflow '$Workflow' on ref '$Ref'."
    }

    Write-Host "Remote validation run: $($run.url)" -ForegroundColor Green

    if ($NoWatch) {
        exit 0
    }

    & gh run watch $run.databaseId --repo $repo --interval 30 --exit-status
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
