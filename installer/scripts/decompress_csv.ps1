param([string]$AppDir)

$python = Join-Path $AppDir "python\python.exe"
$src    = Join-Path $AppDir "data\citations-2026-03-31.csv.bz2"
$dst    = Join-Path $AppDir "data\citations-2026-03-31.csv"
$script = Join-Path $AppDir "installer\tmp\decompress.py"

Set-Content $script @"
import bz2, os, sys
src = sys.argv[1]
dst = sys.argv[2]
with bz2.open(src, 'rb') as fin, open(dst, 'wb') as fout:
    while True:
        chunk = fin.read(8 * 1024 * 1024)
        if not chunk:
            break
        fout.write(chunk)
os.remove(src)
"@ -Encoding UTF8

& $python $script $src $dst
Remove-Item $script -Force -ErrorAction SilentlyContinue
