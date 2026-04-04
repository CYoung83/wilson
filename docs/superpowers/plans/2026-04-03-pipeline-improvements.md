# Pipeline Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement three pipeline improvements: (1) respect CourtListener `blocked` flag by skipping Phase 2/3 for privacy-protected opinions, (2) add a name-based lookup confidence threshold with "did you mean?" suggestions, and (3) notify users when a newer bulk citation CSV is available on S3.

**Architecture:** All changes are in `api.py` and `coherence_check.py`. No new files required. Each improvement is independent and can be tested separately. All changes must work on both `/verify/stream` and `/batch/stream`.

**Critical constraints:**
- Do NOT use sse_starlette -- raw StreamingResponse with asyncio.sleep(0) only
- Do NOT use Unicode characters in print() calls -- Windows cp1252 will raise UnicodeEncodeError
- Do NOT commit directly to main -- create branch `feature/pipeline-improvements` first
- Every function needs a docstring
- Fail loudly with clear error messages

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `api.py` | blocked flag check, name confidence threshold, CSV update check on startup |
| Modify | `coherence_check.py` | blocked flag awareness |
| Create | `tests/test_pipeline_improvements.py` | Tests for all three improvements |

---

## Task 0: Create Feature Branch

**Files:** none

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feature/pipeline-improvements
```

- [ ] **Step 2: Verify branch**

```bash
git branch
```

Expected: `* feature/pipeline-improvements` is the active branch.

---

## Task 1: CourtListener `blocked` Flag Compliance

**Files:**
- Modify: `api.py`
- Create: `tests/test_pipeline_improvements.py`

**Why this matters:** CourtListener asks API users to respect their privacy
removal system. When someone requests de-indexing of a case, CourtListener sets
`blocked: true` on the cluster object. Wilson must not run Phase 2 or Phase 3
on these opinions. This is both an ethical requirement and good practice for
maintaining API access.

- [ ] **Step 1: Write failing tests**

Create `tests/test_pipeline_improvements.py`:

```python
"""
Tests for Wilson pipeline improvements:
- CourtListener blocked flag compliance
- Name-based lookup confidence threshold
- CSV update check notification
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Task 1: blocked flag compliance
# ---------------------------------------------------------------------------

def test_fetch_cluster_blocked_returns_true():
    """fetch_cluster_blocked returns True when cluster has blocked=True."""
    from api import fetch_cluster_blocked
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"blocked": True, "id": 111170}
    with patch("api.http_requests.get", return_value=mock_resp):
        result = fetch_cluster_blocked(111170)
    assert result is True


def test_fetch_cluster_blocked_returns_false():
    """fetch_cluster_blocked returns False when cluster has blocked=False."""
    from api import fetch_cluster_blocked
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"blocked": False, "id": 111170}
    with patch("api.http_requests.get", return_value=mock_resp):
        result = fetch_cluster_blocked(111170)
    assert result is False


def test_fetch_cluster_blocked_api_error_returns_false():
    """fetch_cluster_blocked returns False on API error -- do not block on uncertainty."""
    from api import fetch_cluster_blocked
    with patch("api.http_requests.get", side_effect=Exception("timeout")):
        result = fetch_cluster_blocked(111170)
    assert result is False


def test_fetch_cluster_blocked_missing_field_returns_false():
    """fetch_cluster_blocked returns False when blocked field is absent."""
    from api import fetch_cluster_blocked
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": 111170}
    with patch("api.http_requests.get", return_value=mock_resp):
        result = fetch_cluster_blocked(111170)
    assert result is False
```

- [ ] **Step 2: Run tests -- verify they fail**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_pipeline_improvements.py -k "blocked" -v 2>&1 | head -20
```

Expected: `ImportError` or `AttributeError` -- `fetch_cluster_blocked` does not exist yet.

- [ ] **Step 3: Add `fetch_cluster_blocked` to `api.py`**

Find the section of `api.py` where `lookup_citation_api` is defined. Add immediately after it:

```python
def fetch_cluster_blocked(cluster_id: int) -> bool:
    """
    Check whether a CourtListener cluster has been flagged for privacy protection.

    CourtListener allows individuals to request de-indexing of their cases.
    When blocked=True, Wilson skips Phase 2 and Phase 3 out of respect for
    that privacy request. On any API error, returns False (do not block on
    uncertainty -- better to over-verify than under-verify).

    Args:
        cluster_id: CourtListener cluster ID from Phase 1 verification

    Returns:
        True if the cluster is privacy-protected, False otherwise
    """
    try:
        resp = http_requests.get(
            f"https://www.courtlistener.com/api/rest/v4/clusters/{cluster_id}/",
            headers=CL_HEADERS,
            timeout=5
        )
        if resp.status_code == 200:
            return bool(resp.json().get("blocked", False))
        return False
    except Exception:
        return False
```

- [ ] **Step 4: Run blocked flag tests -- verify they pass**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_pipeline_improvements.py -k "blocked" -v
```

Expected: 4 passed.

- [ ] **Step 5: Integrate blocked check into `run_pipeline` in `api.py`**

In `run_pipeline`, find the section after `phase1_complete` yields EXISTS verdict
and before Phase 2 begins. Add the blocked check:

```python
    # After phase1_complete yields EXISTS -- check privacy protection before Phase 2/3
    if cluster_id:
        is_blocked = fetch_cluster_blocked(cluster_id)
        if is_blocked:
            yield make_event("phase1_complete", data={
                "verdict": "EXISTS",
                "cluster_id": cluster_id,
                "case_name": actual_case_name,
                "cited_name": cited_name,
                "match_pct": match_pct,
                "api_found": True,
                "local_csv": csv_stat,
                "privacy_protected": True,
                "message": (
                    f"Citation verified -- {actual_case_name} ({match_pct}% name match). "
                    f"This opinion has been flagged for privacy protection. "
                    f"Quote verification and coherence checking are not available."
                )
            })
            yield make_event("done", duration=round(time.time() - start_time, 2))
            return
```

Note: The existing `phase1_complete` EXISTS yield must be updated to include
`"privacy_protected": False` so the UI can check the field consistently:

```python
    yield make_event("phase1_complete", data={
        "verdict": "EXISTS",
        "cluster_id": cluster_id,
        "case_name": actual_case_name,
        "cited_name": cited_name,
        "match_pct": match_pct,
        "api_found": True,
        "local_csv": csv_stat,
        "privacy_protected": False,
        "message": f"Citation verified -- {actual_case_name} ({match_pct}% name match)"
    })
```

- [ ] **Step 6: Update UI in `index.html` to display privacy protection note**

In the `renderPhase1` JavaScript function, after building the detail grid,
add handling for the `privacy_protected` field:

```javascript
if (d.privacy_protected) {
    h += `<div class="reasoning" style="border-left-color: #4a3a1a; color: #ff9800;">
        This opinion has been flagged for privacy protection.
        Quote verification and coherence checking are not available for this citation.
    </div>`;
}
```

- [ ] **Step 7: Commit**

```bash
git add api.py templates/index.html tests/test_pipeline_improvements.py
git commit -m "feat: respect CourtListener blocked flag -- skip Phase 2/3 for privacy-protected opinions"
```

---

## Task 2: Name-Based Lookup Confidence Threshold

**Files:**
- Modify: `api.py`
- Modify: `tests/test_pipeline_improvements.py`

**Why this matters:** When a user types a truncated or informal case name
(e.g. "Daubert v. Merrell Dow" instead of the full "Daubert v. Merrell Dow
Pharmaceuticals, Inc."), the name-based fallback finds a real case but the
similarity score may be low enough to misidentify. Currently Wilson proceeds
with whatever the top result is. It should surface a "did you mean X?"
suggestion when confidence is low.

**Thresholds:**
- Name similarity < 60%: return `suggestion` event, do not proceed
- Name similarity >= 60%: proceed normally (fallback found something plausible)
- Note: this is separate from the MISATTRIBUTED threshold (75%). This is a
  pre-verification nudge in the fallback path only.

- [ ] **Step 1: Add tests**

Add to `tests/test_pipeline_improvements.py`:

```python
# ---------------------------------------------------------------------------
# Task 2: name-based lookup confidence threshold
# ---------------------------------------------------------------------------

def test_name_similarity_above_threshold_proceeds():
    """
    When name similarity >= 60%, fallback proceeds normally.
    Similarity between 'Daubert v. Merrell Dow' and
    'Daubert v. Merrell Dow Pharmaceuticals, Inc.' should be >= 60.
    """
    from rapidfuzz import fuzz
    user_input = "Daubert v. Merrell Dow"
    actual = "Daubert v. Merrell Dow Pharmaceuticals, Inc."
    score = fuzz.partial_ratio(user_input.lower(), actual.lower())
    assert score >= 60, f"Expected >= 60, got {score}"


def test_name_similarity_below_threshold_blocked():
    """
    When name similarity < 60%, the fallback should not proceed.
    Completely unrelated names should score below threshold.
    """
    from rapidfuzz import fuzz
    user_input = "Smith v. Jones"
    actual = "Daubert v. Merrell Dow Pharmaceuticals, Inc."
    score = fuzz.partial_ratio(user_input.lower(), actual.lower())
    assert score < 60, f"Expected < 60, got {score}"
```

- [ ] **Step 2: Run tests -- verify they pass**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_pipeline_improvements.py -k "threshold" -v
```

Expected: 2 passed. These tests verify the threshold logic is sound before
implementing it in the pipeline.

- [ ] **Step 3: Add `FALLBACK_CONFIDENCE_THRESHOLD` constant to `api.py`**

Near the top of `api.py`, after `CASE_NAME_MATCH_THRESHOLD = 75`, add:

```python
# Minimum similarity for name-based fallback to proceed without a "did you mean?" prompt
# Lower than CASE_NAME_MATCH_THRESHOLD (75) -- this is a pre-verification nudge,
# not a verdict threshold
FALLBACK_CONFIDENCE_THRESHOLD = 60
```

- [ ] **Step 4: Add `suggestion` event to `run_pipeline` in `api.py`**

In `run_pipeline`, find the name-based fallback section where `lookup_by_name`
is called and citations are extracted from the fallback result. After extracting
`fb_full_citation` and before proceeding, add:

```python
        if fb_found and fb_full_citation:
            # Check confidence before proceeding -- low similarity means
            # Wilson may have found the wrong case
            from rapidfuzz import fuzz as _fuzz
            fallback_similarity = _fuzz.partial_ratio(
                citation_text.lower(),
                (fb_case_name or "").lower()
            )
            if fallback_similarity < FALLBACK_CONFIDENCE_THRESHOLD:
                yield make_event("suggestion", data={
                    "user_input": citation_text,
                    "suggested_citation": fb_full_citation,
                    "suggested_name": fb_case_name,
                    "similarity": round(fallback_similarity),
                    "message": (
                        f"Wilson found a case that may match: {fb_case_name} "
                        f"({fb_full_citation}). Similarity to your input: "
                        f"{round(fallback_similarity)}%. "
                        f"Please verify this is the correct case before proceeding."
                    )
                })
                yield make_event("done", duration=round(time.time() - start_time, 2))
                return

            # Similarity acceptable -- proceed with fallback citation
            citations = get_citations(fb_full_citation)
            used_fallback = True
            fallback_citation = fb_full_citation
            yield make_event("status", message=f"Found via name search: {fb_full_citation}")
```

- [ ] **Step 5: Handle `suggestion` event in `index.html` UI**

In the JavaScript event handler loop in `index.html`, add handling for the
`suggestion` event type:

```javascript
else if (t === 'suggestion') {
    setProgress(100, false);
    stopTimer(e.duration);
    results.innerHTML += `<div class="phase-block" style="border-color: #4a3a1a;">
        <div class="phase-header">
            <span class="phase-label">Name Lookup -- Low Confidence</span>
            <span class="verdict v-orange">DID YOU MEAN?</span>
        </div>
        <div class="reasoning">
            ${e.data.message}
        </div>
        <div style="margin-top: 0.75rem; display: flex; gap: 0.5rem;">
            <button onclick="document.getElementById('citation').value = '${e.data.suggested_citation}'; resetForm(); document.getElementById('citation').value = '${e.data.suggested_citation}';"
                style="flex: 1; padding: 0.5rem; background: #0d2a0d; border: 1px solid #1a4a1a; border-radius: 4px; color: #4caf50; cursor: pointer; font-family: inherit; font-size: 0.82rem;">
                Use "${e.data.suggested_citation}"
            </button>
            <button onclick="resetForm();"
                style="flex: 0 0 auto; padding: 0.5rem 1rem; background: #161616; border: 1px solid #252525; border-radius: 4px; color: #888; cursor: pointer; font-family: inherit; font-size: 0.82rem;">
                Start over
            </button>
        </div>
    </div>`;
    document.getElementById('results-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}
```

- [ ] **Step 6: Commit**

```bash
git add api.py templates/index.html tests/test_pipeline_improvements.py
git commit -m "feat: name-based fallback confidence threshold with did-you-mean suggestion"
```

---

## Task 3: CSV Update Check Notification

**Files:**
- Modify: `api.py`
- Modify: `templates/index.html`
- Modify: `tests/test_pipeline_improvements.py`

**Why this matters:** The bulk citation CSV is dated (e.g. citations-2026-03-31.csv).
CourtListener publishes new versions periodically. Wilson should notify users
when a newer file is available without auto-downloading.

**Implementation approach:**
- On server startup, parse the date from the configured CSV filename
- Check S3 bucket for files newer than that date
- Store result in a module-level flag
- `/health` endpoint exposes the flag
- UI status bar pill changes color when update is available

- [ ] **Step 1: Add tests**

Add to `tests/test_pipeline_improvements.py`:

```python
# ---------------------------------------------------------------------------
# Task 3: CSV update check
# ---------------------------------------------------------------------------

def test_parse_csv_date_valid():
    """parse_csv_date extracts date from standard filename."""
    from api import parse_csv_date
    from datetime import date
    result = parse_csv_date("citations-2026-03-31.csv")
    assert result == date(2026, 3, 31)


def test_parse_csv_date_full_path():
    """parse_csv_date handles full file paths."""
    from api import parse_csv_date
    from datetime import date
    result = parse_csv_date("/var/data/citations-2025-12-01.csv")
    assert result == date(2025, 12, 1)


def test_parse_csv_date_no_date_returns_none():
    """parse_csv_date returns None when filename has no parseable date."""
    from api import parse_csv_date
    result = parse_csv_date("citations.csv")
    assert result is None


def test_parse_csv_date_none_input_returns_none():
    """parse_csv_date returns None for None input."""
    from api import parse_csv_date
    result = parse_csv_date(None)
    assert result is None
```

- [ ] **Step 2: Run tests -- verify they fail**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_pipeline_improvements.py -k "csv_date or csv_update" -v 2>&1 | head -20
```

Expected: `ImportError` or `AttributeError` -- `parse_csv_date` does not exist yet.

- [ ] **Step 3: Add CSV update check functions to `api.py`**

Add after the `get_citations_df()` function:

```python
# CSV update check -- populated at startup, checked by /health endpoint
CSV_UPDATE_AVAILABLE = False
CSV_LATEST_FILENAME = None


def parse_csv_date(csv_path: Optional[str]):
    """
    Extract the date from a CourtListener bulk CSV filename.

    CourtListener names bulk files as citations-YYYY-MM-DD.csv.
    Returns a datetime.date object or None if no date found.

    Args:
        csv_path: Full path or filename of the CSV file

    Returns:
        datetime.date if parseable, None otherwise
    """
    if not csv_path:
        return None
    import re
    from datetime import date
    filename = os.path.basename(csv_path)
    match = re.search(r"citations-(\d{4})-(\d{2})-(\d{2})", filename)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def check_csv_update_available() -> bool:
    """
    Check CourtListener S3 for bulk citation CSV files newer than the current one.

    Queries the public S3 bucket listing for files matching the citations-*.csv.bz2
    pattern and compares dates against the current CSV filename.

    Returns True if a newer file is found, False otherwise (including on errors).
    Errors are logged but never raised -- update check is informational only.
    """
    global CSV_UPDATE_AVAILABLE, CSV_LATEST_FILENAME

    current_date = parse_csv_date(CITATIONS_CSV)
    if not current_date:
        return False

    try:
        import xml.etree.ElementTree as ET
        resp = http_requests.get(
            "https://com-courtlistener-storage.s3-us-west-2.amazonaws.com/",
            params={"prefix": "bulk-data/citations-", "delimiter": "/"},
            timeout=10
        )
        if resp.status_code != 200:
            return False

        root = ET.fromstring(resp.text)
        ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        keys = [
            el.text for el in root.findall(".//s3:Key", ns)
            if el.text and el.text.endswith(".csv.bz2")
        ]

        latest = None
        latest_key = None
        for key in keys:
            d = parse_csv_date(key)
            if d and (latest is None or d > latest):
                latest = d
                latest_key = key

        if latest and latest > current_date:
            CSV_UPDATE_AVAILABLE = True
            CSV_LATEST_FILENAME = latest_key.split("/")[-1] if latest_key else None
            print(f"CSV update available: {CSV_LATEST_FILENAME}")
            return True

        CSV_UPDATE_AVAILABLE = False
        return False

    except Exception as e:
        print(f"CSV update check failed: {e}")
        return False
```

- [ ] **Step 4: Call `check_csv_update_available()` at startup**

Find the section in `api.py` near `get_citations_df()` where the CSV is
confirmed to exist. Add a startup call using a FastAPI lifespan event.

Find the `app = FastAPI(...)` instantiation and add a lifespan handler:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks: pre-load CSV, check for updates."""
    # Pre-load CSV into memory on startup (not on first request)
    if os.path.exists(CITATIONS_CSV):
        print("Pre-loading citations CSV into memory...")
        get_citations_df()
        # Check for CSV updates in background (non-blocking)
        import asyncio
        asyncio.get_event_loop().run_in_executor(None, check_csv_update_available)
    yield

app = FastAPI(
    title="Wilson",
    description="AI Reasoning Auditor -- Open-source legal citation verification",
    version="0.1.0",
    lifespan=lifespan,
)
```

Note: If `app = FastAPI(...)` already exists in `api.py`, update it to include
`lifespan=lifespan`. Do not duplicate the `app` instantiation.

- [ ] **Step 5: Expose CSV update status in `/health` endpoint**

In the `/health` endpoint in `api.py`, add to the returned dict:

```python
"csv_update": {
    "available": CSV_UPDATE_AVAILABLE,
    "latest_filename": CSV_LATEST_FILENAME
}
```

- [ ] **Step 6: Run tests -- verify they pass**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_pipeline_improvements.py -k "csv_date" -v
```

Expected: 4 passed.

- [ ] **Step 7: Update UI status pill in `index.html`**

The CSV status pill currently reads:
```html
{% if csv_available %}
    <span class="status-pill ok">Offline CSV -- 18M Records</span>
{% else %}
    <span class="status-pill warn">Offline CSV -- Not Configured</span>
{% endif %}
```

Update to pass `csv_update_available` from the server and handle it in the pill:

In `api.py`, in the `index` route, add `csv_update_available` to the template context:

```python
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    available, llm_message = coherence_available()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "llm_available": available,
            "llm_message": llm_message,
            "csv_available": os.path.exists(CITATIONS_CSV),
            "csv_update_available": CSV_UPDATE_AVAILABLE,
            "csv_latest_filename": CSV_LATEST_FILENAME,
        }
    )
```

In `index.html`, update the CSV pill:

```html
{% if csv_available %}
    {% if csv_update_available %}
        <span class="status-pill warn" title="Update available: {{ csv_latest_filename }}. Re-run setup to update.">
            Offline CSV -- Update Available
        </span>
    {% else %}
        <span class="status-pill ok">Offline CSV -- 18M Records</span>
    {% endif %}
{% else %}
    <span class="status-pill warn">Offline CSV -- Not Configured</span>
{% endif %}
```

Also apply the same context update to the `upload` route if it exists.

- [ ] **Step 8: Run full test suite**

```bash
.\venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 9: Commit**

```bash
git add api.py templates/index.html tests/test_pipeline_improvements.py
git commit -m "feat: CSV update check -- notify when newer bulk data available on S3"
```

---

## Task 4: Smoke Test -- Pipeline Improvements End to End

**Files:**
- No changes -- manual verification

- [ ] **Step 1: Start Wilson**

```bash
.\venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: Check /health endpoint**

Open browser to `http://localhost:8000/health` and verify:
- `csv_update` key is present with `available` and `latest_filename` fields
- All other health fields present and correct

- [ ] **Step 3: Test blocked flag (manual)**

Run a citation for cluster 111170 (Strickland v. Washington) through the UI.
The blocked flag check adds ~200ms to Phase 1 for the extra API call.
Verify Phase 1 still returns EXISTS and Phase 2/3 proceed normally
(Strickland is not blocked).

- [ ] **Step 4: Test name confidence threshold (manual)**

In the citation field, type: `Smith v. Jones`
This should trigger the name-based fallback (no reporter), find something,
and if the similarity is below 60%, return the "did you mean?" suggestion
rather than proceeding. Verify the suggestion UI renders correctly.

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat: pipeline improvements complete -- blocked flag, name threshold, CSV update check"
```

- [ ] **Step 6: Push feature branch**

```bash
git push -u origin feature/pipeline-improvements
```

---

## Completion Checklist

- [ ] Branch `feature/pipeline-improvements` created and all commits on it
- [ ] `fetch_cluster_blocked()` added to `api.py` and tested
- [ ] Blocked opinions skip Phase 2/3 with clear UI message
- [ ] `parse_csv_date()` and `check_csv_update_available()` added and tested
- [ ] CSV update status in `/health` and UI pill
- [ ] Name confidence threshold (60%) in fallback path
- [ ] "Did you mean?" suggestion UI renders correctly
- [ ] All tests pass: `.\venv\Scripts\python.exe -m pytest tests/ -v`
- [ ] Feature branch pushed to GitHub
