$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the Python 3.12 environment first. See README.md.' }
$listener = Get-NetTCPConnection -LocalPort 8010 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw 'Port 8010 is already in use. Identify the existing service before starting another.' }
Push-Location $projectRoot
try {
    & $pythonPath -m uvicorn auditor.main:app --app-dir backend --host 127.0.0.1 --port 8010 --no-proxy-headers
    if ($LASTEXITCODE -ne 0) { throw 'Backend stopped with an error.' }
} finally { Pop-Location }
