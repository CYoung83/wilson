# Wilson Document Upload Portal -- Design Spec
**Date:** 2026-04-03
**Status:** Approved
**Version target:** v0.1.0

---

## Purpose

Add a document upload portal to Wilson that accepts PDF, DOCX, and TXT files,
extracts all legal citations, and runs Wilson's full verification pipeline on
each citation in batch. Designed for both legal professionals (auditability)
and laypeople (plain-English output, clear progress, accessible UI).

Future v1.0.0 will extend this with full-document contextual LLM analysis
(reviewing the entire filing for inconsistencies, not just individual
citations). That work depends on this portal as its foundation.

---

## Architecture

### New files

| File | Purpose |
|------|---------|
| `templates/upload.html` | Upload portal UI |
| `document_parser.py` | Text extraction, citation extraction with context, proposition suggestion |

### New API endpoints (added to `api.py`)

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/upload` | Serves the upload portal page |
| POST | `/upload/parse` | Accepts multipart file, returns citations with context snippets |
| POST | `/batch/propositions` | Accepts citation + context, returns LLM-proposed proposition |
| POST | `/batch/stream` | Accepts batch job, streams SSE results |

### Main page change

`templates/index.html` header gets an "Upload Document" link pointing to `/upload`.

### Deferred to v1.0.0

Full SPA with client-side routing -- convert both pages to a single-page app
with JS-based tab/route switching and shared component templates. Approved
for v1.0.0 during this brainstorm session.

---

## New Dependencies

| Package | Purpose | Notes |
|---------|---------|-------|
| `pypdf` | PDF text extraction | Pure Python, no C compilation |
| `python-docx` | DOCX text extraction | Pure Python, no C compilation |

---

## `document_parser.py`

### `extract_text(file_bytes: bytes, filename: str) -> dict`

Dispatches by file extension:
- `.pdf` -- extracted via `pypdf`
- `.docx` -- extracted via `python-docx` (including footnotes -- citations
  commonly appear in footnotes)
- `.txt` -- decoded directly (UTF-8 with `errors='replace'` fallback)

Fails loudly with a clear message on unsupported type or extraction error.
No silent failures.

Returns:
```json
{
  "text": "...",
  "page_count": 42,
  "pages_processed": 42,
  "extraction_method": "text_layer" | "ocr" | "plaintext" | "docx"
}
```

Page count is returned alongside text so the calling layer can make chunking
decisions before processing begins.

### `extract_citations_with_context(text: str) -> list[dict]`

Runs eyecite on the full document text. For each citation found, captures:
- `citation_text` -- the raw citation string
- `context_snippet` -- sentence containing the citation plus one sentence on
  each side (~300-500 chars)
- `char_offset` -- character position in the document (for ordering)

Returns list sorted by `char_offset` (document order).

### `suggest_proposition(citation_text: str, context_snippet: str) -> dict`

Makes a focused LLM call via the same Ollama connection used in Phase 3
(reuses pattern from `coherence_check.py` -- same host, model, `format: json`,
`think: false` flags).

Prompt instructs the LLM to produce one plain-English sentence stating what
legal proposition this case is being cited for, based on the surrounding
context.

Returns:
```json
{
  "proposition": "...",
  "backend_used": "ollama" | "fallback",
  "raw_snippet": "..."
}
```

Graceful degradation: if Ollama unavailable, `backend_used` is `"fallback"` and
`proposition` is set to the raw snippet so the human has something to start
with. The UI notes the fallback inline.

The raw snippet is always available in the UI as a collapsible
"View source context" toggle on each proposition row.

---

## Proposition Generation -- Concurrency Model

`suggest_proposition` runs **3 citations at a time** via `asyncio.gather`.

Rationale:
- Snappy enough that the queue populates visibly as the user reviews
- Conservative enough that if the user skips early citations, in-flight LLM
  calls for citations 2-3 are the maximum wasted work
- Avoids hammering Ollama with 50 simultaneous requests on large documents

Implementation:
```python
async def suggest_propositions_batch(citations: list[dict]) -> list[dict]:
    results = []
    for i in range(0, len(citations), 3):
        chunk = citations[i:i+3]
        chunk_results = await asyncio.gather(*[
            suggest_proposition(c["citation_text"], c["context_snippet"])
            for c in chunk
        ])
        results.extend(chunk_results)
        # Yield control so UI can update between chunks
        await asyncio.sleep(0)
    return results
```

The proposition queue UI populates incrementally -- rows become editable as
each chunk of 3 completes, rather than waiting for all propositions before
showing the queue.

---

## User Flow

### Step 1 -- Upload

User lands on `/upload`. Drag-and-drop zone (also click-to-browse).
Accepted types: `.pdf`, `.docx`, `.txt`.
File size limit: **50MB**.

On submit, file is sent to `POST /upload/parse`.

**Chunking:** Page count is the actual processing constraint.
File size is validated at upload (50MB hard limit for server protection),
but page count governs processing:
- <= 200 pages: processed as a single batch
- > 200 pages: Wilson automatically chunks into sequential 200-page batches

When chunking applies, user is informed before proceeding:
`This document is X pages. Wilson will process it in N batches of up to 200
pages and queue them automatically. Results build as each batch completes.`

**Upload errors (caught at POST /upload/parse before any pipeline runs):**
- Unsupported file type -- clear message, re-upload prompt
- File exceeds 50MB -- message states the limit plainly
- Extraction failure (corrupted PDF, encrypted DOCX) -- message names the
  problem, no silent failure
- Zero citations found -- `No legal citations were found in this document.
  Wilson looks for standard reporter format, e.g. 384 U.S. 436.`
  Option to go back and try a different file.

### Step 2 -- Depth selector

Before the batch runs, user selects audit depth.

**Phase 3 availability check at this step:**
If Ollama is unavailable AND CourtListener semantic search is unavailable,
the "Full audit" option is greyed out with an inline note:
`Phase 3 requires Ollama (local LLM) or a CourtListener API connection.
Check your configuration to enable coherence checking.`

This prevents the user from building a 40-row proposition queue and
discovering at run time that Phase 3 cannot execute.

| Option | Phases run | Description shown to user |
|--------|-----------|--------------------------|
| Existence only | Phase 1 | Check that every citation actually exists |
| Existence + Quotes | Phase 1 + 2 | Also verify quoted language appears in each opinion |
| Full audit | Phase 1 + 2 + 3 | Also check whether each case supports the argument it's cited for |

A **Cancel** button prompts: `This will clear your upload and citation queue.
Continue?` and returns to Step 1 on confirmation.

### Step 3 -- Proposition review queue (Full audit only)

Wilson calls `POST /batch/propositions` for each citation and builds a
scrollable list view showing all citations simultaneously.

Propositions populate **3 at a time** (see concurrency model above). Rows
become editable as each group of 3 completes -- the queue is usable before
all propositions are generated.

Each row contains:
- Citation text
- Context snippet (collapsible "View source context" toggle -- always available
  regardless of whether Ollama ran)
- Wilson's proposed proposition (editable text field, pre-filled by LLM or
  raw snippet if LLM unavailable -- fallback noted inline)
- Status badge: `Pending` / `Accepted` / `Rewritten` / `Skipped`

User can click any row in any order -- non-linear navigation. Earlier entries
can be revised after later entries inform the decision.

A running tally at the top: `4 accepted · 2 rewritten · 1 skipped · 3 pending`

**Run Audit** button at the bottom activates once at least one citation has
been acted on (accepted, rewritten, or skipped). Pending citations are treated
as skipped at run time -- the tally makes this visible before the user commits.

**Back** button returns to Step 2 (depth selector) without losing queue state.
Navigation: Step 2 Back button prompts confirmation before clearing the upload.
Step 3 Back button returns to Step 2 silently (queue state preserved).

### Step 4 -- Batch run

`POST /batch/stream` fires. SSE streams results using the same raw
`StreamingResponse` + `asyncio.sleep(0)` pattern as `/verify/stream`.

**Overall progress bar** -- always visible. Shows `Citation 3 of 12` with
percentage fill. Animated green shimmer while active (same CSS as index.html).

**Per-citation status line** -- plain English, not phase labels:
- `Checking whether "[case name]" exists...`
- `Verifying quoted language...`
- `Reading opinion for context...`
When complete, the line collapses into a verdict chip.

**Heartbeat:** Server emits a keep-alive SSE event every 3 seconds during
long Phase 3 LLM calls.
- No event for 10 seconds -- soft warning: `Still working -- LLM inference
  can take a moment on large opinions.`
- No event for 30 seconds -- hard warning: `No response from server.
  You may cancel and retry.`

**Elapsed timer** -- running clock while batch is active.

**Cancel mid-batch** -- closes the SSE stream. Completed results render
immediately. A banner notes: `Batch cancelled at citation X of N.`

**Chunked documents:** Each 200-page batch completes and appends to the
summary table before the next batch begins. A batch progress indicator shows
`Batch 1 of 3 complete`.

**Partial failures:** If one citation errors mid-batch, that row gets an ERROR
verdict with the reason stated plainly. The batch continues. A warning banner
at the top of the summary table notes: `X citation(s) encountered errors and
could not be fully verified.`

### Step 5 -- Summary table

Renders when the `done` SSE event fires (or on cancel, with partial results).

One row per citation. Columns:
- Citation text
- Phase 1 verdict (badge + plain-English gloss)
- Phase 2 verdict (badge + plain-English gloss, if run)
- Phase 3 verdict (badge + plain-English gloss, if run)
- Expand toggle (shows full reasoning, matched passage, confidence,
  backend used for Phase 3)

**Plain-English verdict glosses:**

| Verdict | Plain English |
|---------|--------------|
| FABRICATED | This citation does not exist in any federal court record. |
| MISATTRIBUTED | These coordinates belong to a different case. |
| EXISTS | Citation verified. |
| 100% MATCH | Quoted language found exactly in the opinion. |
| XX% MATCH | Similar language found; minor wording differences. |
| NOT FOUND | Quoted language not found in the opinion. |
| SUPPORTS | The cited case supports this argument. |
| DOES_NOT_SUPPORT | The cited case does not support this argument. |
| UNCERTAIN | Relationship between case and argument is unclear. |
| SKIPPED | Not checked (proposition was skipped or Phase 3 unavailable). |
| ERROR | Verification failed. Reason shown inline. |

**Final duration** and citation count shown below the table.

---

## Progress and Accessibility

Wilson's batch UI is designed for two audiences simultaneously:

**Legal professionals** need auditability: every verdict has a reasoning chain,
raw snippets are available, phase labels are present in the expand view,
backend used for Phase 3 is disclosed (Ollama vs. CourtListener semantic search).

**Laypeople** need clarity: plain-English glosses on every verdict, progress
that makes the program's state unambiguous, no jargon in the primary view.

The plain-English layer is additive -- it does not replace technical output,
it accompanies it.

---

## Styling

`upload.html` inherits the existing dark theme from `index.html` (replicate
the CSS inline -- no shared stylesheet for now per YAGNI). Same color palette,
same font stack, same verdict badge classes (`v-green`, `v-red`, `v-orange`,
`v-grey`), same `fadeUp` animation, same progress bar shimmer.

---

## Not in scope for v0.1.0

- HTML report generation (downloadable audit report) -- separate feature
- Full-document contextual LLM analysis -- foundation built here, analysis deferred
- Saving batch results to CSV -- separate feature
- Multi-file upload in a single session
- OCR for image-only PDFs (pytesseract/Tesseract) -- deferred; text-layer PDFs
  and DOCX cover the majority of use cases. OCR added when user demand is clear.
