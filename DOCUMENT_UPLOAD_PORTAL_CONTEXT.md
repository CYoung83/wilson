# Document Upload Portal - Implementation Context

## Design Specification

**Purpose:** Add a document upload portal to Wilson that accepts PDF, DOCX, and TXT files, extracts all legal citations, and runs Wilson's full verification pipeline on each citation in batch.

**Target:** v0.1.0 milestone

**Architecture:**
- New `document_parser.py` handles text extraction and citation extraction
- Four new endpoints in `api.py` handle file upload/parse, proposition generation (SSE), and batch streaming (SSE)
- New `templates/upload.html` is a standalone multi-step UI following the existing dark theme

**User Flow:**
1. Upload document (PDF, DOCX, or TXT, max 50MB)
2. Select audit depth (Existence only / Existence + Quotes / Full audit)
3. Review propositions (Full audit only) - user can Accept/Rewrite/Skip
4. Run batch stream (SSE)
5. View summary table with verdicts and glosses

## Key Technical Decisions

- **Streaming:** Use raw `StreamingResponse` with `text/event-stream` and `asyncio.sleep(0)` after each yield (same pattern as existing /verify/stream)
- **Chunking:** Documents > 200 pages are automatically chunked into sequential batches
- **Proposition concurrency:** 3 citations at a time via `asyncio.gather`
- **Phase 3 fallback:** If Ollama unavailable, use CourtListener semantic search
- **File size limit:** 50MB hard limit for server protection
- **Dependencies:** pypdf==5.4.0, python-docx==1.1.2, python-multipart==0.0.20

## New API Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/upload` | Serves the upload portal page |
| POST | `/upload/parse` | Accepts multipart file, returns citations with context snippets |
| POST | `/batch/propositions` | Accepts citation + context, returns LLM-proposed proposition (SSE) |
| POST | `/batch/stream` | Accepts batch job, streams SSE results |

## New Files

| File | Purpose |
|------|---------|
| `document_parser.py` | Text extraction, citation+context extraction, proposition suggestion |
| `templates/upload.html` | Upload portal UI (multi-step) |
| `tests/test_document_parser.py` | Unit tests for document_parser |
| `tests/test_upload_api.py` | Integration tests for new endpoints |
| `tests/test_upload_smoke.py` | Smoke tests for end-to-end flow |

## Task List

### Task 1: Add Dependencies
- Modify `requirements.txt` to add pypdf==5.4.0, python-docx==1.1.2, python-multipart==0.0.20
- Install dependencies
- Verify imports work
- Commit

### Task 2: document_parser.py — Skeleton + TXT Extraction
- Create `tests/__init__.py` (empty file)
- Create `tests/test_document_parser.py` with failing tests
- Create `document_parser.py` skeleton + TXT implementation
- Run TXT tests — verify they pass
- Commit

### Task 3: document_parser.py — DOCX Extraction
- Add DOCX tests to `tests/test_document_parser.py`
- Run DOCX tests — verify they pass
- Commit

### Task 4: document_parser.py — PDF Extraction
- Add PDF tests to `tests/test_document_parser.py`
- Run PDF tests — verify they pass
- Commit

### Task 5: document_parser.py — extract_citations_with_context
- Write failing tests for citation extraction
- Implement `extract_citations_with_context` in `document_parser.py`
- Run citation tests
- Run full test suite
- Commit

### Task 6: document_parser.py — Proposition Suggestion
- Write failing tests for proposition suggestion
- Implement `suggest_proposition` and `suggest_propositions_batch` in `document_parser.py`
- Run proposition tests
- Run full test suite
- Commit

### Task 7: API Endpoints — GET /upload and POST /upload/parse
- Write failing tests in `tests/test_upload_api.py`
- Add new imports and models to `api.py`
- Add `GET /upload` and `POST /upload/parse` to `api.py`
- Run upload/parse tests
- Commit

### Task 8: API Endpoints — POST /batch/propositions
- Write failing test in `tests/test_upload_api.py`
- Add `POST /batch/propositions` to `api.py`
- Run test
- Commit

### Task 9: API Endpoints — POST /batch/stream
- Write failing tests in `tests/test_upload_api.py`
- Add `POST /batch/stream` to `api.py`
- Run batch/stream tests
- Run full test suite
- Commit

### Task 10: upload.html — Steps 1 & 2
- Create `templates/upload.html` with complete HTML (Steps 1-2 fully implemented)
- Manually test Steps 1 and 2 in browser
- Add "Upload Document" link to `templates/index.html` header
- Commit

### Task 11: upload.html — Step 3
- Replace `_propositionQueueImpl` placeholder with full implementation
- Manually test the proposition queue
- Commit

### Task 12: upload.html — Steps 4 & 5
- Replace `_batchImpl` and `_cancelBatchImpl` placeholders with full implementation
- Manually test the full flow end-to-end
- Commit

### Task 13: Integration Smoke Test + Final Checks
- Create `tests/test_upload_smoke.py` with smoke tests
- Run smoke tests (server must be running)
- Run full unit test suite one final time
- Final commit

## Plain-English Verdict Glosses

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

## Styling Requirements

- `upload.html` inherits the existing dark theme from `index.html`
- Replicate CSS inline (no shared stylesheet for now per YAGNI)
- Same color palette, font stack, verdict badge classes
- Same `fadeUp` animation, progress bar shimmer

## Not in Scope for v0.1.0

- HTML report generation (downloadable audit report)
- Full-document contextual LLM analysis
- Saving batch results to CSV
- Multi-file upload in a single session
- OCR for image-only PDFs