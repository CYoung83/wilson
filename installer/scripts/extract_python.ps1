param([string]$AppDir)

$zip  = Join-Path $AppDir "installer\tmp\python-3.13.12-embed-amd64.zip"
$dest = Join-Path $AppDir "python"

if (-not (Test-Path $zip)) {
    Write-Error "Python zip not found at: $zip"
    exit 1
}

New-Item -ItemType Directory -Force -Path $dest | Out-Null
Expand-Archive -Path $zip -DestinationPath $dest -Force

if (-not (Test-Path (Join-Path $dest "python.exe"))) {
    Write-Error "Extraction completed but python.exe not found in $dest"
    exit 1
}
