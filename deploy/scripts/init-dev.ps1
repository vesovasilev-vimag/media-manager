$ErrorActionPreference = 'Stop'
$deployRoot = Split-Path $PSScriptRoot -Parent
$secretRoot = Join-Path $deployRoot 'secrets'
New-Item -ItemType Directory -Force -Path $secretRoot | Out-Null
foreach ($name in @('db_password', 'setup_token')) {
    $target = Join-Path $secretRoot $name
    if (-not (Test-Path -LiteralPath $target)) {
        $bytes = New-Object byte[] 48
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        [IO.File]::WriteAllText($target, [Convert]::ToBase64String($bytes))
    }
}
Write-Output 'Development secrets initialized without printing values.'
