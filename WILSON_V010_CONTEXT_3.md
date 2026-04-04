# Wilson v0.1.0 -- Development Context
# Updated: 2026-04-04
# Status: Settings panel in progress -- CSS/JS scope bug to fix

---

## What Wilson is

Wilson is an open-source AI reasoning auditor for legal citations. Apache 2.0.
Repo: https://github.com/CYoung83/wilson
Developer: National Standard Consulting LLC (SDVOSB, disabled veteran owned)
Mission: "Wilson removes the advantage afforded to those who will lie."

---

## Completed in v0.1.0

### Backend -- COMPLETE
- Phase 3 fallback: Ollama -> CourtListener semantic search -> SKIPPED
- `check_coherence_embeddings()` in coherence_check.py
- `backend_used` field on all Phase 3 results
- Automatic fallback chain, no user configuration required

### Document Upload Portal -- COMPLETE (merged to main)
- `document_parser.py` -- PDF, DOCX, TXT extraction with page chunking
- `extract_citations_with_context()` -- eyecite extraction with context window
- `suggest_proposition()` / `suggest_propositions_batch()` -- Ollama with graceful fallback
- GET /upload, POST /upload/parse, POST /batch/propositions, POST /batch/stream
- `templates/upload.html` -- 5-step UI: upload, depth selector, proposition review, batch stream, summary table
- 19 tests passing at merge

### Pipeline Improvements -- COMPLETE (merged to main)
- CourtListener `blocked` flag compliance -- skip Phase 2/3 for privacy-protected opinions
- Name-based fallback confidence threshold (60%) with "did you mean?" suggestion
- CSV update check -- S3 polling at startup, amber pill in UI, exposed in /health
- 29 tests passing at merge

### Settings Panel API -- COMPLETE (on feature/settings-panel, not yet merged)
- GET /settings/ollama-models
- POST /settings/ollama-model
- POST /settings/ollama-host
- POST /settings/courtlistener-token
- write_env_value() helper
- 36 tests passing

### Settings Panel UI -- IN PROGRESS (on feature/settings-panel)
- CSS custom properties added to index.html and upload.html
- Theme definitions: dark, light, high-contrast
- Gear icon in header of both pages
- Settings drawer HTML in both pages
- Settings JavaScript functions in both pages
- **BUG:** applySettings() defined as IIFE -- not in global scope
  openSettings() and other drawer functions also not in global scope
  Result: SyntaxError and ReferenceError on both pages
- **FIX NEEDED:** Convert IIFE to named function, verify all drawer functions
  are in global scope, not wrapped in any closure

---

## The Settings Panel Bug (fix first thing tomorrow)

**Symptoms:**
- `Uncaught SyntaxError: Unexpected token ')'` at line ~487 in index.html
- `Uncaught ReferenceError: openSettings is not defined`
- Same errors in upload.html

**Root cause:**
The `applySettings` function was defined as an IIFE:
```javascript
(function applySettings() { ... })();
```
The opening was changed to `function applySettings() {` but the closing
`})();` was only partially fixed. There is still a stray `)` somewhere
causing the SyntaxError. Until that syntax error is resolved, nothing in
the script block runs -- hence `openSettings is not defined`.

**Fix approach:**
1. In DevTools Sources, find line 487 in index.html and line 971 in upload.html
2. Look for a stray `})();` or lone `)` that doesn't belong
3. Remove it
4. Verify `applySettings`, `openSettings`, `closeSettings`, `setSetting`,
   `syncSettingSelects`, `loadSettingsValues`, `updateOllamaModel`,
   `testOllamaHost`, `verifyClToken`, `checkCsvUpdate` are all defined
   at the top level of the script, not inside any wrapper

**Alternatively:** Have glm rewrite the entire script section of both files
from scratch with all functions in global scope. The HTML structure is correct,
only the JS needs fixing.

---

## Architecture -- current file state

```
wilson/
  api.py                    -- FastAPI, all endpoints including settings
  quote_verify.py           -- Phase 2 fuzzy matching
  coherence_check.py        -- Phase 3 Ollama + embeddings fallback
  document_parser.py        -- text extraction, citation+context, propositions
  smoke_test.py             -- Phase 1+2 integration test
  test_mata_avianca.py      -- 6-citation proof of concept
  charlotin_processor.py    -- Batch processor
  requirements.txt          -- All dependencies
  .env                      -- Configuration (gitignored)
  .env.example              -- Template
  CLAUDE.md                 -- Local execution agent instructions
  templates/
    index.html              -- Single-citation UI (settings drawer added, JS broken)
    upload.html             -- Document upload portal (settings drawer added, JS broken)
  tests/
    __init__.py
    test_document_parser.py -- 19 tests
    test_pipeline_improvements.py -- 10 tests
    test_settings.py        -- 7 tests
  docs/
    superpowers/
      plans/                -- Execution plans for local model
      specs/                -- Design specs for contributors
  installer/                -- Windows installer files
```

---

## Key technical decisions -- LOCKED IN

### Streaming
Raw `StreamingResponse` + `asyncio.sleep(0)` after each yield.
NEVER use sse_starlette -- it buffers on Windows browsers.

### In-memory CSV
`get_citations_df()` global loads once at first request.
First query: ~30s. All subsequent: <1s.

### Case name threshold
`CASE_NAME_MATCH_THRESHOLD = 75` (rapidfuzz partial_ratio)
`FALLBACK_CONFIDENCE_THRESHOLD = 60` (name-based fallback)

### BeautifulSoup
Always `"lxml"` parser. Filter XMLParsedAsHTMLWarning.

### Phase 3 -- Ollama
- Default model: `qwen3.5:35b`
- Default context: `245760`
- `"format": "json"` required
- `"think": False` required (Qwen3 hybrid thinking)
- Front-only truncation (dissent at end, back truncation caused bad verdicts)
- All results include `backend_used: "ollama" | "embeddings" | None`

### Phase 3 -- CourtListener embeddings fallback
- GET `/api/rest/v4/search/?q={proposition}&type=o&semantic=true`
- rank < 20: SUPPORTS, rank 20-50: UNCERTAIN, not found: DOES_NOT_SUPPORT

### Windows
- No Unicode in print() -- cp1252 raises UnicodeEncodeError
- Use `--` not em-dash, `->` not arrow
- fast-diff-match-patch: pure Python shim in installer

### Local execution agent
- Model: glm-4.7-flash (19GB, fits in VRAM with headroom)
- gemma4:31b too large -- 37GB total, overflows 32GB VRAM on generation
- Qwen3-Coder-30B: over-reasons, fails to execute tool calls
- CLAUDE.md in project root constrains agent behavior
- Direct task prompts, not plan file navigation

---

## Environment variables

```bash
COURTLISTENER_TOKEN=        # Required
CITATIONS_CSV=              # Optional. Bulk CSV path (18M records, ~1.9GB)
OLLAMA_HOST=                # Optional. Default: http://localhost:11434
OLLAMA_MODEL=               # Optional. Default: qwen3.5:35b
OLLAMA_CONTEXT_SIZE=        # Optional. Default: 245760
ENV_PATH=                   # Auto-set to .env location relative to api.py
PACER_USERNAME=             # Optional
PACER_PASSWORD=             # Optional
```

---

## CourtListener API

- Base: `https://www.courtlistener.com/api/rest/v4/`
- Citation lookup: POST `/citation-lookup/` with `{"text": "..."}`
- Cluster: GET `/clusters/{id}/` -- includes `blocked` field
- Opinions: GET `/opinions/?cluster={id}&fields=id,html_with_citations`
- Search: GET `/search/?q={name}&type=o`
- Semantic search: GET `/search/?q={proposition}&type=o&semantic=true`
- Auth: `Authorization: Token {COURTLISTENER_TOKEN}` header

---

## Remaining v0.1.0 work

### Immediate (fix first)
1. Fix settings panel JS scope bug in index.html and upload.html
2. Verify theme switching works in browser
3. Commit fix, merge feature/settings-panel PR

### Branding (after settings panel merge)
- Favicon: wilson_icon.ico already in installer/, add to both HTML pages
- Header refinement: small favicon image before h1
- About modal: mission statement, Cast Away reference, links, license, attribution

### GitHub Actions (after branding)
- Release workflow: build Windows installer on tag, attest binary
- Build provenance: actions/attest-build-provenance

### Deferred
- HTML report generation
- Timer and token tally per query
- CourtListener blocked flag in upload portal batch stream
- OCR for image-only PDFs
- QUICKSTART.md
- PACER integration
- Docker deployment
- Full SPA (v1.0.0)
- Multi-file upload (v1.0.0)

---

## Test citations

**FABRICATED:**
- `Varghese v. China Southern Airlines Co., Ltd., 925 F.3d 1339 (11th Cir. 2019)`
- `Shaboon v. Egyptair, 2013 WL 3829266 (N.D. Ill. 2013)`

**EXISTS:**
- `Miranda v. Arizona, 384 U.S. 436 (1966)` -- cluster 107252
- `Strickland v. Washington, 466 U.S. 668 (1984)` -- cluster 111170
- `Daubert v. Merrell Dow Pharmaceuticals, Inc., 509 U.S. 579 (1993)` -- cluster 112903
- `Obergefell v. Hodges, 576 U.S. 644 (2015)` -- cluster 2812209

**MISATTRIBUTED:**
- `Petersen v. Iran Air, 905 F.2d 1011 (7th Cir. 1990)` -- belongs to Silagy v. Peters

---

## Running Wilson (dev)

```powershell
# Windows
cd C:\wilson\v0.1.0
.\venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# Run tests
.\venv\Scripts\python.exe -m pytest tests/ -v
```

## Local model workflow

- Planning and architecture: Claude.ai (this session)
- Execution: Claude Code + glm-4.7-flash via Ollama
- Task prompts: direct specification, not plan file navigation
- CLAUDE.md: constrains agent to execution-only behavior
- Branch per feature, PR to main, never commit directly to main
