# VERIFICATION FINDINGS — Wilson v0.1.1
**Date:** 2026-06-09
**Branch:** verify-commit-signing (not main)
**Scope:** Read-only verification session per WILSON_PILOT_DONE.md checklist items 1-5.

---

## TASK 1 — Test Baseline

**Result:** 36/36 tests passed. Matches the v0.1.0 recorded count from WILSON_PROJECT_HANDOFF.md.
**Test files:** test_document_parser.py (19), test_pipeline_improvements.py (10), test_settings.py (7).
**Command used:** `C:\wilson\v0.1.0\venv\Scripts\python.exe -m pytest`

No test failures. Baseline is healthy.

---

## TASK 2 — Verdict Taxonomy

**Finding:** No central enum exists. All verdicts are string literals scattered across `api.py` and `coherence_check.py`. This works but makes the taxonomy fragile to typos and hard to audit at a glance.

### Phase 1 (Existence Verification) — api.py
| Verdict | Line | Meaning |
|---------|------|---------|
| `FABRICATED` | ~500 | Citation not found in CourtListener |
| `EXISTS` | ~548, ~565 | Citation verified against CourtListener |
| `ERROR` | ~513 | API call failed or unexpected response |
| `MISATTRIBUTED` | ~528 | Citation found but case name does not match |

### Phase 2 (Quote Verification) — api.py
| Verdict | Line | Meaning |
|---------|------|---------|
| `EXACT_MATCH` | ~590 | Quoted text found verbatim in opinion |
| `FUZZY_MATCH` | ~605 | Partial similarity match |
| `NOT_FOUND` | ~605 | Quoted text not present in opinion |

### Phase 3 (Coherence Checking) — coherence_check.py and api.py (~618-623)
| Verdict | Source | Meaning |
|---------|--------|---------|
| `SUPPORTS` | coherence_check.py | Cited case supports the proposition |
| `DOES_NOT_SUPPORT` | coherence_check.py | Case does not support the proposition |
| `UNCERTAIN` | coherence_check.py | Model cannot determine coherence |
| `SKIPPED` | coherence_check.py | Backend (Ollama/ CourtListener) unavailable |
| `ERROR` | coherence_check.py | Inference or API error occurred |

**Risk:** `ERROR` is used in both Phase 1 and Phase 3 with different meanings (P1 = CourtListener API failure, P3 = LLM inference failure). A report consumer could confuse the two. Low risk since phase context disambiguates, but worth noting for report design.

**Verdict for report spec:** All 9 verdict values are confirmed from source code. The glossary in `templates/index.html` (lines 963-973) lists all 9 correctly and matches the code.

---

## TASK 3 — Batch Stream Bug (Critical)

**Location:** `templates/upload.html`, lines 1436-1615 (`runAuditBtn` click handler)

**Finding:** The batch audit stream never fires. Line 1499 references `response.body.getReader()` but the `response` variable is never defined in that scope. There is no `fetch()` call to `/batch/stream` anywhere in the click handler.

**Code excerpt (line 1499):**
```javascript
const reader = response.body.getReader();
```
`response` is undefined. No preceding fetch exists. This line throws a `ReferenceError` immediately when reached.

**Root cause:** The code assumes a fetch response object exists but never creates one. The `/batch/stream` endpoint on the backend (`api.py` lines 928-979) is functional, but the frontend never calls it.

**Impact:** Step 5 of the upload flow (the actual batch audit) cannot complete. A user who reaches the "Run Audit" button will get a JavaScript error and no results.

### Additional Finding — Dead Code
`templates/upload.html`, lines 1616-1735: An EventSource-based handler exists that references undefined `event` and `eventSource` variables. This appears to be an abandoned reimplementation attempt. It is dead code — it cannot execute because the variables it depends on are never declared in scope.

---

## TASK 4 — Summary Table Verdict Population (Critical)

**Location:** `templates/upload.html`, lines 1755-1800 (`renderSummary()` function) and line 1184

**Finding:** The summary table will always show "-" for all verdict columns because the data it reads was never populated.

**Details:**
- Line 1184: `summaryData = []` is declared but never written to. No code pushes verdict data into this array.
- `renderSummary()` (line 1755) reads `citation.phase1_verdict`, `citation.phase2_verdict`, `citation.phase3_verdict` from `citationsData`.
- The SSE event handlers (lines ~1500-1600) update visual status lines in the DOM but never write verdict strings back into `citationsData`.
- Even if Task 3's batch stream bug were fixed, the summary table would still show "-" because the SSE handlers don't populate the data structure that `renderSummary()` reads.

**Impact:** The verification report cannot display per-citation verdicts in the summary table. This blocks the Definition of Done: "receives a Verification Report without a crash."

---

## TASK 5 — 24-Finding Code Review List

**Finding:** Not found in the repository. Searched exhaustively:
- All `.md` files (project root and `docs/`)
- All `.txt` files
- Glob patterns for `*finding*`, `*audit*`, `*review*`, `*fix*`, `*tier*`, `*TODO*`
- Grep for "24", "finding", "code review fix", "tier" references

The list is referenced in WILSON_PROJECT_HANDOFF.md (line 46) as "ready for CC, organized in three priority tiers" with location marked as "VERIFY (likely in the Wilson repo or Drive)." It appears to exist outside the repository — possibly in Google Drive or a prior session transcript.

**Action needed:** The list must be located externally before Tier 1 items can be scoped and implemented.

---

## TASK 6 — Repository State

### Current Branch
`verify-commit-signing` (not main). Working on a feature branch as required by CLAUDE.md policy.

### Modified Files (unstaged)
| File | Status |
|------|--------|
| `.claude/settings.local.json` | Modified |
| `CLAUDE.md` | Modified |
| `api.py` | Modified |
| `templates/index.html` | Modified |
| `templates/upload.html` | Modified |

### Staged Files (added, not yet committed)
- `.idea/.gitignore`, `.idea/inspectionProfiles/profiles_settings.xml`, `.idea/modules.xml`, `.idea/v0.1.0.iml`, `.idea/vcs.xml` — IDE configuration files from JetBrains

### Untracked Files
- `.serena/` — Serena MCP tool state directory
- `WILSON_PILOT_DONE.md` — pilot scope document (newly added)
- `WILSON_PROJECT_HANDOFF.md` — project handoff document (newly added)

### Recent Commits (3 most recent)
```
1d94887 v0.1.1 — sse-starlette removed, Phase 2 timeout, dynamic CSV URL, Windows encoding fixes
fe4b4e1 chore: remove test artifacts from working session
ad8c2f4 test: verify commit signing
```

### Tags
`v0.0.5`, `v0.1.0`, `v0.1.1` — all present on origin per handoff doc.

---

## SUMMARY OF BLOCKERS FOR DEFINITION OF DONE

Two critical bugs block the Definition of Done path ("attorney installs, drops a brief, receives a report without a crash"):

1. **Batch stream never fires** (`upload.html:1499`) — undefined `response` variable, missing fetch call to `/batch/stream`.
2. **Summary table shows no verdicts** (`upload.html:1755-1800`) — SSE handlers don't populate `citationsData`; `summaryData` array is never written to.

Both are frontend-only bugs in `templates/upload.html`. The backend endpoints (`api.py`) are functional and tested.

The 24-finding code review list (Task 5) could not be located in the repository. It must be found externally before Tier 1 scoping can proceed.
