# Clear local users + sessions so /setup (first admin) works again. See scripts/dev-reset-auth.mjs.
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\weir-env.ps1"
$repoRoot = Split-Path -Parent $PSScriptRoot
Import-WeirDotEnv -RepoRoot $repoRoot
& node (Join-Path $PSScriptRoot "dev-reset-auth.mjs") @args
exit $LASTEXITCODE
