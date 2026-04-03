param([string]$AppDir)

$envFile    = Join-Path $AppDir ".env"
$envExample = Join-Path $AppDir ".env.example"
$csvPath    = Join-Path $AppDir "data\citations-2026-03-31.csv"

# Create .env from example if not present
if (-not (Test-Path $envFile)) {
    Copy-Item $envExample $envFile
}

$content = Get-Content $envFile -Raw

# Set self-contained CSV path
$content = $content -replace "CITATIONS_CSV=.*", "CITATIONS_CSV=$csvPath"

# Auto-detect Ollama and set model
$ollamaHost = "http://localhost:11434"
$detectedModel = $null

try {
    $response = Invoke-RestMethod -Uri "$ollamaHost/api/tags" -TimeoutSec 3 -ErrorAction Stop
    $models = $response.models | ForEach-Object { $_.name }
    if ($models) {
        $detectedModel = $models | Select-Object -First 1
    }
} catch {}

if ($detectedModel) {
    $content = $content -replace "OLLAMA_HOST=.*",  "OLLAMA_HOST=$ollamaHost"
    $content = $content -replace "OLLAMA_MODEL=.*", "OLLAMA_MODEL=$detectedModel"
} else {
    # Ollama not found locally -- clear host so Wilson reports Phase 3 offline cleanly
    $content = $content -replace "OLLAMA_HOST=.*",  "OLLAMA_HOST=http://localhost:11434"
    $content = $content -replace "OLLAMA_MODEL=.*", "OLLAMA_MODEL="
}

Set-Content $envFile $content -NoNewline
