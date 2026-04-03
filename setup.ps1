# ==============================================================================
# Wilson Setup Script for Windows
# ==============================================================================
# Sets up Wilson on Windows with PowerShell 5.1 or later.
# Run once after cloning the repo:
#
#   git clone https://github.com/CYoung83/wilson.git
#   cd wilson
#   Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#   .\setup.ps1
#
# Self-contained: all data, config, and dependencies live inside the
# wilson folder. Nothing is installed globally.
# Idempotent: safe to run multiple times.
# ==============================================================================

$ErrorActionPreference = "Stop"

# Resolve project root to wherever this script lives
$WILSON_ROOT = $PSScriptRoot
$VENV_DIR    = Join-Path $WILSON_ROOT "venv"
$ENV_FILE    = Join-Path $WILSON_ROOT ".env"
$ENV_EXAMPLE = Join-Path $WILSON_ROOT ".env.example"
$DATA_DIR    = Join-Path $WILSON_ROOT "data"
$PYTHON      = Join-Path $VENV_DIR "Scripts\python.exe"
$PIP         = Join-Path $VENV_DIR "Scripts\pip.exe"

# Colors
function Write-Step  { param($msg) Write-Host "`n[$([char]0x25BA)] $msg" -ForegroundColor Cyan }
function Write-OK    { param($msg) Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn  { param($msg) Write-Host "  [!!] $msg" -ForegroundColor Yellow }
function Write-Fail  { param($msg) Write-Host "  [XX] $msg" -ForegroundColor Red }
function Write-Info  { param($msg) Write-Host "       $msg" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  Wilson -- AI Reasoning Auditor" -ForegroundColor White
Write-Host "  Windows Setup Script" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
Write-Host ""

# ------------------------------------------------------------------------------
# Step 1: Check Python version
# ------------------------------------------------------------------------------
Write-Step "1/7  Checking Python version"

$pythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -gt 3 -or ($major -eq 3 -and $minor -ge 12)) {
                $pythonCmd = $cmd
                Write-OK "Python $major.$minor found ($cmd)"
                break
            } else {
                Write-Warn "Python $major.$minor found but 3.12+ required"
            }
        }
    } catch { }
}

if (-not $pythonCmd) {
    Write-Fail "Python 3.12+ not found."
    Write-Info "Download from: https://www.python.org/downloads/"
    Write-Info "During install, check 'Add python.exe to PATH'"
    exit 1
}

# ------------------------------------------------------------------------------
# Step 2: Create virtual environment
# ------------------------------------------------------------------------------
Write-Step "2/7  Setting up virtual environment"

if (Test-Path $VENV_DIR) {
    Write-OK "Virtual environment already exists -- skipping"
} else {
    Write-Info "Creating venv at $VENV_DIR"
    & $pythonCmd -m venv $VENV_DIR
    Write-OK "Virtual environment created"
}

# ------------------------------------------------------------------------------
# Step 3: Install dependencies
# ------------------------------------------------------------------------------
Write-Step "3/7  Installing dependencies"

Write-Info "Upgrading pip..."
& $PYTHON -m pip install --quiet --upgrade pip

Write-Info "Installing Wilson dependencies..."
& $PIP install --quiet -r (Join-Path $WILSON_ROOT "requirements.txt")
Write-OK "Dependencies installed"

# ------------------------------------------------------------------------------
# Step 4: Configure .env
# ------------------------------------------------------------------------------
Write-Step "4/7  Configuring environment"

if (Test-Path $ENV_FILE) {
    Write-OK ".env already exists -- skipping creation"
} else {
    Copy-Item $ENV_EXAMPLE $ENV_FILE
    Write-OK "Created .env from .env.example"
}

# Check for CourtListener token
$envContent = Get-Content $ENV_FILE -Raw
$tokenLine  = ($envContent -split "`n") | Where-Object { $_ -match "^COURTLISTENER_TOKEN=" }
$tokenValue = if ($tokenLine) { ($tokenLine -split "=", 2)[1].Trim().Trim('"').Trim("'") } else { "" }

if (-not $tokenValue -or $tokenValue -eq "your_courtlistener_token_here") {
    Write-Host ""
    Write-Warn "CourtListener API token required for Wilson to function."
    Write-Info "Get yours free at: https://www.courtlistener.com/sign-in/"
    Write-Host ""
    $input = Read-Host "  Enter your CourtListener API token (or press Enter to skip)"
    if ($input.Trim()) {
        $envContent = $envContent -replace "COURTLISTENER_TOKEN=.*", "COURTLISTENER_TOKEN=$($input.Trim())"
        Set-Content $ENV_FILE $envContent -NoNewline
        Write-OK "Token saved to .env"
    } else {
        Write-Warn "Skipped -- add COURTLISTENER_TOKEN to .env before running Wilson"
    }
} else {
    Write-OK "CourtListener token found"
}

# Set self-contained paths in .env
# Ensure CITATIONS_CSV points inside the project folder if not already set
$csvLine = ($envContent -split "`n") | Where-Object { $_ -match "^CITATIONS_CSV=" }
$csvValue = if ($csvLine) { ($csvLine -split "=", 2)[1].Trim().Trim('"').Trim("'") } else { "" }

if (-not $csvValue -or $csvValue -eq "/path/to/citations-2026-03-31.csv") {
    $defaultCsvPath = Join-Path $DATA_DIR "citations-2026-03-31.csv"
    $envContent = $envContent -replace "CITATIONS_CSV=.*", "CITATIONS_CSV=$defaultCsvPath"
    Set-Content $ENV_FILE $envContent -NoNewline
    Write-Info "CITATIONS_CSV set to $defaultCsvPath"
}

# ------------------------------------------------------------------------------
# Step 5: Bulk citation data (optional)
# ------------------------------------------------------------------------------
Write-Step "5/7  Bulk citation data (optional)"

Write-Host ""
Write-Host "  Wilson can verify citations offline against 18 million federal" -ForegroundColor DarkGray
Write-Host "  case records. Requires ~1.9GB of disk space (~121MB download)." -ForegroundColor DarkGray
Write-Host ""

$csvPath = Join-Path $DATA_DIR "citations-2026-03-31.csv"

if (Test-Path $csvPath) {
    Write-OK "Bulk CSV already present at $csvPath"
} else {
    $downloadCsv = Read-Host "  Download bulk citation data? ~1.9GB uncompressed (y/N)"
    if ($downloadCsv -match "^[Yy]$") {

        New-Item -ItemType Directory -Force -Path $DATA_DIR | Out-Null

        $bulkUrl    = "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/citations-2026-03-31.csv.bz2"
        $compressed = Join-Path $DATA_DIR "citations-2026-03-31.csv.bz2"

        Write-Info "Downloading from CourtListener S3..."
        try {
            $progressPreference = 'SilentlyContinue'
            Invoke-WebRequest -Uri $bulkUrl -OutFile $compressed
            $progressPreference = 'Continue'
            Write-OK "Download complete"
        } catch {
            Write-Fail "Download failed: $_"
            Write-Info "You can download manually from:"
            Write-Info $bulkUrl
            Write-Info "Then decompress with 7-Zip and set CITATIONS_CSV in .env"
        }

        if (Test-Path $compressed) {
            Write-Info "Decompressing .bz2 file..."

            # Try Python's bz2 module for decompression (no 7-Zip required)
            $decompressScript = @"
import bz2, os, sys
src = sys.argv[1]
dst = sys.argv[2]
print(f'Decompressing {os.path.getsize(src):,} bytes...')
with bz2.open(src, 'rb') as f_in, open(dst, 'wb') as f_out:
    chunk_size = 8 * 1024 * 1024  # 8MB chunks
    while True:
        chunk = f_in.read(chunk_size)
        if not chunk:
            break
        f_out.write(chunk)
print('Done.')
"@
            $decompressScript | & $PYTHON - $compressed $csvPath

            if (Test-Path $csvPath) {
                Remove-Item $compressed -Force
                Write-OK "Decompressed to $csvPath"

                # Update .env with confirmed path
                $envContent = Get-Content $ENV_FILE -Raw
                $envContent = $envContent -replace "CITATIONS_CSV=.*", "CITATIONS_CSV=$csvPath"
                Set-Content $ENV_FILE $envContent -NoNewline
                Write-OK "CITATIONS_CSV updated in .env"
            } else {
                Write-Fail "Decompression failed -- file not found after extraction"
                Write-Info "Try decompressing manually with 7-Zip: https://www.7-zip.org"
            }
        }

    } else {
        Write-Warn "Skipped -- Wilson will use API-only verification"
        Write-Info "You can download bulk data later and set CITATIONS_CSV in .env"
        Write-Info "On first use, Wilson will prompt you again"
    }
}

# ------------------------------------------------------------------------------
# Step 6: Check Ollama (optional)
# ------------------------------------------------------------------------------
Write-Step "6/7  Checking Ollama (Phase 3 coherence checking)"

$ollamaHost = "http://localhost:11434"
$envContent = Get-Content $ENV_FILE -Raw
$ollamaLine = ($envContent -split "`n") | Where-Object { $_ -match "^OLLAMA_HOST=" }
if ($ollamaLine) {
    $ollamaHost = ($ollamaLine -split "=", 2)[1].Trim().Trim('"').Trim("'")
}

try {
    $response = Invoke-RestMethod -Uri "$ollamaHost/api/tags" -TimeoutSec 3 -ErrorAction Stop
    $models = $response.models | ForEach-Object { $_.name }
    Write-OK "Ollama reachable at $ollamaHost"
    if ($models) {
        Write-Info "Available models: $($models -join ', ')"
        Write-OK "Phase 3 coherence checking ENABLED"
    } else {
        Write-Warn "No models loaded. Run: ollama pull llama3"
    }
} catch {
    Write-Warn "Ollama not reachable at $ollamaHost"
    Write-Info "Phase 3 coherence checking will be skipped"
    Write-Info "Install Ollama from: https://ollama.com"
    Write-Info "Or set OLLAMA_HOST in .env if running on another machine"
}

# ------------------------------------------------------------------------------
# Step 7: Run tests
# ------------------------------------------------------------------------------
Write-Step "7/7  Running Wilson test suite"

$passed = 0
$failed = 0

Set-Location $WILSON_ROOT

Write-Host ""
Write-Info "Running smoke_test.py (Phases 1 + 2)..."
try {
    & $PYTHON smoke_test.py
    Write-OK "smoke_test.py -- PASSED"
    $passed++
} catch {
    Write-Fail "smoke_test.py -- FAILED"
    $failed++
}

Write-Host ""
Write-Info "Running test_mata_avianca.py (proof of concept)..."
try {
    & $PYTHON test_mata_avianca.py
    Write-OK "test_mata_avianca.py -- PASSED"
    $passed++
} catch {
    Write-Fail "test_mata_avianca.py -- FAILED"
    $failed++
}

Write-Host ""
Write-Info "Running coherence_check.py (Phase 3)..."
try {
    & $PYTHON coherence_check.py
    Write-OK "coherence_check.py -- PASSED"
    $passed++
} catch {
    Write-Warn "coherence_check.py -- SKIPPED or FAILED (Ollama required)"
}

# ------------------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------------------
Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  Wilson Setup Complete" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
Write-Host ""
Write-Host "  Tests passed: $passed" -ForegroundColor Green
if ($failed -gt 0) {
    Write-Host "  Tests failed: $failed" -ForegroundColor Red
}
Write-Host ""
Write-Host "  To run Wilson web interface:" -ForegroundColor White
Write-Host "    cd $WILSON_ROOT" -ForegroundColor DarkGray
Write-Host "    .\venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  To run command line tests:" -ForegroundColor White
Write-Host "    .\venv\Scripts\python.exe smoke_test.py" -ForegroundColor DarkGray
Write-Host "    .\venv\Scripts\python.exe test_mata_avianca.py" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Configuration: .env" -ForegroundColor DarkGray
Write-Host "  Documentation: README.md" -ForegroundColor DarkGray
Write-Host "  API notes:     API_ACCESS_NOTES.md" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Wilson is ready." -ForegroundColor Green
Write-Host ""
