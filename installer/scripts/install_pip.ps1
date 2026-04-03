param([string]$AppDir)

$python = Join-Path $AppDir "python\python.exe"
$tmp    = Join-Path $AppDir "installer\tmp"

# Install pip
$getPip = Join-Path $tmp "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $getPip
& $python $getPip --no-warn-script-location

# Install setuptools -- required for source builds
& $python -m pip install setuptools --no-warn-script-location

# Install pure Python diff-match-patch to satisfy eyecite's
# fast-diff-match-patch requirement without needing a C compiler
& $python -m pip install diff-match-patch --no-warn-script-location

# Create fast-diff-match-patch shim so pip doesn't try to build it from source
$sitePackages = Join-Path $AppDir "python\Lib\site-packages"

$distInfo = Join-Path $sitePackages "fast_diff_match_patch-2.1.0.dist-info"
New-Item -ItemType Directory -Force -Path $distInfo | Out-Null

Set-Content (Join-Path $distInfo "METADATA") @"
Metadata-Version: 2.1
Name: fast-diff-match-patch
Version: 2.1.0
"@
Set-Content (Join-Path $distInfo "WHEEL") @"
Wheel-Version: 1.0
Generator: wilson-installer
Root-Is-Purelib: true
Tag: py3-none-any
"@
Set-Content (Join-Path $distInfo "RECORD") ""

# Create the shim module that wraps pure Python diff-match-patch
Set-Content (Join-Path $sitePackages "fast_diff_match_patch.py") @"
# Wilson installer shim
# Wraps pure Python diff-match-patch to satisfy eyecite dependency
# without requiring Microsoft C++ Build Tools
from diff_match_patch import diff_match_patch
"@

# Install all Wilson dependencies preferring pre-compiled wheels
& $python -m pip install `
    -r (Join-Path $AppDir "requirements.txt") `
    --prefer-binary `
    --no-warn-script-location
