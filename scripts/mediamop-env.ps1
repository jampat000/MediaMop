# Shared helpers for PowerShell dev scripts — load apps/backend/.env into the process.
# Shell environment variables always win over .env file lines.

function Import-MediaMopBackendDotEnv {
    param(
        [Parameter(Mandatory = $true)]
        [string]$BackendDir
    )
    $EnvFilePath = Join-Path $BackendDir '.env'
    if (-not (Test-Path -LiteralPath $EnvFilePath)) {
        return
    }
    Get-Content -LiteralPath $EnvFilePath -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            return
        }
        $eq = $line.IndexOf('=')
        if ($eq -lt 1) {
            return
        }
        $key = $line.Substring(0, $eq).Trim()
        $val = $line.Substring($eq + 1).Trim()
        if (($val.Length -ge 2) -and $val.StartsWith('"') -and $val.EndsWith('"')) {
            $val = $val.Substring(1, $val.Length - 2)
        } elseif (($val.Length -ge 2) -and $val.StartsWith("'") -and $val.EndsWith("'")) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if ($key -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
            return
        }
        $existing = [Environment]::GetEnvironmentVariable($key, 'Process')
        if ([string]::IsNullOrWhiteSpace($existing)) {
            Set-Item -Path "Env:$key" -Value $val
        }
    }
}
