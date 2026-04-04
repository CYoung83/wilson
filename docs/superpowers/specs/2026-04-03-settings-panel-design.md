# Wilson Settings Panel -- Design Spec
**Date:** 2026-04-03
**Status:** Approved
**Version target:** v0.1.0

---

## Purpose

Add a persistent settings panel accessible from both `index.html` and
`upload.html`. Settings fall into two categories:

**Client-side only** (localStorage, no server restart):
- Theme, font size, layout density

**Server-side** (write to `.env`, update running server state):
- Ollama host, Ollama model, CourtListener token

The settings panel is a slide-in drawer from the right side of the screen,
triggered by a gear icon in the header. It is accessible from both pages.

---

## Architecture

### New endpoints (added to `api.py`)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/settings/ollama-models` | Proxy Ollama /api/tags -- returns available model names |
| POST | `/settings/ollama-model` | Update OLLAMA_MODEL in memory and .env |
| POST | `/settings/ollama-host` | Update OLLAMA_HOST in memory and .env, test connection |
| POST | `/settings/courtlistener-token` | Validate token against CL API, update in .env |

### Files modified

| File | Changes |
|------|---------|
| `api.py` | 4 new endpoints, helper to write .env values |
| `templates/index.html` | Gear icon in header, settings drawer, theme/font/density CSS vars |
| `templates/upload.html` | Same gear icon, same drawer, same CSS vars |
| `tests/test_settings.py` | Unit tests for all 4 endpoints |

---

## Settings Catalog

### Theme
- Options: Dark (default) | Light | High Contrast | Auto
- Storage: `localStorage["wilson-theme"]`
- Implementation: `data-theme` attribute on `<html>` element
- CSS custom properties per theme:

```css
[data-theme="dark"] {
    --bg: #0a0a0a;
    --bg-card: #111;
    --text: #e0e0e0;
    --text-muted: #888;
    --border: #252525;
    --accent: #4caf50;
    --accent-warn: #ff9800;
    --accent-err: #f44336;
}
[data-theme="light"] {
    --bg: #f5f5f5;
    --bg-card: #fff;
    --text: #1a1a1a;
    --text-muted: #666;
    --border: #ddd;
    --accent: #2e7d32;
    --accent-warn: #e65100;
    --accent-err: #c62828;
}
[data-theme="high-contrast"] {
    --bg: #000;
    --bg-card: #000;
    --text: #fff;
    --text-muted: #ccc;
    --border: #fff;
    --accent: #0f0;
    --accent-warn: #ff0;
    --accent-err: #f00;
}
```

Auto mode: detect `prefers-color-scheme` on load, apply dark or light accordingly.
On explicit selection, override the OS preference and store in localStorage.

### Font size
- Options: Small (13px) | Medium (15px, default) | Large (17px)
- Storage: `localStorage["wilson-font-size"]`
- Implementation: `font-size` on `<html>`, all other sizes use `rem`

### Layout density
- Options: Compact | Comfortable (default)
- Storage: `localStorage["wilson-density"]`
- Implementation: CSS variable `--spacing` -- 0.5rem (compact) or 1rem (comfortable)
- Affects padding on cards, phase blocks, form elements

### Ollama model selector
- Dropdown populated by GET `/settings/ollama-models`
- Shows all available models with current model highlighted
- On change: POST `/settings/ollama-model` with `{"model": "model-name"}`
- Shows spinner during update, green checkmark on success, red error on failure
- If Ollama unavailable, dropdown is disabled with note "Ollama not connected"

### Ollama host
- Editable text input, current value from server
- "Test" button: POST `/settings/ollama-host` with `{"host": "http://..."}` -- tests
  connection without saving
- "Save" button: saves and updates running server
- Shows connection status inline: green "Connected" or red "Cannot reach Ollama"

### CourtListener token
- Masked input (type="password")
- "Verify" button: POST `/settings/courtlistener-token` with `{"token": "..."}` --
  validates against CL API without saving
- "Save" button: saves and updates running server
- Shows validation status: green "Token valid" or red "Token invalid"

### CSV status (read-only)
- Displays current CSV path, record count, date from filename
- "Check for updates" button: triggers manual S3 check
- Shows amber notice if CSV_UPDATE_AVAILABLE is True

### Show/hide progress log
- Toggle: show the live SSE log lines during pipeline execution
- Storage: `localStorage["wilson-show-log"]`
- Default: shown

---

## UI Design

### Gear icon placement
In the header of both `index.html` and `upload.html`, add a gear icon button
on the right side of the header bar. Use a simple SVG gear icon, no external
dependencies.

```html
<button id="settings-btn" aria-label="Settings" onclick="openSettings()">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42
                 M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
    </svg>
</button>
```

### Drawer behavior
- Slides in from the right, 320px wide
- Dark overlay behind drawer (`rgba(0,0,0,0.5)`)
- Escape key closes it
- Click on overlay closes it
- No Save button for client-side settings -- apply immediately
- Explicit Save buttons only for server-side settings (token, host, model)

### Drawer structure
```
[X] Settings
─────────────────
APPEARANCE
  Theme        [Dark ▼]
  Font size    [Medium ▼]
  Density      [Comfortable ▼]

DISPLAY
  Progress log [Toggle ON]

OLLAMA
  Host         [http://localhost:11434] [Test] [Save]
  Model        [qwen3.5:35b ▼] (auto-saves on change)
  Status       ● Connected

COURTLISTENER
  Token        [••••••••••••] [Verify] [Save]
  Status       ● Valid

DATA
  CSV          citations-2026-03-31.csv
               18,116,834 records
               [Check for updates]
               ▲ Update available: citations-2026-04-01.csv (if applicable)
```

---

## New API Endpoints

### GET /settings/ollama-models

Returns available Ollama models by proxying to the configured OLLAMA_HOST.

Response:
```json
{
    "models": ["qwen3.5:35b", "llama3:latest", "nemotron-cascade-2:30b"],
    "current": "qwen3.5:35b",
    "ollama_available": true
}
```

On Ollama unavailable:
```json
{
    "models": [],
    "current": "qwen3.5:35b",
    "ollama_available": false
}
```

### POST /settings/ollama-model

Request: `{"model": "llama3:latest"}`

Updates `OLLAMA_MODEL` global in memory. Writes to `.env`. Does not restart server.

Response:
```json
{"success": true, "model": "llama3:latest"}
```

### POST /settings/ollama-host

Request: `{"host": "http://10.27.27.5:11434", "save": true}`

If `save=false`: test connection only, do not persist.
If `save=true`: test connection, update `OLLAMA_HOST` global, write to `.env`.

Response:
```json
{"success": true, "host": "http://10.27.27.5:11434", "connected": true, "models": ["qwen3.5:35b"]}
```

On connection failure:
```json
{"success": false, "host": "http://10.27.27.5:11434", "connected": false, "error": "Cannot reach Ollama at http://10.27.27.5:11434"}
```

### POST /settings/courtlistener-token

Request: `{"token": "abc123...", "save": true}`

If `save=false`: validate token against CL API, do not persist.
If `save=true`: validate, update `CL_TOKEN` and `CL_HEADERS` globals, write to `.env`.

Validation: GET `https://www.courtlistener.com/api/rest/v4/` with the token.
200 = valid. Anything else = invalid.

Response:
```json
{"success": true, "valid": true}
```

---

## `.env` Write Helper

A new `write_env_value(key, value)` function in `api.py`:
- Reads current `.env` file
- Finds the line matching `key=...` and replaces it
- If key not found, appends it
- Writes back atomically
- Never raises -- logs errors silently

```python
def write_env_value(key: str, value: str) -> bool:
    """
    Update a single key in the .env file.
    Returns True on success, False on any error.
    Thread-safe via file locking is not required for this use case
    (settings changes are infrequent and user-initiated).
    """
```

The `.env` file path is resolved relative to the script directory, not the
working directory, so it works regardless of where uvicorn is launched from.

---

## localStorage Schema

```javascript
// Applied on every page load before render
const DEFAULTS = {
    "wilson-theme": "dark",
    "wilson-font-size": "medium",   // 15px
    "wilson-density": "comfortable",
    "wilson-show-log": "true"
};

function applySettings() {
    const theme = localStorage.getItem("wilson-theme") || "dark";
    const fontSize = localStorage.getItem("wilson-font-size") || "medium";
    const density = localStorage.getItem("wilson-density") || "comfortable";

    document.documentElement.setAttribute("data-theme", theme);
    document.documentElement.style.fontSize = {
        small: "13px", medium: "15px", large: "17px"
    }[fontSize] || "15px";
    document.documentElement.style.setProperty("--spacing",
        density === "compact" ? "0.5rem" : "1rem"
    );
}

// Call immediately on load -- before page renders
applySettings();
```

---

## CSS Custom Properties Migration

Both `index.html` and `upload.html` currently use hardcoded hex values
throughout their CSS. As part of this feature, migrate the most impactful
values to CSS custom properties so themes work correctly.

Priority values to migrate:
- Background: `#0a0a0a` -> `var(--bg)`
- Card background: `#111` / `#161616` -> `var(--bg-card)`
- Text: `#e0e0e0` -> `var(--text)`
- Muted text: `#888` -> `var(--text-muted)`
- Border: `#252525` -> `var(--border)`
- Green accent: `#4caf50` -> `var(--accent)`
- Orange accent: `#ff9800` -> `var(--accent-warn)`
- Red accent: `#f44336` -> `var(--accent-err)`

Full migration of every hardcoded color is not required for v0.1.0 -- the
priority is ensuring the main backgrounds, text, and borders respond to
theme changes. Individual component colors (verdict badges etc.) can remain
hardcoded for now.

---

## Styling

The settings drawer uses the same CSS custom properties as the rest of the
page. The drawer itself has a slightly elevated background (`--bg-card`) to
distinguish it from the page background.

Drawer animation:
```css
#settings-drawer {
    position: fixed;
    top: 0;
    right: -340px;
    width: 320px;
    height: 100vh;
    background: var(--bg-card);
    border-left: 1px solid var(--border);
    transition: right 0.25s ease;
    z-index: 1000;
    overflow-y: auto;
    padding: 1.5rem;
}
#settings-drawer.open {
    right: 0;
}
#settings-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.5);
    z-index: 999;
}
#settings-overlay.open {
    display: block;
}
```

---

## Not in scope for v0.1.0

- Settings sync across browser tabs
- Export/import settings as JSON
- Per-page settings (same settings apply to both index and upload)
- Settings migration when keys change
- "Reset to defaults" button (can be added later)
