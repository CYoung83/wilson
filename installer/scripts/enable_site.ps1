param([string]$AppDir)

$pythonDir = Join-Path $AppDir "python"
$pthFile   = Get-ChildItem $pythonDir -Filter "python*._pth" | Select-Object -First 1

if (-not $pthFile) {
    Write-Error "No ._pth file found in $pythonDir"
    exit 1
}

$content = Get-Content $pthFile.FullName -Raw
$content = $content -replace "#import site", "import site"
Set-Content $pthFile.FullName $content -NoNewline
