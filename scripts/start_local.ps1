$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'asx_feed_env\Scripts\python.exe'
$frontend = Join-Path $root 'frontend'

if (-not (Test-Path $python)) {
    throw "Python environment not found at $python. Create it and install requirements.txt first."
}

function Test-Port($port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Port 8000)) {
    Start-Process powershell.exe -WorkingDirectory $root -ArgumentList @(
        '-NoExit',
        '-Command',
        "& '$python' -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000"
    ) | Out-Null
}

$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $response = Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch {
    }
}

if (-not $ready) {
    throw 'Backend did not become ready on http://127.0.0.1:8000. Check the backend terminal for startup errors.'
}

if (-not (Test-Port 3000)) {
    Start-Process npm.cmd -WorkingDirectory $frontend -ArgumentList @('run', 'dev') | Out-Null
}

Write-Host 'Backend ready:  http://localhost:8000/health'
Write-Host 'Frontend URL:   http://localhost:3000'
Write-Host 'Admin URL:      http://localhost:3000/admin'