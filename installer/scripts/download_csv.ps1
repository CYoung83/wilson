param([string]$AppDir)

$url  = "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/bulk-data/citations-2026-03-31.csv.bz2"
$dest = Join-Path $AppDir "data\citations-2026-03-31.csv.bz2"

New-Item -ItemType Directory -Force -Path (Join-Path $AppDir "data") | Out-Null
Invoke-WebRequest -Uri $url -OutFile $dest
