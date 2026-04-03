$WilsonRoot  = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python      = Join-Path $WilsonRoot "python\python.exe"
$EnvFile     = Join-Path $WilsonRoot ".env"
$FirstLaunch = Join-Path $WilsonRoot "Wilson_firstlaunch.ps1"
$Port        = 8000
$Url         = "http://localhost:$Port"

function Get-EnvValue {
    param($key)
    $line = (Get-Content $EnvFile | Where-Object { $_ -match "^$key=" } | Select-Object -First 1)
    if ($line) { return ($line -split "=", 2)[1].Trim() }
    return ""
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  Wilson -- AI Reasoning Auditor" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
Write-Host ""

# Check Python runtime
if (-not (Test-Path $Python)) {
    Write-Host "[ERROR] Python runtime not found. Please reinstall Wilson." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check configuration exists
if (-not (Test-Path $EnvFile)) {
    Write-Host "[ERROR] Configuration file not found. Please reinstall Wilson." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Run first launch configuration if token is missing or CSV is absent
$token   = Get-EnvValue "COURTLISTENER_TOKEN"
$csvPath = Get-EnvValue "CITATIONS_CSV"
$needsConfig = (-not $token -or $token -eq "your_courtlistener_token_here")
$needsCsv    = (-not (Test-Path $csvPath))

if (($needsConfig -or $needsCsv) -and (Test-Path $FirstLaunch)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $FirstLaunch $WilsonRoot
}

# Check if already running
try {
    $test = New-Object Net.Sockets.TcpClient("127.0.0.1", $Port)
    $test.Close()
    Write-Host "  [!!] Port $Port already in use -- Wilson may already be running." -ForegroundColor Yellow
    Write-Host "       Opening browser..." -ForegroundColor DarkGray
    Start-Process $Url
    Read-Host "Press Enter to exit"
    exit 0
} catch {}

Write-Host "  Starting server at $Url" -ForegroundColor DarkGray
Write-Host "  This window must stay open while Wilson is running." -ForegroundColor DarkGray
Write-Host "  Close this window to shut down Wilson." -ForegroundColor DarkGray
Write-Host ""

# Start uvicorn as background process
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName               = $Python
$startInfo.Arguments              = "-m uvicorn api:app --host 127.0.0.1 --port $Port --log-level warning"
$startInfo.WorkingDirectory       = $WilsonRoot
$startInfo.UseShellExecute        = $false
$startInfo.CreateNoWindow         = $true

$proc = [System.Diagnostics.Process]::Start($startInfo)
Write-Host "  Server process started (PID: $($proc.Id))" -ForegroundColor DarkGray

# Poll until ready
$ready = $false
Write-Host "  Waiting for server..." -ForegroundColor DarkGray
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $t = New-Object Net.Sockets.TcpClient("127.0.0.1", $Port)
        $t.Close()
        $ready = $true
        break
    } catch {}
}

if ($ready) {
    Write-Host "  Server ready -- opening browser..." -ForegroundColor Green
    Write-Host ""
    Start-Process $Url
} else {
    Write-Host ""
    Write-Host "[ERROR] Server did not start within 30 seconds." -ForegroundColor Red
    Write-Host "        Check that your CourtListener token is set in .env" -ForegroundColor DarkGray
    $proc | Stop-Process -Force -ErrorAction SilentlyContinue
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "============================================================" -ForegroundColor White
Write-Host "  Wilson is running at $Url" -ForegroundColor Green
Write-Host "  Close this window to stop Wilson." -ForegroundColor DarkGray
Write-Host "============================================================" -ForegroundColor White
Write-Host ""

$proc.WaitForExit()

Write-Host ""
Write-Host "  Wilson server stopped." -ForegroundColor DarkGray
Write-Host ""
Read-Host "Press Enter to close"
