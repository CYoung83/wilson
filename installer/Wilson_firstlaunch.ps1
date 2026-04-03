param([string]$AppDir)

$envFile = Join-Path $AppDir ".env"
$python  = Join-Path $AppDir "python\python.exe"

function ConvertFrom-SecureStringPlain {
    param([System.Security.SecureString]$secure)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringAuto($ptr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
}

function Get-EnvValue {
    param($key)
    $line = (Get-Content $envFile | Where-Object { $_ -match "^$key=" } | Select-Object -First 1)
    if ($line) { return ($line -split "=", 2)[1].Trim() }
    return ""
}

function Set-EnvValue {
    param($key, $value)
    $content = Get-Content $envFile -Raw
    if ($content -match "(?m)^$key=") {
        $content = $content -replace "(?m)^$key=.*", "$key=$value"
    } else {
        $content = $content.TrimEnd() + "`n$key=$value`n"
    }
    Set-Content $envFile $content -NoNewline
}

function Test-CourtListenerToken {
    param($token)
    try {
        $resp = Invoke-RestMethod `
            -Uri "https://www.courtlistener.com/api/rest/v4/" `
            -Headers @{ Authorization = "Token $token" } `
            -TimeoutSec 8 `
            -ErrorAction Stop
        return $true
    } catch { return $false }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  Wilson -- First Launch Configuration" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
Write-Host ""

$configChanged = $false

# ------------------------------------------------------------------------------
# CourtListener token
# ------------------------------------------------------------------------------
$token = Get-EnvValue "COURTLISTENER_TOKEN"

if (-not $token -or $token -eq "your_courtlistener_token_here") {
    Write-Host "  CourtListener API token required for Wilson to function." -ForegroundColor Yellow
    Write-Host "  Get yours free at: https://www.courtlistener.com/sign-in/" -ForegroundColor DarkGray
    Write-Host ""

    $attempts = 0
    while ($true) {
        $attempts++
        $secure = Read-Host "  Enter CourtListener token (or press Enter to skip)" -AsSecureString
        $plain  = ConvertFrom-SecureStringPlain $secure

        if (-not $plain.Trim()) {
            Write-Host "  Skipped -- Phase 1 and Phase 2 will not function without a token." -ForegroundColor Yellow
            break
        }

        Write-Host "  Validating token..." -ForegroundColor DarkGray
        if (Test-CourtListenerToken $plain.Trim()) {
            Set-EnvValue "COURTLISTENER_TOKEN" $plain.Trim()
            Write-Host "  Token validated and saved." -ForegroundColor Green
            $configChanged = $true
            break
        } else {
            Write-Host "  Token validation failed -- check the token and try again." -ForegroundColor Red
            if ($attempts -ge 3) {
                Write-Host "  Too many attempts -- skipping. Add token to .env manually." -ForegroundColor Yellow
                break
            }
        }
    }
    Write-Host ""
}

# ------------------------------------------------------------------------------
# Bulk citation CSV
# ------------------------------------------------------------------------------
$csvPath = Get-EnvValue "CITATIONS_CSV"

if (-not (Test-Path $csvPath)) {
    Write-Host "  Bulk citation database not found." -ForegroundColor Yellow
    Write-Host "  Without it, Wilson uses the CourtListener API only (no offline verification)." -ForegroundColor DarkGray
    Write-Host "  Download size: ~121MB compressed, ~1.9GB uncompressed." -ForegroundColor DarkGray
    Write-Host ""
    $download = Read-Host "  Download bulk citation database now? (y/N)"

    if ($download -match "^[Yy]$") {
        $dataDir = Join-Path $AppDir "data"
        New-Item -ItemType Directory -Force -Path $dataDir | Out-Null

        $url        = "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/citations-2026-03-31.csv.bz2"
        $compressed = Join-Path $dataDir "citations-2026-03-31.csv.bz2"
        $final      = Join-Path $dataDir "citations-2026-03-31.csv"

        Write-Host "  Downloading..." -ForegroundColor DarkGray
        try {
            $ProgressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $url -OutFile $compressed
            $ProgressPreference = 'Continue'
            Write-Host "  Download complete. Decompressing (this takes a minute)..." -ForegroundColor DarkGray

            $decompScript = Join-Path $env:TEMP "wilson_decompress.py"
            Set-Content $decompScript @"
import bz2, os, sys
src, dst = sys.argv[1], sys.argv[2]
with bz2.open(src, 'rb') as fin, open(dst, 'wb') as fout:
    while True:
        chunk = fin.read(8 * 1024 * 1024)
        if not chunk:
            break
        fout.write(chunk)
os.remove(src)
"@ -Encoding UTF8
            & $python $decompScript $compressed $final
            Remove-Item $decompScript -Force -ErrorAction SilentlyContinue

            if (Test-Path $final) {
                Set-EnvValue "CITATIONS_CSV" $final
                Write-Host "  Bulk database ready." -ForegroundColor Green
                $configChanged = $true
            } else {
                Write-Host "  Decompression failed -- you can retry by relaunching Wilson." -ForegroundColor Red
            }
        } catch {
            Write-Host "  Download failed: $_" -ForegroundColor Red
            Write-Host "  You can retry by relaunching Wilson." -ForegroundColor DarkGray
        }
    } else {
        Write-Host "  Skipped -- Wilson will use API-only verification." -ForegroundColor DarkGray
        Write-Host "  You can download the database by relaunching Wilson." -ForegroundColor DarkGray
    }
    Write-Host ""
}

# ------------------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------------------
if ($configChanged) {
    Write-Host "  Configuration saved to .env" -ForegroundColor Green
} else {
    Write-Host "  Configuration unchanged." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "  Starting Wilson..." -ForegroundColor White
Write-Host ""
