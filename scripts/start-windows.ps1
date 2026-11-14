# Start this app on a Windows PC.
# A new PC, with only Windows installed, uses Docker. Run:
#   powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1
# That command is safe to run again after a reboot.
#
# -Native installs the same versions the app is built for, then starts without Docker:
#   Python 3.12, Node.js 22, PostgreSQL 16, Memurai (Redis 7 protocol). Celery uses --pool=solo.
#   powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1 -Native
param(
    [switch]$Native
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function New-ServicePassword {
    # Windows complexity is upper, lower, and a digit. No quotes or symbols: the Postgres installer splits on those.
    $upper = -join ((65..90) | Get-Random -Count 4 | ForEach-Object { [char]$_ })
    $lower = -join ((97..122) | Get-Random -Count 8 | ForEach-Object { [char]$_ })
    $digit = -join ((0..9) | Get-Random -Count 4 | ForEach-Object { [string]$_ })
    return "$upper$lower$digit"
}

function New-Secret([int]$HexChars) {
    $chars = @()
    for ($i = 0; $i -lt $HexChars; $i++) {
        $chars += '{0:x}' -f (Get-Random -Maximum 16)
    }
    return -join $chars
}

function New-DockerEnv {
    $dest = Join-Path $Root ".env"
    if (Test-Path $dest) {
        Write-Host "Using existing $dest"
        return
    }
    $pg = New-Secret 32
    $redis = New-Secret 32
    $jwt = New-Secret 48
    $secret = New-Secret 48
    $enc = New-Secret 32
    $raw = Get-Content (Join-Path $Root ".env.example") -Raw
    $raw = $raw.Replace("strong_password_here", $pg)
    $raw = $raw.Replace("redis_password_here", $redis)
    $raw = $raw.Replace("your-jwt-secret-key", $jwt)
    $raw = $raw.Replace("your-super-secret-key-change-this", $secret)
    $raw = $raw.Replace("your-32-byte-encryption-key-here!!", $enc)
    Set-Content -Path $dest -Value $raw -NoNewline
    Write-Host "Created $dest with new local passwords. The Dhan token is empty. LIVE_TRADING_ENABLED stays false."
}

function Add-DockerToPath {
    $bin = "C:\Program Files\Docker\Docker\resources\bin"
    if (Test-Path $bin) {
        $env:Path = "$bin;" + $env:Path
    }
}

function Wait-DockerEngine {
    Add-DockerToPath
    $desktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (Test-Path $desktop) {
        Start-Process $desktop
    }
    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $deadline) {
        docker info *> $null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 5
    }
    throw "Docker Desktop did not start. Open it once, wait until it is running, then run this script again."
}

function Wait-Api([int]$Port) {
    $base = if ($Port -eq 80) { "http://localhost" } else { "http://localhost:$Port" }
    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $deadline) {
        try {
            $res = Invoke-WebRequest -Uri "$base/api/health" -UseBasicParsing -TimeoutSec 5
            if ($res.StatusCode -eq 200) { return }
        } catch {
            Start-Sleep -Seconds 5
        }
    }
    throw "The API did not answer on $base/api/health. Check 'docker compose logs backend'."
}

function New-FirstAdmin {
    $pass = New-Secret 24
    $out = docker compose exec -T -e "FIRST_ADMIN_PASSWORD=$pass" backend python -m app.scripts.create_admin
    Write-Host $out
    if ($out -match "Created admin") {
        Write-Host ""
        Write-Host "Sign in at http://localhost"
        Write-Host "Username: admin"
        Write-Host "Password: $pass"
        Write-Host "This password is shown once. It is not saved in .env."
    }
}

function Test-Port([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-WebPort {
    if (Test-Port 80) { return 5173 }
    return 80
}

function Test-CanBind([int]$Port) {
    $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Any, $Port)
    try {
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        $listener.Stop()
    }
}

function Get-NativeWebPort {
    if (Test-CanBind 80) { return 80 }
    return 5173
}

function Get-LanHost {
    $ip = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
        Select-Object -First 1 -ExpandProperty IPAddress
    if ($ip) { return $ip }
    return "localhost"
}

function Allow-HomePort([int]$Port) {
    $name = "Algo platform TCP $Port"
    if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) { return }
    try {
        New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private | Out-Null
    } catch {
        Write-Host "Could not open port $Port on the Private firewall. Other devices on this network may be blocked."
    }
}

function Write-HomeAddress([int]$Port) {
    $hostName = Get-LanHost
    $url = if ($Port -eq 80) { "http://$hostName" } else { "http://${hostName}:$Port" }
    Write-Host "On this PC: http://localhost$(if ($Port -eq 80) { '' } else { ":$Port" })"
    Write-Host "On this home network: $url"
    Write-Host "No router port forward is required. Postgres and Redis stay on this PC."
}

function Update-SessionPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$userPath"
    foreach ($extra in @(
        "C:\Program Files\nodejs",
        "C:\Program Files\PostgreSQL\16\bin",
        "$env:LOCALAPPDATA\Programs\Python\Python312",
        "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts",
        "C:\Program Files\Python312",
        "C:\Program Files\Python312\Scripts"
    )) {
        if (Test-Path $extra) { $env:Path = "$extra;" + $env:Path }
    }
}

function Install-Winget([string]$Id) {
    winget install -e --id $Id --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "winget could not install $Id" }
    Update-SessionPath
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-Memurai {
    # Redis 7 protocol. The exact id with --disable-interactivity fails on a new PC:
    # Memurai is a Windows service, and that flag hides the Administrator prompt.
    Write-Host "Installing Memurai (Redis 7 protocol). Windows has no current Redis build."
    Write-Host "Windows will ask for Administrator. Approve that prompt."
    winget install Memurai.MemuraiDeveloper --accept-package-agreements --accept-source-agreements
    $wingetCode = $LASTEXITCODE
    $alreadyThere = @(0, -1978335189, -1978334963, -1978334962)
    if ($alreadyThere -notcontains $wingetCode) {
        Write-Host "winget could not install Memurai (exit $wingetCode). Downloading the developer installer."
        $msi = Join-Path $env:TEMP "Memurai-Developer-v4.1.2.msi"
        Invoke-WebRequest -Uri "https://dist.memurai.com/releases/Memurai-Developer/4.1.2/Memurai-Developer-v4.1.2.msi" -OutFile $msi
        $installArgs = "/i `"$msi`" /quiet"
        try {
            if (Test-IsAdmin) {
                $proc = Start-Process msiexec.exe -ArgumentList $installArgs -Wait -PassThru
            } else {
                $proc = Start-Process msiexec.exe -ArgumentList $installArgs -Verb RunAs -Wait -PassThru
            }
        } catch {
            throw "Memurai did not install. Approve the Administrator prompt, then run this script again."
        }
        if ($null -eq $proc.ExitCode -or ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010 -and $proc.ExitCode -ne 1638)) {
            throw "Memurai did not install (msiexec $($proc.ExitCode)). Open PowerShell as Administrator and run this script again."
        }
    }

    $svc = Get-Service -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'Memurai' } | Select-Object -First 1
    if ($svc -and $svc.Status -ne "Running") {
        try {
            Start-Service $svc.Name
        } catch {
            throw "Memurai is installed, but its service is stopped. Open PowerShell as Administrator and run this script again."
        }
    }
}

function Get-PostgresInstallerUrl {
    $fallback = "https://get.enterprisedb.com/postgresql/postgresql-16.15-5-windows-x64.exe"
    $show = & winget show -e --id PostgreSQL.PostgreSQL.16 --accept-source-agreements 2>&1 | Out-String
    $found = [regex]::Match($show, 'https://get\.enterprisedb\.com/postgresql/postgresql-16\S+\.exe')
    if ($found.Success) { return $found.Value }
    return $fallback
}

function Install-Postgres([string]$SuperPassword) {
    # Same failure as Memurai: --disable-interactivity hides the Administrator prompt,
    # and winget then exits before the EnterpriseDB installer runs. The override still
    # makes that installer unattended. Stack Builder is left out; it pops a window at the end.
    Write-Host "Installing PostgreSQL 16."
    Write-Host "Windows will ask for Administrator. Approve that prompt."
    $override = "--mode unattended --unattendedmodeui none --superpassword $SuperPassword --servicepassword $SuperPassword --servicename postgresql-x64-16 --serverport 5432 --enable-components server,commandlinetools"
    winget install -e --id PostgreSQL.PostgreSQL.16 --scope machine --accept-package-agreements --accept-source-agreements --override $override
    $wingetCode = $LASTEXITCODE
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline -and -not (Test-Port 5432)) { Start-Sleep -Seconds 2 }
    if (Test-Port 5432) { return }

    Write-Host "winget could not install PostgreSQL 16 (exit $wingetCode). Downloading the installer from EnterpriseDB."
    $url = Get-PostgresInstallerUrl
    $exe = Join-Path $env:TEMP "postgresql-16-windows-x64.exe"
    $prev = $ProgressPreference
    $ProgressPreference = "SilentlyContinue"
    try {
        Invoke-WebRequest -Uri $url -OutFile $exe -UseBasicParsing
    } catch {
        throw "PostgreSQL 16 did not download from $url. Check this PC's internet connection, then run this script again."
    } finally {
        $ProgressPreference = $prev
    }
    if (-not (Test-Path $exe) -or (Get-Item $exe).Length -lt 1MB) {
        throw "PostgreSQL 16 did not download from $url. Check this PC's internet connection, then run this script again."
    }
    try {
        if (Test-IsAdmin) {
            $proc = Start-Process -FilePath $exe -ArgumentList $override -Wait -PassThru
        } else {
            $proc = Start-Process -FilePath $exe -ArgumentList $override -Verb RunAs -Wait -PassThru
        }
    } catch {
        throw "PostgreSQL 16 did not install. Approve the Administrator prompt, then run this script again."
    }
    if ($null -eq $proc.ExitCode -or ($proc.ExitCode -ne 0 -and $proc.ExitCode -ne 3010)) {
        throw "PostgreSQL 16 did not install (installer exit $($proc.ExitCode)). Open PowerShell as Administrator and run this script again."
    }
}

function Find-Python312 {
    Update-SessionPath
    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Program Files\Python312\python.exe",
        "C:\Program Files\Python\Python312\python.exe"
    )) {
        if (Test-Path $candidate) { return $candidate }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $exe = & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $exe) { return $exe.Trim() }
    }
    return $null
}

function Ensure-NativeTools {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is missing. Open the Microsoft Store, install App Installer, or run Windows Update, then run this script again."
    }
    $python = Find-Python312
    if (-not $python) {
        Write-Host "Installing Python 3.12."
        winget install python3.12 --accept-package-agreements --accept-source-agreements
        Update-SessionPath
        $python = Find-Python312
    }
    if (-not $python) {
        throw "Python 3.12 is not on PATH yet. Close this window, open PowerShell again, and run the same -Native command."
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Host "Installing Node.js 22."
        Install-Winget "OpenJS.NodeJS.22"
    }
    $node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $node) {
        throw "Node.js 22 is not on PATH yet. Close this window, open PowerShell again, and run the same -Native command."
    }

    if (-not (Test-Port 6379)) {
        Install-Memurai
        $deadline = (Get-Date).AddMinutes(2)
        while ((Get-Date) -lt $deadline -and -not (Test-Port 6379)) { Start-Sleep -Seconds 3 }
    }
    if (-not (Test-Port 6379)) {
        throw "Redis is not listening on localhost:6379. Start the Memurai service, then run this script again."
    }

    $superPassword = $null
    if (-not (Test-Port 5432)) {
        $superPassword = New-ServicePassword
        Install-Postgres $superPassword
        Update-SessionPath
        $svc = Get-Service -Name "postgresql-x64-16" -ErrorAction SilentlyContinue
        if ($svc -and $svc.Status -ne "Running") {
            try {
                Start-Service $svc.Name
            } catch {
                throw "PostgreSQL 16 is installed, but its service is stopped. Open PowerShell as Administrator and run this script again."
            }
        }
        $deadline = (Get-Date).AddMinutes(2)
        while ((Get-Date) -lt $deadline -and -not (Test-Port 5432)) { Start-Sleep -Seconds 3 }
    }
    if (-not (Test-Port 5432)) {
        throw "Postgres is not listening on localhost:5432. If the installer asked for a restart, restart Windows and run this script again."
    }
    return @{ Python = $python; SuperPassword = $superPassword }
}

function Initialize-NativeDatabase([string]$SuperPassword) {
    $psql = "C:\Program Files\PostgreSQL\16\bin\psql.exe"
    if (-not (Test-Path $psql)) {
        $cmd = Get-Command psql -ErrorAction SilentlyContinue
        if ($cmd) { $psql = $cmd.Source } else { throw "psql was not found. PostgreSQL 16 client tools are required." }
    }
    $envFile = Join-Path $Root "backend\.env"
    $dbUser = "algo_user"
    $dbName = "algo_platform"
    $dbPass = ""
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^POSTGRES_USER=(.*)$') { $dbUser = $Matches[1] }
        if ($line -match '^POSTGRES_DB=(.*)$') { $dbName = $Matches[1] }
        if ($line -match '^POSTGRES_PASSWORD=(.*)$') { $dbPass = $Matches[1] }
    }
    if ($SuperPassword) { $env:PGPASSWORD = $SuperPassword }
    $role = & $psql -U postgres -h 127.0.0.1 -d postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$dbUser'"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not sign in to local Postgres as user postgres. If Postgres was already installed, its superuser password is unknown to this script."
    }
    if ($role.Trim() -ne "1") {
        & $psql -U postgres -h 127.0.0.1 -d postgres -c "CREATE USER ""$dbUser"" WITH PASSWORD '$dbPass' LOGIN;"
        if ($LASTEXITCODE -ne 0) { throw "Could not create the Postgres role $dbUser" }
    }
    $exists = & $psql -U postgres -h 127.0.0.1 -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$dbName'"
    if ($exists.Trim() -ne "1") {
        & $psql -U postgres -h 127.0.0.1 -d postgres -c "CREATE DATABASE ""$dbName"" OWNER ""$dbUser"";"
        if ($LASTEXITCODE -ne 0) { throw "Could not create the database $dbName" }
    }
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
}

function Start-Native {
    $tools = Ensure-NativeTools

    $backendEnv = Join-Path $Root "backend\.env"
    if (-not (Test-Path $backendEnv)) {
        $pg = New-Secret 32
        $redis = New-Secret 32
        $jwt = New-Secret 48
        $secret = New-Secret 48
        $enc = New-Secret 32
        $raw = Get-Content (Join-Path $Root ".env.example") -Raw
        $raw = $raw.Replace("strong_password_here", $pg)
        $raw = $raw.Replace("redis_password_here", $redis)
        $raw = $raw.Replace("your-jwt-secret-key", $jwt)
        $raw = $raw.Replace("your-super-secret-key-change-this", $secret)
        $raw = $raw.Replace("your-32-byte-encryption-key-here!!", $enc)
        Set-Content -Path $backendEnv -Value $raw -NoNewline
        Write-Host "Created $backendEnv with new local passwords. The Dhan token is empty. LIVE_TRADING_ENABLED stays false."
    }
    $raw = Get-Content $backendEnv -Raw
    $raw = $raw.Replace("@postgres:5432", "@localhost:5432")
    $raw = $raw.Replace("@redis:6379", "@localhost:6379")
    $raw = $raw -replace '(?m)^REDIS_URL=.*', 'REDIS_URL=redis://localhost:6379/0'
    Set-Content -Path $backendEnv -Value $raw -NoNewline
    Initialize-NativeDatabase $tools.SuperPassword

    $py = Join-Path $Root "backend\.venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        & $tools.Python -m venv (Join-Path $Root "backend\.venv")
    }
    & $py -m pip install -r (Join-Path $Root "backend\requirements.txt")

    Push-Location (Join-Path $Root "frontend")
    if (-not (Test-Path "node_modules")) { npm install }
    Pop-Location

    $backend = Join-Path $Root "backend"
    $frontend = Join-Path $Root "frontend"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$py' -m uvicorn app.main:app --reload"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$py' -m celery -A app.worker.celery_app worker --pool=solo --loglevel=info"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backend'; & '$py' -m celery -A app.worker.celery_app beat --loglevel=info"
    $webPort = Get-NativeWebPort
    Allow-HomePort $webPort
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$frontend'; npm run dev -- --host 0.0.0.0 --port $webPort --strictPort"
    Write-HomeAddress $webPort

    $deadline = (Get-Date).AddMinutes(3)
    $up = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $res = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 5
            if ($res.StatusCode -eq 200) { $up = $true; break }
        } catch { Start-Sleep -Seconds 3 }
    }
    if ($up) {
        $pass = New-Secret 24
        $env:FIRST_ADMIN_PASSWORD = $pass
        Push-Location $backend
        $out = & $py -m app.scripts.create_admin
        Pop-Location
        Remove-Item Env:FIRST_ADMIN_PASSWORD
        Write-Host $out
        if ($out -match "Created admin") {
            Write-Host "Username: admin"
            Write-Host "Password: $pass"
            Write-Host "This password is shown once. It is not saved in .env."
        }
    }
    Write-Host "API http://localhost:8000  UI http://localhost:5173"
}

Write-Host ""
Write-Host "Dhan live orders need this PC's own public IPv4 whitelisted at web.dhan.co,"
Write-Host "then a new access token in this machine's .env. Leave LIVE_TRADING_ENABLED=false until then."
Write-Host ""

if ($Native) {
    Start-Native
    exit 0
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw "winget is missing. Open the Microsoft Store, install App Installer, or run Windows Update, then run this script again."
}

$installedSomething = $false
wsl --status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing WSL. Windows will ask you to restart."
    wsl --install --no-distribution
    $installedSomething = $true
}

Add-DockerToPath
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Docker Desktop."
    winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
    $installedSomething = $true
}

if ($installedSomething) {
    Write-Host ""
    Write-Host "Restart this PC if Windows asked you to, then run the same command again:"
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1"
    exit 0
}

Wait-DockerEngine
New-DockerEnv
$env:WEB_PORT = "$(Get-WebPort)"
Allow-HomePort ([int]$env:WEB_PORT)
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
Wait-Api ([int]$env:WEB_PORT)
New-FirstAdmin
$homeUrl = if ($env:WEB_PORT -eq "80") { "http://localhost" } else { "http://localhost:$($env:WEB_PORT)" }
Start-Process $homeUrl
Write-HomeAddress ([int]$env:WEB_PORT)
