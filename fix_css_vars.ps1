# Wilson CSS Variable Migration
# Replaces critical hardcoded hex colors with CSS custom properties
# Run from C:\wilson\v0.1.0

param(
    [string]$File
)

if (-not $File) {
    Write-Error "Usage: .\fix_css_vars.ps1 -File templates\index.html"
    exit 1
}

if (-not (Test-Path $File)) {
    Write-Error "File not found: $File"
    exit 1
}

$content = Get-Content $File -Raw

# Track replacement count
$count = 0

function Replace-All {
    param($old, $new)
    $script:count += ([regex]::Matches($script:content, [regex]::Escape($old))).Count
    $script:content = $script:content.Replace($old, $new)
}

# ── Body and page backgrounds ─────────────────────────────────────────
Replace-All "background: #0a0a0a"        "background: var(--bg)"
Replace-All "background: #0A0A0A"        "background: var(--bg)"
Replace-All "background-color: #0a0a0a"  "background-color: var(--bg)"

# ── Card / elevated backgrounds ───────────────────────────────────────
Replace-All "background: #111111"        "background: var(--bg-card)"
Replace-All "background: #111"           "background: var(--bg-card)"
Replace-All "background: #161616"        "background: var(--bg-elevated)"
Replace-All "background: #1a1a1a"        "background: var(--bg-elevated)"
Replace-All "background-color: #111"     "background-color: var(--bg-card)"
Replace-All "background-color: #161616"  "background-color: var(--bg-elevated)"
Replace-All "background:#111"            "background:var(--bg-card)"
Replace-All "background:#161616"         "background:var(--bg-elevated)"
Replace-All "background:#0a0a0a"         "background:var(--bg)"

# ── Text colors ───────────────────────────────────────────────────────
Replace-All "color: #e0e0e0"             "color: var(--text)"
Replace-All "color: #E0E0E0"             "color: var(--text)"
Replace-All "color: #888888"             "color: var(--text-muted)"
Replace-All "color: #888"                "color: var(--text-muted)"
Replace-All "color: #999"                "color: var(--text-muted)"
Replace-All "color:#e0e0e0"              "color:var(--text)"
Replace-All "color:#888"                 "color:var(--text-muted)"

# ── Border colors ─────────────────────────────────────────────────────
Replace-All "border: 1px solid #252525"     "border: 1px solid var(--border)"
Replace-All "border: 1px solid #333"        "border: 1px solid var(--border)"
Replace-All "border: 1px solid #2a2a2a"     "border: 1px solid var(--border)"
Replace-All "border-color: #252525"         "border-color: var(--border)"
Replace-All "border-bottom: 1px solid #252525" "border-bottom: 1px solid var(--border)"
Replace-All "border-top: 1px solid #252525"    "border-top: 1px solid var(--border)"
Replace-All "1px solid #252525"             "1px solid var(--border)"
Replace-All "1px solid #333333"             "1px solid var(--border)"
Replace-All "1px solid #333"                "1px solid var(--border)"

# ── Inline style attributes (common patterns) ─────────────────────────
Replace-All "background:#0a0a0a"         "background:var(--bg)"
Replace-All "color:#e0e0e0"              "color:var(--text)"
Replace-All "color:#888"                 "color:var(--text-muted)"
Replace-All "border:1px solid #252525"   "border:1px solid var(--border)"
Replace-All "border:1px solid #333"      "border:1px solid var(--border)"

# Write back
Set-Content $File $content -NoNewline

Write-Host "Done. Made $count replacements in $File"
