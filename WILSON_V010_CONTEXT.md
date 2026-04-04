# Wilson v0.1.0 -- Development Context Handoff

## What Wilson is

Wilson is an open-source AI reasoning auditor for legal citations. Apache 2.0.
Repo: https://github.com/CYoung83/wilson
Developer: National Standard Consulting LLC (SDVOSB, disabled veteran owned)

Mission statement: "Wilson removes the advantage afforded to those who will lie."

## Current state (v0.0.5 -- published and live)

Three-phase citation verification pipeline with FastAPI web interface and Windows installer.

### Phase 1 -- Citation Existence
- eyecite extracts citations from text
- CourtListener API v4 citation-lookup endpoint verifies existence
- Local bulk CSV (18M records) loaded into memory for fast offline verification
- Case name fuzzy match (75% threshold, rapidfuzz) catches misattributed citations
- Name-based fallback lookup when only case name provided (no reporter)
- Verdicts: FABRICATED | MISATTRIBUTED | EXISTS

### Phase 2 -- Quote Verification
- Fetches full opinion text via CourtListener opinions API
- Exact + fuzzy match (rapidfuzz) against full opinion text
- Verdicts: 100% MATCH | XX% MATCH | NOT FOUND

### Phase 3 -- Coherence Checking (current: Ollama only)
- Full opinion text sent to local LLM via Ollama
- Asks whether cited case supports the proposition it is cited for
- Configurable via OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_CONTEXT_SIZE in .env
- Degrades gracefully (SKIPPED) if Ollama not configured
- Verdicts: SUPPORTS | DOES_NOT_SUPPORT | UNCERTAIN | SKIPPED

### Proven against
Mata v. Avianca (1:22-cv-01461, S.D.N.Y.) -- 6/6 correct verdicts.
Three fabricated, two misattributed, one legitimate. Zero false positives.

## Architecture -- key files

```
wilson/
  api.py                  -- FastAPI app, streaming SSE pipeline, in-memory CSV
  quote_verify.py         -- Phase 2 fuzzy matching
  coherence_check.py      -- Phase 3 Ollama inference
  smoke_test.py           -- Phase 1+2 integration test
  test_mata_avianca.py    -- 6-citation proof of concept
  charlotin_processor.py  -- Batch processor for Charlotin database
  requirements.txt        -- Dependencies
  .env                    -- Configuration (gitignored)
  .env.example            -- Template
  templates/
    index.html            -- Single-page web UI
  installer/              -- Windows installer files
    wilson.iss            -- Inno Setup script
    Wilson.bat            -- Launcher (thin wrapper)
    Wilson_launcher.ps1   -- Main launcher logic
    Wilson_firstlaunch.ps1 -- First-run credential collection
    scripts/              -- Install helper scripts
```

## Key technical decisions (locked in -- do not revisit without cause)

- **Streaming:** `/verify/stream` uses raw `StreamingResponse` with `text/event-stream`
  and `asyncio.sleep(0)` after each yield for reliable cross-platform flushing.
  Do NOT use `sse_starlette` -- it buffers on Windows browsers.

- **In-memory CSV:** `get_citations_df()` global loads CSV once at first request.
  All subsequent queries use the in-memory dataframe. First query is slow (~30s),
  all subsequent queries are fast (<1s).

- **Case name threshold:** `CASE_NAME_MATCH_THRESHOLD = 75` (rapidfuzz partial_ratio).
  Below 75% = MISATTRIBUTED. Raised from 60 after testing showed false positives.

- **BeautifulSoup:** Use `"lxml"` parser, not `"html.parser"`.
  Filter XMLParsedAsHTMLWarning in both quote_verify.py and coherence_check.py.

- **Ollama Phase 3 (updated 2026-04-03):**
  Default model: `qwen3.5:35b`. Default context: `245760` (240k, tested stable on RTX 5090 32GB).
  Must use `"format": "json"` (grammar-level enforcement) and `"think": False` (disables Qwen3
  hybrid thinking mode -- without this, output goes to `thinking` field and `response` is empty).
  Fallback: if `response` empty and `thinking` field has content, use `thinking` as raw_response.
  Truncation: front-only (dissent is at the end; 75/25 split was causing DISSENTS verdicts).
  All Phase 3 returns include `backend_used: "ollama" | "embeddings" | None`.

- **Windows print statements:** No Unicode (em-dash U+2014, arrow U+2192) in any print() call.
  Windows cp1252 terminal raises UnicodeEncodeError. Use `--` and `->` instead.

- **Windows compatibility:** fast-diff-match-patch cannot compile against embedded
  Python (no Python.h headers). Installer uses a shim:
  1. Install pure Python `diff-match-patch`
  2. Create fake `fast_diff_match_patch` dist-info and module that wraps it
  This satisfies eyecite's dependency without C compilation.

## Environment variables

```bash
COURTLISTENER_TOKEN=        # Required. Free at courtlistener.com/sign-in
CITATIONS_CSV=              # Optional. Path to bulk CSV (18M records, ~1.9GB)
OLLAMA_HOST=                # Optional. Default: http://localhost:11434
OLLAMA_MODEL=               # Optional. Default: llama3
OLLAMA_CONTEXT_SIZE=        # Optional. Default: 32000. Tested at 200000.
PACER_USERNAME=             # Optional. For original filing retrieval.
PACER_PASSWORD=             # Optional.
CHARLOTIN_CSV=              # Optional. Charlotin hallucination database path.
RESULTS_CSV=                # Optional. Batch processing output path.
```

## CourtListener API

- Base: `https://www.courtlistener.com/api/rest/v4/`
- Citation lookup: POST `/citation-lookup/` with `{"text": "..."}`
- Opinions: GET `/opinions/?cluster={id}&fields=id,html_with_citations`
- Search: GET `/search/?q={name}&type=o`
- Semantic search: GET `/search/?q={proposition}&type=o&semantic=true`
- Auth: `Authorization: Token {COURTLISTENER_TOKEN}` header

## v0.1.0 Priority Order

### 1. Backend -- COMPLETE (2026-04-03)
**Embeddings API as Phase 3 fallback -- SHIPPED**

CourtListener supports semantic search via GET with `semantic=true`.
Wilson sends the proposition text, gets back semantically ranked opinions,
checks whether the verified cluster_id appears in results and at what rank.

Implementation approach (Option C -- automatic fallback):
- Try Ollama first (existing behavior)
- If Ollama unavailable, try CourtListener semantic search
- If both unavailable, return SKIPPED
- No user configuration required -- just works

New verdicts for embeddings backend:
- SUPPORTS (cluster in top 20 results, score above threshold)
- UNCERTAIN (cluster in results 21-50, or score borderline)
- DOES_NOT_SUPPORT (cluster not in top 50 results)
- SKIPPED (both backends unavailable)

Add to coherence_check.py:
```python
def check_coherence_embeddings(proposition, cluster_id):
    resp = requests.get(
        "https://www.courtlistener.com/api/rest/v4/search/",
        params={"q": proposition, "type": "o", "semantic": "true"},
        headers=CL_HEADERS,
        timeout=15
    )
    results = resp.json().get("results", [])
    for rank, result in enumerate(results):
        if result.get("cluster_id") == cluster_id:
            return {
                "verdict": "SUPPORTS" if rank < 20 else "UNCERTAIN",
                "confidence": "HIGH" if rank < 10 else "MEDIUM",
                "rank": rank + 1,
                "reasoning": f"Case ranked #{rank+1} in semantic similarity to proposition. "
                             f"{'Strong support indicated.' if rank < 10 else 'Moderate support indicated.'}"
            }
    return {
        "verdict": "DOES_NOT_SUPPORT",
        "confidence": "MEDIUM",
        "rank": None,
        "reasoning": "Case did not appear in top semantic matches for this proposition."
    }
```

Update `check_coherence()` to try embeddings if Ollama unavailable.
Add `backend_used` field to Phase 3 results so UI can display which backend ran.

### 2. Features
- Document upload portal (accept PDF, DOCX, TXT -- extract citations and run pipeline)
- Batch processing pipeline (run multiple citations, return aggregated results)
- HTML report generation (downloadable audit report)
- Timer and token tally per query (display in UI)

### 3. Pipeline improvements
- CourtListener `blocked` flag compliance:
  Check `blocked` field on cluster response. If True, skip Phase 2 and Phase 3,
  note in results that opinion is privacy-protected.
- Name-based lookup confidence threshold:
  If name similarity between user input and top search result is below threshold,
  return "did you mean X?" suggestion instead of proceeding with wrong case.
- CSV update check:
  On startup, check S3 for newer bulk data filename. If found, display notification
  in UI status bar. Do not auto-download.

### 4. Core UI (settings panel)
- Theme: light / dark / high contrast / auto (follows OS)
- Font size: small / medium / large
- Layout density: compact / comfortable
- Ollama model selector: dropdown from live /api/tags query
- Ollama host field: editable, test connection button
- CourtListener token field: masked, verify button
- CSV path: shows path, file size, record count, last updated
- Show/hide progress log toggle
- All settings persist to localStorage
- Settings accessible via gear icon in header

### 5. Branding (last)
- Favicon: Wilson volleyball icon (wilson_icon.ico already exists in installer/)
- Header branding refinement
- About page or modal

## Deferred to later versions
- CourtListener webhook integration (requires publicly accessible URL -- not localhost)
- Semantic similarity via POST with pre-computed embeddings (requires Inception microservice)
- PACER integration
- Intel community application forks
- Docker deployment configuration

## Test citations

**FABRICATED (confirmed):**
- `Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339 (11th Cir. 2019)`
- `Shaboon v. Egyptair, 2013 WL 3829266 (N.D. Ill. 2013)`
- `Martinez v. Delta Air Lines, 2019 WL 4748390 (E.D. Pa. 2019)`

**EXISTS (real):**
- `Miranda v. Arizona, 384 U.S. 436 (1966)` -- cluster 107252
- `Strickland v. Washington, 466 U.S. 668 (1984)` -- cluster 111170
- `Daubert v. Merrell Dow Pharmaceuticals, Inc., 509 U.S. 579 (1993)` -- cluster 112903
- `Obergefell v. Hodges, 576 U.S. 644 (2015)` -- cluster 2812209

**MISATTRIBUTED:**
- `Petersen v. Iran Air, 905 F.2d 1011 (7th Cir. 1990)` -- belongs to Silagy v. Peters

## Running Wilson (dev)

```bash
# Linux/Mac
source venv/bin/activate
uvicorn api:app --reload --host 0.0.0.0 --port 8000

# Windows
.\venv\Scripts\python.exe -m uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

## Notes on code style
- Chris is not a developer -- he uses AI assistance for implementation
- Prefer explicit over clever
- Every function needs a docstring
- Fail loudly with clear error messages
- Degrade gracefully -- partial results are better than no results
- No hardcoded paths -- everything configurable via .env
