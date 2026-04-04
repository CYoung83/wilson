# Settings Panel Implementation Plan

> **For agentic workers:** Read CLAUDE.md before starting. You are a code execution agent. Do not plan, brainstorm, or load design skills. Execute each task exactly as specified, run tests, commit, stop.

**Goal:** Add a persistent settings panel to Wilson accessible from both index.html and upload.html. Client-side settings (theme, font size, density, show/hide log) persist to localStorage. Server-side settings (Ollama host, model, CourtListener token) write to .env and update running server state.

**Critical constraints:**
- Do NOT use sse_starlette
- Do NOT use Unicode in print() calls
- Do NOT commit to main -- all commits go to feature/settings-panel
- Every function needs a docstring
- Read only the files needed for each task

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `api.py` | 4 new endpoints, write_env_value helper |
| Modify | `templates/index.html` | Gear icon, settings drawer, CSS vars, theme system |
| Modify | `templates/upload.html` | Same gear icon, same drawer, same CSS vars |
| Create | `tests/test_settings.py` | Unit tests for all 4 endpoints |

---

## Task 0: Create Feature Branch

- [ ] **Step 1: Create and switch to feature branch**

```powershell
git checkout main
git pull
git checkout -b feature/settings-panel
```

- [ ] **Step 2: Verify**

```powershell
git branch
```

Expected: `* feature/settings-panel`

---

## Task 1: Settings API Endpoints

**Files:**
- Modify: `api.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_settings.py`:

```python
"""
Tests for Wilson settings panel API endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock


def test_get_ollama_models_available():
    """GET /settings/ollama-models returns model list when Ollama is available."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen3.5:35b"},
            {"name": "llama3:latest"}
        ]
    }
    with patch("api.http_requests.get", return_value=mock_resp):
        response = client.get("/settings/ollama-models")
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    assert "current" in data
    assert "ollama_available" in data
    assert data["ollama_available"] is True
    assert "qwen3.5:35b" in data["models"]


def test_get_ollama_models_unavailable():
    """GET /settings/ollama-models returns empty list when Ollama is unavailable."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    with patch("api.http_requests.get", side_effect=Exception("connection refused")):
        response = client.get("/settings/ollama-models")
    assert response.status_code == 200
    data = response.json()
    assert data["ollama_available"] is False
    assert data["models"] == []


def test_post_ollama_model_valid():
    """POST /settings/ollama-model updates model and returns success."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    with patch("api.write_env_value", return_value=True):
        response = client.post(
            "/settings/ollama-model",
            json={"model": "llama3:latest"}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["model"] == "llama3:latest"


def test_post_ollama_host_test_only():
    """POST /settings/ollama-host with save=false tests without persisting."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}]}
    with patch("api.http_requests.get", return_value=mock_resp):
        response = client.post(
            "/settings/ollama-host",
            json={"host": "http://localhost:11434", "save": False}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True


def test_post_courtlistener_token_valid():
    """POST /settings/courtlistener-token validates token against CL API."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("api.http_requests.get", return_value=mock_resp):
        response = client.post(
            "/settings/courtlistener-token",
            json={"token": "abc123", "save": False}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True


def test_post_courtlistener_token_invalid():
    """POST /settings/courtlistener-token returns valid=False for bad token."""
    from fastapi.testclient import TestClient
    from api import app
    client = TestClient(app)
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    with patch("api.http_requests.get", return_value=mock_resp):
        response = client.post(
            "/settings/courtlistener-token",
            json={"token": "badtoken", "save": False}
        )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False


def test_write_env_value_updates_existing_key():
    """write_env_value updates an existing key in .env content."""
    from api import write_env_value
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env',
                                     delete=False) as f:
        f.write("OLLAMA_MODEL=llama3\nCOURTLISTENER_TOKEN=abc\n")
        tmp_path = f.name
    try:
        with patch("api.ENV_PATH", tmp_path):
            result = write_env_value("OLLAMA_MODEL", "qwen3.5:35b")
        assert result is True
        content = open(tmp_path).read()
        assert "OLLAMA_MODEL=qwen3.5:35b" in content
        assert "OLLAMA_MODEL=llama3" not in content
    finally:
        os.unlink(tmp_path)
```

- [ ] **Step 2: Run tests -- verify they fail**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_settings.py -v 2>&1 | Select-Object -Last 15
```

Expected: ImportError or similar -- endpoints do not exist yet.

- [ ] **Step 3: Add write_env_value helper and Pydantic models to api.py**

Find the section in `api.py` where Pydantic models are defined (near `class VerifyRequest`).
Add after the existing models:

```python
class OllamaModelRequest(BaseModel):
    model: str

class OllamaHostRequest(BaseModel):
    host: str
    save: bool = False

class CourtListenerTokenRequest(BaseModel):
    token: str
    save: bool = False
```

Find the module-level constants section (near `CASE_NAME_MATCH_THRESHOLD`).
Add:

```python
# Path to .env file -- resolved relative to this script for portability
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
```

Add this function after `fetch_cluster_blocked`:

```python
def write_env_value(key: str, value: str) -> bool:
    """
    Update a single key=value pair in the .env file.

    If the key exists, replaces its value in-place.
    If the key does not exist, appends it.
    Never raises -- returns False on any error.

    Args:
        key: environment variable name (e.g. "OLLAMA_MODEL")
        value: new value to set

    Returns:
        True on success, False on any error
    """
    try:
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []

        found = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                new_lines.append(f"{key}={value}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            new_lines.append(f"{key}={value}\n")

        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        return True
    except Exception as e:
        print(f"write_env_value failed for {key}: {e}")
        return False
```

- [ ] **Step 4: Add the 4 settings endpoints to api.py**

Add after the `/health` endpoint:

```python
@app.get("/settings/ollama-models")
async def get_ollama_models():
    """
    Return available Ollama models by querying the configured Ollama instance.

    Proxies to OLLAMA_HOST/api/tags to avoid CORS issues in the browser.
    Returns empty list with ollama_available=False if Ollama is unreachable.
    """
    try:
        resp = http_requests.get(
            f"{OLLAMA_HOST}/api/tags",
            timeout=5
        )
        if resp.status_code == 200:
            models = [m["name"] for m in resp.json().get("models", [])]
            return {
                "models": models,
                "current": OLLAMA_MODEL,
                "ollama_available": True
            }
        return {"models": [], "current": OLLAMA_MODEL, "ollama_available": False}
    except Exception:
        return {"models": [], "current": OLLAMA_MODEL, "ollama_available": False}


@app.post("/settings/ollama-model")
async def update_ollama_model(request: OllamaModelRequest):
    """
    Update the active Ollama model in memory and persist to .env.

    Does not restart the server -- the new model takes effect on the
    next Phase 3 coherence check call.

    Args:
        request: OllamaModelRequest with model name

    Returns:
        success bool and updated model name
    """
    global OLLAMA_MODEL
    OLLAMA_MODEL = request.model
    write_env_value("OLLAMA_MODEL", request.model)
    return {"success": True, "model": request.model}


@app.post("/settings/ollama-host")
async def update_ollama_host(request: OllamaHostRequest):
    """
    Test and optionally update the Ollama host.

    If save=False, tests the connection without persisting.
    If save=True, tests the connection, updates OLLAMA_HOST global,
    and writes to .env.

    Args:
        request: OllamaHostRequest with host URL and save flag

    Returns:
        success bool, connected bool, available models list
    """
    global OLLAMA_HOST
    try:
        resp = http_requests.get(
            f"{request.host}/api/tags",
            timeout=5
        )
        connected = resp.status_code == 200
        models = []
        if connected:
            models = [m["name"] for m in resp.json().get("models", [])]
    except Exception as e:
        return {
            "success": False,
            "host": request.host,
            "connected": False,
            "models": [],
            "error": f"Cannot reach Ollama at {request.host}"
        }

    if request.save and connected:
        OLLAMA_HOST = request.host
        write_env_value("OLLAMA_HOST", request.host)

    return {
        "success": connected,
        "host": request.host,
        "connected": connected,
        "models": models
    }


@app.post("/settings/courtlistener-token")
async def update_courtlistener_token(request: CourtListenerTokenRequest):
    """
    Validate a CourtListener API token and optionally persist it.

    If save=False, validates without persisting.
    If save=True, validates, updates CL_TOKEN and CL_HEADERS globals,
    and writes to .env.

    Validation: GET to CourtListener API root with the token.
    200 = valid. Anything else = invalid.

    Args:
        request: CourtListenerTokenRequest with token and save flag

    Returns:
        success bool and valid bool
    """
    global CL_TOKEN, CL_HEADERS
    try:
        resp = http_requests.get(
            "https://www.courtlistener.com/api/rest/v4/",
            headers={"Authorization": f"Token {request.token}"},
            timeout=8
        )
        valid = resp.status_code == 200
    except Exception:
        return {"success": False, "valid": False}

    if request.save and valid:
        CL_TOKEN = request.token
        CL_HEADERS = {"Authorization": f"Token {CL_TOKEN}"}
        write_env_value("COURTLISTENER_TOKEN", request.token)

    return {"success": True, "valid": valid}
```

- [ ] **Step 5: Run tests -- verify they pass**

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_settings.py -v
```

Expected: 7 passed.

- [ ] **Step 6: Run full test suite**

```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: All existing tests plus 7 new tests pass.

- [ ] **Step 7: Commit**

```powershell
git add api.py tests/test_settings.py
git commit -m "feat: settings panel API endpoints and write_env_value helper"
```

---

## Task 2: CSS Custom Properties + Theme System in index.html

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Add CSS custom properties and theme definitions**

In `templates/index.html`, find the opening `<style>` tag and add immediately
after it (before any existing CSS):

```css
/* ── Theme system ────────────────────────────────────────────────── */
:root {
    --bg: #0a0a0a;
    --bg-card: #111;
    --bg-elevated: #161616;
    --text: #e0e0e0;
    --text-muted: #888;
    --border: #252525;
    --accent: #4caf50;
    --accent-dark: #0d2a0d;
    --accent-border: #1a4a1a;
    --accent-warn: #ff9800;
    --accent-warn-dark: #4a3a1a;
    --accent-err: #f44336;
    --spacing: 1rem;
}
[data-theme="light"] {
    --bg: #f5f5f5;
    --bg-card: #fff;
    --bg-elevated: #f0f0f0;
    --text: #1a1a1a;
    --text-muted: #666;
    --border: #ddd;
    --accent: #2e7d32;
    --accent-dark: #e8f5e9;
    --accent-border: #a5d6a7;
    --accent-warn: #e65100;
    --accent-warn-dark: #fff3e0;
    --accent-err: #c62828;
    --spacing: 1rem;
}
[data-theme="high-contrast"] {
    --bg: #000;
    --bg-card: #000;
    --bg-elevated: #111;
    --text: #fff;
    --text-muted: #ccc;
    --border: #fff;
    --accent: #0f0;
    --accent-dark: #001100;
    --accent-border: #0f0;
    --accent-warn: #ff0;
    --accent-warn-dark: #111100;
    --accent-err: #f00;
    --spacing: 1rem;
}
[data-theme="compact"] { --spacing: 0.5rem; }
```

- [ ] **Step 2: Add applySettings() to the top of the script section**

Find the `<script>` tag in `index.html`. Add as the very first thing inside it:

```javascript
// ── Settings: apply before render to prevent flash ──────────────────
(function applySettings() {
    const theme = localStorage.getItem('wilson-theme') || 'dark';
    const fontSize = localStorage.getItem('wilson-font-size') || 'medium';
    const density = localStorage.getItem('wilson-density') || 'comfortable';

    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.style.fontSize = {
        small: '13px', medium: '15px', large: '17px'
    }[fontSize] || '15px';
    document.documentElement.style.setProperty('--spacing',
        density === 'compact' ? '0.5rem' : '1rem'
    );
})();
```

- [ ] **Step 3: Add gear icon to header**

Find the `<header>` element in `index.html`. Add the gear button as the last
child of the header:

```html
<button id="settings-btn" onclick="openSettings()"
        aria-label="Open settings"
        style="background:none;border:none;cursor:pointer;color:var(--text-muted);
               padding:0.25rem;border-radius:4px;display:flex;align-items:center;">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <circle cx="12" cy="12" r="3"/>
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83
                 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1
                 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65
                 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65
                 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1
                 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82
                 l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9
                 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65
                 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2
                 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65
                 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0
                 0-1.51 1z"/>
    </svg>
</button>
```

- [ ] **Step 4: Add settings drawer HTML**

Add before the closing `</body>` tag:

```html
<!-- Settings overlay -->
<div id="settings-overlay" onclick="closeSettings()"
     style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:999;"></div>

<!-- Settings drawer -->
<div id="settings-drawer"
     style="position:fixed;top:0;right:-340px;width:320px;height:100vh;
            background:var(--bg-card);border-left:1px solid var(--border);
            transition:right 0.25s ease;z-index:1000;overflow-y:auto;
            padding:1.5rem;font-size:0.875rem;">

    <div style="display:flex;justify-content:space-between;align-items:center;
                margin-bottom:1.5rem;">
        <span style="font-weight:600;color:var(--text);">Settings</span>
        <button onclick="closeSettings()"
                style="background:none;border:none;cursor:pointer;
                       color:var(--text-muted);font-size:1.2rem;">&times;</button>
    </div>

    <!-- Appearance -->
    <div style="margin-bottom:1.5rem;">
        <div style="color:var(--text-muted);font-size:0.75rem;letter-spacing:0.08em;
                    text-transform:uppercase;margin-bottom:0.75rem;">Appearance</div>

        <div style="margin-bottom:0.75rem;">
            <label style="display:block;color:var(--text-muted);
                          margin-bottom:0.25rem;font-size:0.8rem;">Theme</label>
            <select id="s-theme" onchange="setSetting('theme',this.value)"
                    style="width:100%;background:var(--bg-elevated);
                           border:1px solid var(--border);border-radius:4px;
                           color:var(--text);padding:0.4rem;font-family:inherit;">
                <option value="dark">Dark</option>
                <option value="light">Light</option>
                <option value="high-contrast">High Contrast</option>
                <option value="auto">Auto (system)</option>
            </select>
        </div>

        <div style="margin-bottom:0.75rem;">
            <label style="display:block;color:var(--text-muted);
                          margin-bottom:0.25rem;font-size:0.8rem;">Font size</label>
            <select id="s-font" onchange="setSetting('font-size',this.value)"
                    style="width:100%;background:var(--bg-elevated);
                           border:1px solid var(--border);border-radius:4px;
                           color:var(--text);padding:0.4rem;font-family:inherit;">
                <option value="small">Small (13px)</option>
                <option value="medium">Medium (15px)</option>
                <option value="large">Large (17px)</option>
            </select>
        </div>

        <div style="margin-bottom:0.75rem;">
            <label style="display:block;color:var(--text-muted);
                          margin-bottom:0.25rem;font-size:0.8rem;">Density</label>
            <select id="s-density" onchange="setSetting('density',this.value)"
                    style="width:100%;background:var(--bg-elevated);
                           border:1px solid var(--border);border-radius:4px;
                           color:var(--text);padding:0.4rem;font-family:inherit;">
                <option value="comfortable">Comfortable</option>
                <option value="compact">Compact</option>
            </select>
        </div>
    </div>

    <!-- Display -->
    <div style="margin-bottom:1.5rem;">
        <div style="color:var(--text-muted);font-size:0.75rem;letter-spacing:0.08em;
                    text-transform:uppercase;margin-bottom:0.75rem;">Display</div>
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="color:var(--text);font-size:0.85rem;">Progress log</span>
            <label style="position:relative;display:inline-block;width:36px;height:20px;">
                <input type="checkbox" id="s-log" onchange="setSetting('show-log',this.checked?'true':'false')"
                       style="opacity:0;width:0;height:0;">
                <span id="s-log-track"
                      style="position:absolute;cursor:pointer;inset:0;
                             background:var(--border);border-radius:20px;
                             transition:0.2s;"></span>
            </label>
        </div>
    </div>

    <!-- Ollama -->
    <div style="margin-bottom:1.5rem;">
        <div style="color:var(--text-muted);font-size:0.75rem;letter-spacing:0.08em;
                    text-transform:uppercase;margin-bottom:0.75rem;">Ollama</div>

        <div style="margin-bottom:0.75rem;">
            <label style="display:block;color:var(--text-muted);
                          margin-bottom:0.25rem;font-size:0.8rem;">Host</label>
            <div style="display:flex;gap:0.4rem;">
                <input id="s-ollama-host" type="text" placeholder="http://localhost:11434"
                       style="flex:1;background:var(--bg-elevated);
                              border:1px solid var(--border);border-radius:4px;
                              color:var(--text);padding:0.4rem;font-family:inherit;
                              font-size:0.8rem;">
                <button onclick="testOllamaHost(false)"
                        style="padding:0.4rem 0.6rem;background:var(--bg-elevated);
                               border:1px solid var(--border);border-radius:4px;
                               color:var(--text-muted);cursor:pointer;font-size:0.8rem;">
                    Test
                </button>
                <button onclick="testOllamaHost(true)"
                        style="padding:0.4rem 0.6rem;background:var(--accent-dark);
                               border:1px solid var(--accent-border);border-radius:4px;
                               color:var(--accent);cursor:pointer;font-size:0.8rem;">
                    Save
                </button>
            </div>
            <div id="s-ollama-host-status" style="font-size:0.78rem;margin-top:0.25rem;
                                                   color:var(--text-muted);"></div>
        </div>

        <div style="margin-bottom:0.75rem;">
            <label style="display:block;color:var(--text-muted);
                          margin-bottom:0.25rem;font-size:0.8rem;">Model</label>
            <select id="s-ollama-model" onchange="updateOllamaModel(this.value)"
                    style="width:100%;background:var(--bg-elevated);
                           border:1px solid var(--border);border-radius:4px;
                           color:var(--text);padding:0.4rem;font-family:inherit;">
                <option value="">Loading...</option>
            </select>
            <div id="s-ollama-model-status" style="font-size:0.78rem;margin-top:0.25rem;
                                                    color:var(--text-muted);"></div>
        </div>
    </div>

    <!-- CourtListener -->
    <div style="margin-bottom:1.5rem;">
        <div style="color:var(--text-muted);font-size:0.75rem;letter-spacing:0.08em;
                    text-transform:uppercase;margin-bottom:0.75rem;">CourtListener</div>

        <div style="margin-bottom:0.75rem;">
            <label style="display:block;color:var(--text-muted);
                          margin-bottom:0.25rem;font-size:0.8rem;">API Token</label>
            <input id="s-cl-token" type="password" placeholder="Enter token"
                   style="width:100%;background:var(--bg-elevated);
                          border:1px solid var(--border);border-radius:4px;
                          color:var(--text);padding:0.4rem;font-family:inherit;
                          font-size:0.8rem;margin-bottom:0.4rem;">
            <div style="display:flex;gap:0.4rem;">
                <button onclick="verifyClToken(false)"
                        style="flex:1;padding:0.4rem;background:var(--bg-elevated);
                               border:1px solid var(--border);border-radius:4px;
                               color:var(--text-muted);cursor:pointer;font-size:0.8rem;">
                    Verify
                </button>
                <button onclick="verifyClToken(true)"
                        style="flex:1;padding:0.4rem;background:var(--accent-dark);
                               border:1px solid var(--accent-border);border-radius:4px;
                               color:var(--accent);cursor:pointer;font-size:0.8rem;">
                    Save
                </button>
            </div>
            <div id="s-cl-status" style="font-size:0.78rem;margin-top:0.25rem;
                                          color:var(--text-muted);"></div>
        </div>
    </div>

    <!-- Data -->
    <div style="margin-bottom:1.5rem;">
        <div style="color:var(--text-muted);font-size:0.75rem;letter-spacing:0.08em;
                    text-transform:uppercase;margin-bottom:0.75rem;">Data</div>
        <div id="s-csv-info" style="color:var(--text-muted);font-size:0.8rem;
                                     margin-bottom:0.5rem;">Loading...</div>
        <button onclick="checkCsvUpdate()"
                style="width:100%;padding:0.4rem;background:var(--bg-elevated);
                       border:1px solid var(--border);border-radius:4px;
                       color:var(--text-muted);cursor:pointer;font-size:0.8rem;">
            Check for updates
        </button>
        <div id="s-csv-update" style="font-size:0.78rem;margin-top:0.25rem;"></div>
    </div>

</div>
```

- [ ] **Step 5: Add settings JavaScript functions**

In the `<script>` section of `index.html`, after the `applySettings()` IIFE,
add:

```javascript
// ── Settings drawer ──────────────────────────────────────────────────
function openSettings() {
    document.getElementById('settings-drawer').style.right = '0';
    document.getElementById('settings-overlay').style.display = 'block';
    loadSettingsValues();
}

function closeSettings() {
    document.getElementById('settings-drawer').style.right = '-340px';
    document.getElementById('settings-overlay').style.display = 'none';
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') closeSettings();
});

function setSetting(key, value) {
    localStorage.setItem('wilson-' + key, value);
    applySettings();
    // Sync select elements to current values
    syncSettingSelects();
}

function syncSettingSelects() {
    const theme = localStorage.getItem('wilson-theme') || 'dark';
    const font = localStorage.getItem('wilson-font-size') || 'medium';
    const density = localStorage.getItem('wilson-density') || 'comfortable';
    const showLog = localStorage.getItem('wilson-show-log') !== 'false';

    const tEl = document.getElementById('s-theme');
    const fEl = document.getElementById('s-font');
    const dEl = document.getElementById('s-density');
    const lEl = document.getElementById('s-log');

    if (tEl) tEl.value = theme;
    if (fEl) fEl.value = font;
    if (dEl) dEl.value = density;
    if (lEl) lEl.checked = showLog;
}

function loadSettingsValues() {
    syncSettingSelects();

    // Load Ollama models
    fetch('/settings/ollama-models')
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById('s-ollama-model');
            if (!sel) return;
            sel.innerHTML = '';
            if (!data.ollama_available) {
                sel.innerHTML = '<option value="">Ollama not connected</option>';
                sel.disabled = true;
                return;
            }
            sel.disabled = false;
            data.models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.textContent = m;
                if (m === data.current) opt.selected = true;
                sel.appendChild(opt);
            });
            // Set host field
            const hostEl = document.getElementById('s-ollama-host');
            if (hostEl) hostEl.placeholder = 'http://localhost:11434';
        })
        .catch(() => {
            const sel = document.getElementById('s-ollama-model');
            if (sel) sel.innerHTML = '<option>Ollama unavailable</option>';
        });

    // Load CSV info from health endpoint
    fetch('/health')
        .then(r => r.json())
        .then(data => {
            const el = document.getElementById('s-csv-info');
            if (!el) return;
            const phase = data.phases && data.phases.phase1_offline;
            if (phase && phase.available) {
                el.innerHTML = phase.csv_path
                    ? phase.csv_path.split(/[/\\]/).pop() +
                      '<br>' + (phase.record_count || 0).toLocaleString() + ' records'
                    : 'CSV configured';
            } else {
                el.textContent = 'No CSV configured';
            }
            // CSV update status
            const upd = document.getElementById('s-csv-update');
            if (upd && data.csv_update && data.csv_update.available) {
                upd.style.color = 'var(--accent-warn)';
                upd.textContent = 'Update available: ' + (data.csv_update.latest_filename || '');
            }
        })
        .catch(() => {});
}

function updateOllamaModel(model) {
    if (!model) return;
    const statusEl = document.getElementById('s-ollama-model-status');
    if (statusEl) statusEl.textContent = 'Saving...';
    fetch('/settings/ollama-model', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({model})
    })
    .then(r => r.json())
    .then(data => {
        if (statusEl) {
            statusEl.style.color = data.success ? 'var(--accent)' : 'var(--accent-err)';
            statusEl.textContent = data.success ? 'Model updated' : 'Update failed';
        }
    })
    .catch(() => { if (statusEl) statusEl.textContent = 'Error'; });
}

function testOllamaHost(save) {
    const hostEl = document.getElementById('s-ollama-host');
    const statusEl = document.getElementById('s-ollama-host-status');
    const host = hostEl ? hostEl.value.trim() : '';
    if (!host) { if (statusEl) statusEl.textContent = 'Enter a host URL'; return; }
    if (statusEl) statusEl.textContent = save ? 'Saving...' : 'Testing...';
    fetch('/settings/ollama-host', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({host, save})
    })
    .then(r => r.json())
    .then(data => {
        if (statusEl) {
            statusEl.style.color = data.connected ? 'var(--accent)' : 'var(--accent-err)';
            statusEl.textContent = data.connected
                ? (save ? 'Saved -- ' : '') + 'Connected (' + (data.models||[]).length + ' models)'
                : data.error || 'Cannot connect';
        }
    })
    .catch(() => { if (statusEl) statusEl.textContent = 'Request failed'; });
}

function verifyClToken(save) {
    const tokenEl = document.getElementById('s-cl-token');
    const statusEl = document.getElementById('s-cl-status');
    const token = tokenEl ? tokenEl.value.trim() : '';
    if (!token) { if (statusEl) statusEl.textContent = 'Enter a token'; return; }
    if (statusEl) statusEl.textContent = save ? 'Saving...' : 'Verifying...';
    fetch('/settings/courtlistener-token', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({token, save})
    })
    .then(r => r.json())
    .then(data => {
        if (statusEl) {
            statusEl.style.color = data.valid ? 'var(--accent)' : 'var(--accent-err)';
            statusEl.textContent = data.valid
                ? (save ? 'Saved -- ' : '') + 'Token valid'
                : 'Token invalid';
        }
    })
    .catch(() => { if (statusEl) statusEl.textContent = 'Request failed'; });
}

function checkCsvUpdate() {
    const el = document.getElementById('s-csv-update');
    if (el) el.textContent = 'Checking...';
    fetch('/health')
        .then(r => r.json())
        .then(data => {
            if (!el) return;
            if (data.csv_update && data.csv_update.available) {
                el.style.color = 'var(--accent-warn)';
                el.textContent = 'Update available: ' + (data.csv_update.latest_filename || '');
            } else {
                el.style.color = 'var(--accent)';
                el.textContent = 'CSV is up to date';
            }
        })
        .catch(() => { if (el) el.textContent = 'Check failed'; });
}
```

- [ ] **Step 6: Run tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: All tests pass. (No new tests for HTML changes -- verified manually.)

- [ ] **Step 7: Commit**

```powershell
git add templates/index.html
git commit -m "feat: settings panel UI -- gear icon, drawer, theme system, all settings controls in index.html"
```

---

## Task 3: Apply Settings Panel to upload.html

**Files:**
- Modify: `templates/upload.html`

- [ ] **Step 1: Copy CSS custom properties block**

In `upload.html`, find the opening `<style>` tag. Add the same CSS custom
properties block from Task 2 Step 1 immediately after it. (Exact same block --
copy verbatim from index.html.)

- [ ] **Step 2: Copy applySettings() IIFE**

Find the `<script>` tag in `upload.html`. Add the same `applySettings()` IIFE
from Task 2 Step 2 as the very first thing inside it.

- [ ] **Step 3: Copy gear icon to upload.html header**

Find the `<header>` element in `upload.html`. Add the same gear icon button
from Task 2 Step 3 as the last child of the header.

- [ ] **Step 4: Copy settings drawer HTML**

Add the same settings overlay and settings drawer HTML from Task 2 Step 4
before the closing `</body>` tag in `upload.html`.

- [ ] **Step 5: Copy settings JavaScript functions**

Add the same settings JavaScript functions from Task 2 Step 5 after the
`applySettings()` IIFE in `upload.html`'s `<script>` section.

- [ ] **Step 6: Run tests**

```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 7: Commit**

```powershell
git add templates/upload.html
git commit -m "feat: apply settings panel to upload.html -- theme system and drawer"
```

---

## Task 4: Smoke Test and Push

- [ ] **Step 1: Run full test suite**

```powershell
.\venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify branch**

```powershell
git branch
```

Expected: `* feature/settings-panel`

- [ ] **Step 3: Push**

```powershell
git push -u origin feature/settings-panel
```

- [ ] **Step 4: Report**

Report:
- Total tests passing
- Commit hashes for Tasks 1-3
- Push confirmation
- Any issues encountered

---

## Completion Checklist

- [ ] Branch `feature/settings-panel` created
- [ ] `write_env_value()` added to `api.py` and tested
- [ ] 4 settings endpoints added to `api.py` and tested
- [ ] CSS custom properties in both `index.html` and `upload.html`
- [ ] `applySettings()` runs before render on both pages
- [ ] Gear icon in header of both pages
- [ ] Settings drawer with all controls in both pages
- [ ] All settings JavaScript functions in both pages
- [ ] All tests pass
- [ ] Feature branch pushed to GitHub
