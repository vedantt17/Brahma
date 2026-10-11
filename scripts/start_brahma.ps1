param([ValidateRange(1024,65535)][int]$Port = 8770)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Create .venv and install requirements.txt first. See README.md.'
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Port $Port is in use. Pass a different -Port value."
}
$artifacts = Join-Path $root 'artifacts'
New-Item -ItemType Directory -Path $artifacts -Force | Out-Null
$previousDatabase = $env:DATABASE_URL
try {
    if (-not $env:DATABASE_URL) {
        $db = (Join-Path $root 'data\brahma.db').Replace('\', '/')
        $env:DATABASE_URL = "sqlite+aiosqlite:///$db"
    }
    $process = Start-Process -FilePath $python -WorkingDirectory $root -WindowStyle Hidden -PassThru `
        -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port',"$Port") `
        -RedirectStandardOutput (Join-Path $artifacts 'server.stdout.log') `
        -RedirectStandardError (Join-Path $artifacts 'server.stderr.log')
    $process.Id | Set-Content -LiteralPath (Join-Path $root '.brahma-server.pid')
    Write-Output "Brahma started (PID $($process.Id)): http://127.0.0.1:$Port"
} finally {
    $env:DATABASE_URL = $previousDatabase
}
