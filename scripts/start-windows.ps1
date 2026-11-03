# Start this app on a Windows PC that has its own checkout.
# Do not copy the Pi's .env, node_modules, or database.
#
# Usage, from the repo root, in PowerShell:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\start-windows.ps1 -Docker
#   .\scripts\start-windows.ps1 -Native
param(
    [switch]$Docker,
    [switch]$Native
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not $Docker -and -not $Native) {
    Write-Host "Choose -Docker (Docker Desktop) or -Native (local Python, Node, Postgres, Redis)."
    exit 1
}

function New-EnvFromExample($destination) {
    if (Test-Path $destination) {
        Write-Host "Using existing $destination"
        return
    }
    Copy-Item (Join-Path $Root ".env.example") $destination
    Write-Host "Created $destination from .env.example. Set new passwords and secrets before live trading."
}

Write-Host ""
Write-Host "Dhan live orders need this PC's own public IPv4 whitelisted at web.dhan.co,"
Write-Host "then a new access token in this machine's .env. Leave LIVE_TRADING_ENABLED=false until then."
Write-Host ""

if ($Docker) {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker Desktop is not installed or not on PATH."
    }
    New-EnvFromExample (Join-Path $Root ".env")
    docker compose up -d --build
    Write-Host "Open http://localhost after the containers are healthy."
    exit 0
}

# Native: Postgres and Redis must already be listening on localhost.
New-EnvFromExample (Join-Path $Root "backend\.env")
$backendEnv = Join-Path $Root "backend\.env"
$raw = Get-Content $backendEnv -Raw
$raw = $raw -replace "@postgres:5432", "@localhost:5432"
$raw = $raw -replace "@redis:6379", "@localhost:6379"
$raw = $raw -replace "redis://:redis_password_here@localhost:6379/0", "redis://localhost:6379/0"
Set-Content -Path $backendEnv -Value $raw -NoNewline

$py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    py -3.12 -m venv (Join-Path $Root "backend\.venv")
}
& $py -m pip install -r (Join-Path $Root "backend\requirements.txt")

Push-Location (Join-Path $Root "frontend")
if (-not (Test-Path "node_modules")) {
    npm install
}
Pop-Location

$backend = Join-Path $Root "backend"
$frontend = Join-Path $Root "frontend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$py' -m uvicorn app.main:app --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$py' -m celery -A app.worker.celery_app worker --pool=solo --loglevel=info"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$py' -m celery -A app.worker.celery_app beat --loglevel=info"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; npm run dev"
Write-Host "API http://localhost:8000  UI http://localhost:5173"
Write-Host "Register a new admin on this empty database. Pi users and trades are not on this machine."
