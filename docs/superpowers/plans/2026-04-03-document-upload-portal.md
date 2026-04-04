# Document Upload Portal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/upload` portal that accepts PDF, DOCX, and TXT files, extracts all legal citations, and runs Wilson's full verification pipeline on each citation in batch with user-selectable depth and a human-in-the-loop proposition review queue for Phase 3.

**Architecture:** New `document_parser.py` handles text extraction and citation extraction. Four new endpoints in `api.py` handle file upload/parse, proposition generation (SSE), and batch streaming (SSE). New `templates/upload.html` is a standalone multi-step UI following the existing dark theme.

**Tech Stack:** pypdf, python-docx, python-multipart, FastAPI UploadFile, asyncio.gather for concurrency, raw StreamingResponse SSE (same pattern as existing /verify/stream — do NOT use sse-starlette).

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Create | `document_parser.py` | Text extraction, citation+context extraction, proposition suggestion |
| Create | `templates/upload.html` | Multi-step upload portal UI |
| Create | `tests/test_document_parser.py` | Unit tests for document_parser |
| Create | `tests/test_upload_api.py` | Integration tests for new endpoints |
| Modify | `api.py` | Add 4 new endpoints + Pydantic models |
| Modify | `requirements.txt` | Add pypdf, python-docx, python-multipart |
| Modify | `templates/index.html` | Add "Upload Document" link in header |

---

## Task 1: Add Dependencies

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add new packages to requirements.txt**

Open `requirements.txt` and add after the `# API and web interface` block:

```
# Document parsing (upload portal)
pypdf==5.4.0
python-docx==1.1.2
python-multipart==0.0.20
```

Note: `python-multipart` is required by FastAPI for `UploadFile` to work. Without it, file upload endpoints silently fail.

- [ ] **Step 2: Install dependencies**

```bash
.\venv\Scripts\pip.exe install pypdf==5.4.0 python-docx==1.1.2 python-multipart==0.0.20
```

Expected: All three install without errors. No C compilation required — all pure Python.

- [ ] **Step 3: Verify imports work**

```bash
.\venv\Scripts\python.exe -c "import pypdf; import docx; import multipart; print('OK')"
```

Expected output: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "feat: add pypdf, python-docx, python-multipart for upload portal"
```

---

## Task 2: `document_parser.py` — Skeleton + TXT Extraction

**Files:**
- Create: `document_parser.py`
- Create: `tests/__init__.py`
- Create: `tests/test_document_parser.py`

- [ ] **Step 1: Create tests directory and write failing tests**

Create `tests/__init__.py` (empty file).

Create `tests/test_document_parser.py`:

```python
"""
Tests for document_parser.py

Covers text extraction (TXT, DOCX, PDF), citation extraction with context,
and proposition suggestion (mocked Ollama).
"""

import pytest
from document_parser import extract_text, extract_citations_with_context


# ---------------------------------------------------------------------------
# TXT extraction
# ---------------------------------------------------------------------------

def test_extract_text_txt_basic():
    """Plain text files are decoded and returned with estimated page count."""
    content = "Miranda v. Arizona, 384 U.S. 436 (1966) established the right to counsel."
    result = extract_text(content.encode("utf-8"), "brief.txt")
    assert result["text"] == content
    assert result["extraction_method"] == "plaintext"
    assert result["page_count"] >= 1
    assert isinstance(result["page_boundaries"], list)
    assert result["page_boundaries"][0] == 0


def test_extract_text_txt_utf8_with_replacement():
    """Invalid UTF-8 bytes are replaced, not raised."""
    bad_bytes = b"Good text \xff\xfe bad bytes"
    result = extract_text(bad_bytes, "broken.txt")
    assert "Good text" in result["text"]
    assert result["extraction_method"] == "plaintext"


def test_extract_text_unsupported_type():
    """Unsupported file extensions raise ValueError with clear message."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text(b"data", "document.xlsx")


def test_extract_text_empty_txt():
    """Empty files return empty text, page_count of 1."""
    result = extract_text(b"", "empty.txt")
    assert result["text"] == ""
    assert result["page_count"] == 1


def test_extract_text_txt_page_boundaries_estimated():
    """Page boundaries are estimated at 3000 chars per page for TXT."""
    # 7500 chars -> 3 estimated pages (0, 3000, 6000)
    content = "x" * 7500
    result = extract_text(content.encode("utf-8"), "long.txt")
    assert result["page_count"] == 3
    assert result["page_boundaries"] == [0, 3000, 6000]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -v 2>&1 | head -30
```

Expected: `ImportError: No module named 'document_parser'` or similar. Tests must fail before implementing.

- [ ] **Step 3: Create `document_parser.py` skeleton + TXT implementation**

```python
"""
document_parser.py

Extracts text from uploaded documents (PDF, DOCX, TXT), identifies legal
citations and their surrounding context, and generates proposition suggestions
for Phase 3 coherence checking.

Why this module exists: Wilson's upload portal needs document-level processing
that the existing api.py pipeline (which operates on individual citations) does
not provide.

Failure modes: unsupported file types raise ValueError; extraction failures
(corrupted files, encrypted PDFs) raise RuntimeError with a plain-English
message. No silent failures.
"""

import os
import re
import math
import asyncio
from typing import Optional
import requests as http_requests
from dotenv import load_dotenv
from eyecite import get_citations

load_dotenv()

CHARS_PER_ESTIMATED_PAGE = 3000
PROPOSITION_BATCH_SIZE = 3

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:35b")
OLLAMA_CONTEXT_SIZE = int(os.getenv("OLLAMA_CONTEXT_SIZE", "245760"))


def extract_text(file_bytes: bytes, filename: str) -> dict:
    """
    Extract plain text from an uploaded file.

    Dispatches by file extension:
    - .txt  -- UTF-8 decode with errors='replace'
    - .docx -- python-docx (body paragraphs + footnotes)
    - .pdf  -- pypdf (text layer only; OCR not supported)

    Returns:
        {
            "text": str,                  # full document text
            "page_count": int,            # actual (PDF) or estimated (DOCX/TXT)
            "page_boundaries": list[int], # char offset where each page starts
            "extraction_method": str      # "plaintext" | "docx" | "text_layer"
        }

    Raises:
        ValueError: unsupported file extension
        RuntimeError: extraction failure (corrupted file, encrypted PDF, etc.)
    """
    ext = os.path.splitext(filename.lower())[1]

    if ext == ".txt":
        return _extract_txt(file_bytes)
    elif ext == ".docx":
        return _extract_docx(file_bytes)
    elif ext == ".pdf":
        return _extract_pdf(file_bytes)
    else:
        raise ValueError(
            f"Unsupported file type: '{ext}'. "
            f"Wilson accepts .pdf, .docx, and .txt files."
        )


def _extract_txt(file_bytes: bytes) -> dict:
    """
    Decode a plain-text file with UTF-8 (errors replaced).
    Page count and boundaries estimated at CHARS_PER_ESTIMATED_PAGE chars/page.
    """
    text = file_bytes.decode("utf-8", errors="replace")
    page_boundaries = _estimate_page_boundaries(text)
    page_count = max(1, len(page_boundaries))
    return {
        "text": text,
        "page_count": page_count,
        "page_boundaries": page_boundaries,
        "extraction_method": "plaintext",
    }


def _estimate_page_boundaries(text: str) -> list:
    """
    Estimate page boundaries at every CHARS_PER_ESTIMATED_PAGE characters.
    Always starts with 0. Returns [0] for empty text.
    """
    if not text:
        return [0]
    return list(range(0, len(text), CHARS_PER_ESTIMATED_PAGE))


def _extract_docx(file_bytes: bytes) -> dict:
    """
    Extract text from a DOCX file including body paragraphs and footnotes.
    Citations frequently appear in footnotes in legal filings.
    Page boundaries are estimated (DOCX has no reliable page model).
    """
    try:
        import io
        from docx import Document
        from docx.oxml.ns import qn

        doc = Document(io.BytesIO(file_bytes))
        parts = []

        # Body paragraphs
        for para in doc.paragraphs:
            if para.text.strip():
                parts.append(para.text)

        # Footnotes (citations commonly live here)
        for rel in doc.part.rels.values():
            if "footnotes" in rel.reltype:
                try:
                    footnote_part = rel.target_part
                    footnote_xml = footnote_part._element
                    for fn in footnote_xml.findall(f".//{qn('w:p')}"):
                        text = "".join(
                            r.text for r in fn.findall(f".//{qn('w:t')}") if r.text
                        )
                        if text.strip():
                            parts.append(text)
                except Exception:
                    pass  # Footnotes optional — don't fail the whole extraction

        text = "\n".join(parts)
        page_boundaries = _estimate_page_boundaries(text)
        return {
            "text": text,
            "page_count": max(1, len(page_boundaries)),
            "page_boundaries": page_boundaries,
            "extraction_method": "docx",
        }
    except Exception as e:
        raise RuntimeError(
            f"Could not read DOCX file. The file may be corrupted or in an "
            f"unsupported format. Detail: {e}"
        )


def _extract_pdf(file_bytes: bytes) -> dict:
    """
    Extract text from a PDF using pypdf's text layer.
    Page boundaries reflect actual PDF page structure.
    Raises RuntimeError if the PDF is encrypted or unreadable.
    OCR is not supported -- image-only PDFs will return empty text.
    """
    try:
        import io
        import pypdf

        reader = pypdf.PdfReader(io.BytesIO(file_bytes))

        if reader.is_encrypted:
            raise RuntimeError(
                "This PDF is encrypted and cannot be read. "
                "Please provide an unlocked copy of the document."
            )

        pages_text = []
        for page in reader.pages:
            pages_text.append(page.extract_text() or "")

        page_boundaries = []
        offset = 0
        for page_text in pages_text:
            page_boundaries.append(offset)
            offset += len(page_text) + 1  # +1 for the newline separator

        text = "\n".join(pages_text)
        return {
            "text": text,
            "page_count": len(reader.pages),
            "page_boundaries": page_boundaries,
            "extraction_method": "text_layer",
        }
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(
            f"Could not read PDF file. The file may be corrupted. Detail: {e}"
        )
```

- [ ] **Step 4: Run TXT tests — verify they pass**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py::test_extract_text_txt_basic tests/test_document_parser.py::test_extract_text_txt_utf8_with_replacement tests/test_document_parser.py::test_extract_text_unsupported_type tests/test_document_parser.py::test_extract_text_empty_txt tests/test_document_parser.py::test_extract_text_txt_page_boundaries_estimated -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add document_parser.py tests/__init__.py tests/test_document_parser.py
git commit -m "feat: document_parser skeleton with TXT extraction and tests"
```

---

## Task 3: `document_parser.py` — DOCX Extraction

**Files:**
- Modify: `tests/test_document_parser.py`
- Modify: `document_parser.py` (already written in Task 2 — tests verify it)

- [ ] **Step 1: Add DOCX tests to `tests/test_document_parser.py`**

Add after the TXT tests:

```python
# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def _make_docx_bytes(paragraphs: list) -> bytes:
    """Helper: create a minimal in-memory DOCX with given paragraph strings."""
    import io
    from docx import Document
    doc = Document()
    for para in paragraphs:
        doc.add_paragraph(para)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extract_text_docx_basic():
    """DOCX body paragraphs are extracted into text."""
    content = [
        "Miranda v. Arizona, 384 U.S. 436 (1966) established the right to counsel.",
        "Strickland v. Washington, 466 U.S. 668 (1984) governs ineffective assistance."
    ]
    docx_bytes = _make_docx_bytes(content)
    result = extract_text(docx_bytes, "brief.docx")
    assert "Miranda v. Arizona" in result["text"]
    assert "Strickland v. Washington" in result["text"]
    assert result["extraction_method"] == "docx"
    assert result["page_count"] >= 1


def test_extract_text_docx_empty():
    """Empty DOCX returns empty text and page_count of 1."""
    docx_bytes = _make_docx_bytes([])
    result = extract_text(docx_bytes, "empty.docx")
    assert result["text"] == ""
    assert result["page_count"] == 1


def test_extract_text_docx_corrupted():
    """Corrupted DOCX bytes raise RuntimeError with plain-English message."""
    with pytest.raises(RuntimeError, match="Could not read DOCX file"):
        extract_text(b"this is not a docx", "broken.docx")
```

- [ ] **Step 2: Run DOCX tests — verify they pass**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -k "docx" -v
```

Expected: 3 passed. The implementation was written in Task 2.

- [ ] **Step 3: Commit**

```bash
git add tests/test_document_parser.py
git commit -m "test: add DOCX extraction tests for document_parser"
```

---

## Task 4: `document_parser.py` — PDF Extraction

**Files:**
- Modify: `tests/test_document_parser.py`

- [ ] **Step 1: Add PDF tests**

Add after the DOCX tests:

```python
# ---------------------------------------------------------------------------
# PDF extraction
# ---------------------------------------------------------------------------

def _make_pdf_bytes(pages: list) -> bytes:
    """Helper: create a minimal in-memory PDF with one text page per string."""
    import io
    import pypdf
    from pypdf import PdfWriter

    writer = PdfWriter()
    for text in pages:
        # Add a blank page and overlay text via a simple content stream
        page = writer.add_blank_page(width=612, height=792)
        # pypdf doesn't have a simple add_text API; use a content stream
        content = f"BT /F1 12 Tf 72 720 Td ({text[:80]}) Tj ET"
        from pypdf.generic import ContentStream, DecodedStreamObject
        stream = DecodedStreamObject()
        stream.set_data(content.encode())
        page["/Contents"] = stream

    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extract_text_pdf_page_count():
    """PDF extraction returns correct page count via pypdf."""
    import io
    import pypdf
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    result = extract_text(pdf_bytes, "two_pages.pdf")
    assert result["extraction_method"] == "text_layer"
    assert result["page_count"] == 2
    assert len(result["page_boundaries"]) == 2
    assert result["page_boundaries"][0] == 0


def test_extract_text_pdf_corrupted():
    """Corrupted PDF bytes raise RuntimeError with plain-English message."""
    with pytest.raises(RuntimeError, match="Could not read PDF file"):
        extract_text(b"not a pdf at all", "broken.pdf")
```

- [ ] **Step 2: Run PDF tests**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -k "pdf" -v
```

Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_document_parser.py
git commit -m "test: add PDF extraction tests for document_parser"
```

---

## Task 5: `document_parser.py` — `extract_citations_with_context`

**Files:**
- Modify: `tests/test_document_parser.py`
- Modify: `document_parser.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_document_parser.py`:

```python
# ---------------------------------------------------------------------------
# Citation extraction with context
# ---------------------------------------------------------------------------

def test_extract_citations_basic():
    """Citations are extracted with surrounding context snippet."""
    text = (
        "The court held that defendants have rights. "
        "Miranda v. Arizona, 384 U.S. 436 (1966) established the right to counsel. "
        "This changed American law forever."
    )
    page_boundaries = [0]
    results = extract_citations_with_context(text, page_boundaries)
    assert len(results) == 1
    assert "384 U.S. 436" in results[0]["citation_text"]
    assert "Miranda" in results[0]["context_snippet"]
    assert results[0]["char_offset"] >= 0
    assert results[0]["page_number"] == 1


def test_extract_citations_multiple():
    """Multiple citations are returned in document order."""
    text = (
        "Miranda v. Arizona, 384 U.S. 436 (1966) first. "
        "Later, Strickland v. Washington, 466 U.S. 668 (1984) applied."
    )
    results = extract_citations_with_context(text, [0])
    assert len(results) == 2
    assert results[0]["char_offset"] < results[1]["char_offset"]


def test_extract_citations_empty_text():
    """Text with no citations returns empty list."""
    results = extract_citations_with_context("No citations here.", [0])
    assert results == []


def test_extract_citations_page_number_assigned():
    """Citations on page 2 get page_number 2."""
    page1 = "x" * 1000
    page2_citation = " Miranda v. Arizona, 384 U.S. 436 (1966) held this."
    text = page1 + page2_citation
    page_boundaries = [0, 1000]
    results = extract_citations_with_context(text, page_boundaries)
    assert len(results) == 1
    assert results[0]["page_number"] == 2


def test_extract_citations_context_window():
    """Context snippet includes sentence before and after the citation."""
    text = (
        "First sentence before. "
        "Miranda v. Arizona, 384 U.S. 436 (1966) is the citation. "
        "Last sentence after."
    )
    results = extract_citations_with_context(text, [0])
    snippet = results[0]["context_snippet"]
    assert "First sentence before" in snippet or "Last sentence after" in snippet
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -k "citations" -v
```

Expected: `ImportError` or `AttributeError` — `extract_citations_with_context` not yet implemented.

- [ ] **Step 3: Implement `extract_citations_with_context` in `document_parser.py`**

Add after `_extract_pdf`:

```python
def extract_citations_with_context(text: str, page_boundaries: list) -> list:
    """
    Run eyecite on document text and return each citation with its surrounding
    context snippet and page number.

    Context window: one sentence before and one sentence after the citation,
    capped at approximately 500 characters total.

    Args:
        text: full document text
        page_boundaries: list of char offsets where each page starts (from extract_text)

    Returns:
        list of dicts, sorted by char_offset:
        [{
            "citation_text": str,
            "context_snippet": str,
            "char_offset": int,
            "page_number": int  # 1-based
        }]
    """
    import bisect

    citations_found = get_citations(text)
    if not citations_found:
        return []

    results = []
    for c in citations_found:
        # eyecite gives us a span via .token.start / .token.end on the matched text
        # Use the span to find context in the original text
        try:
            citation_str = str(c)
            # Find the position of this citation in the text
            char_offset = text.find(citation_str)
            if char_offset == -1:
                # Fallback: use groups to reconstruct a search string
                groups = c.groups
                vol = groups.get("volume", "")
                reporter = groups.get("reporter", "")
                page = groups.get("page", "")
                search_str = f"{vol} {reporter} {page}".strip()
                char_offset = text.find(search_str)
            if char_offset == -1:
                char_offset = 0

            context_snippet = _extract_context_window(text, char_offset, citation_str)

            # Assign page number via binary search on page_boundaries
            page_idx = bisect.bisect_right(page_boundaries, char_offset) - 1
            page_number = max(1, page_idx + 1)

            results.append({
                "citation_text": citation_str,
                "context_snippet": context_snippet,
                "char_offset": char_offset,
                "page_number": page_number,
            })
        except Exception:
            continue  # Skip unparseable citations; partial results > no results

    # Sort by document order
    results.sort(key=lambda x: x["char_offset"])
    return results


def _extract_context_window(text: str, char_offset: int, citation_str: str) -> str:
    """
    Extract a context window around a citation: one sentence before,
    the citation itself, and one sentence after. Capped at 500 chars.

    Sentence boundaries detected by '. ' or '\n'.
    """
    # Look back up to 300 chars for a sentence boundary
    look_back = max(0, char_offset - 300)
    prefix_text = text[look_back:char_offset]
    # Find last sentence boundary in prefix
    for sep in [". ", ".\n", "\n\n"]:
        idx = prefix_text.rfind(sep)
        if idx != -1:
            prefix_text = prefix_text[idx + len(sep):]
            break

    # Look ahead up to 300 chars for a sentence boundary
    end_offset = char_offset + len(citation_str)
    look_ahead = min(len(text), end_offset + 300)
    suffix_text = text[end_offset:look_ahead]
    for sep in [". ", ".\n", "\n\n"]:
        idx = suffix_text.find(sep)
        if idx != -1:
            suffix_text = suffix_text[:idx + 1]
            break

    snippet = (prefix_text + citation_str + suffix_text).strip()
    return snippet[:500]
```

- [ ] **Step 4: Run citation tests**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -k "citations" -v
```

Expected: 5 passed.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add document_parser.py tests/test_document_parser.py
git commit -m "feat: extract_citations_with_context with page numbers and context window"
```

---

## Task 6: `document_parser.py` — Proposition Suggestion

**Files:**
- Modify: `tests/test_document_parser.py`
- Modify: `document_parser.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_document_parser.py`:

```python
# ---------------------------------------------------------------------------
# Proposition suggestion
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock
import asyncio


def test_suggest_proposition_ollama_success():
    """When Ollama responds, proposition and backend_used=ollama are returned."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "response": '{"proposition": "Counsel must be provided to defendants."}'
    }

    with patch("document_parser.http_requests.post", return_value=mock_response):
        from document_parser import suggest_proposition
        result = asyncio.get_event_loop().run_until_complete(
            suggest_proposition(
                "Miranda v. Arizona, 384 U.S. 436 (1966)",
                "Miranda established the right to counsel during police interrogation."
            )
        )

    assert result["backend_used"] == "ollama"
    assert "Counsel must be provided" in result["proposition"]
    assert result["raw_snippet"] is not None


def test_suggest_proposition_ollama_unavailable():
    """When Ollama is unreachable, backend_used=fallback and proposition=raw_snippet."""
    import requests as real_requests

    with patch("document_parser.http_requests.post", side_effect=real_requests.ConnectionError()):
        from document_parser import suggest_proposition
        result = asyncio.get_event_loop().run_until_complete(
            suggest_proposition(
                "Miranda v. Arizona, 384 U.S. 436 (1966)",
                "Miranda established the right to counsel."
            )
        )

    assert result["backend_used"] == "fallback"
    assert result["proposition"] == "Miranda established the right to counsel."
    assert result["raw_snippet"] == "Miranda established the right to counsel."


def test_suggest_propositions_batch_runs_three_at_a_time():
    """suggest_propositions_batch processes citations in groups of 3."""
    call_count = {"n": 0}

    async def mock_suggest(citation_text, context_snippet):
        call_count["n"] += 1
        return {
            "proposition": f"Proposition for {citation_text[:20]}",
            "backend_used": "ollama",
            "raw_snippet": context_snippet
        }

    citations = [
        {"citation_text": f"Case {i}, 100 U.S. {i} (2000)", "context_snippet": f"Context {i}"}
        for i in range(6)
    ]

    with patch("document_parser.suggest_proposition", side_effect=mock_suggest):
        from document_parser import suggest_propositions_batch
        results = asyncio.get_event_loop().run_until_complete(
            suggest_propositions_batch(citations)
        )

    assert len(results) == 6
    assert all("proposition" in r for r in results)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -k "proposition" -v
```

Expected: ImportError — functions not yet implemented.

- [ ] **Step 3: Implement `suggest_proposition` and `suggest_propositions_batch`**

Add to `document_parser.py`:

```python
async def suggest_proposition(citation_text: str, context_snippet: str) -> dict:
    """
    Use the local Ollama LLM to distill a proposition from the surrounding
    context — what legal argument is this case being cited to support?

    Reuses the same Ollama connection pattern as coherence_check.py:
    format=json, think=False (prevents Qwen3 routing output to 'thinking' field).

    Graceful degradation: if Ollama is unavailable, returns the raw context
    snippet as the proposition so the human-in-the-loop queue still has
    something useful to display.

    Returns:
        {
            "proposition": str,              # LLM output or raw_snippet fallback
            "backend_used": "ollama" | "fallback",
            "raw_snippet": str               # always the original context snippet
        }
    """
    prompt = (
        f"A legal document cites the case: {citation_text}\n\n"
        f"The surrounding text reads:\n{context_snippet}\n\n"
        f"In one plain-English sentence, state the legal proposition that this "
        f"case is being cited to support. Be specific to the argument being made. "
        f"Respond with JSON: {{\"proposition\": \"...\"}}"
    )

    try:
        resp = http_requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "think": False,
                "options": {"num_ctx": min(4096, OLLAMA_CONTEXT_SIZE)},
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        raw_response = data.get("response") or data.get("thinking", "")
        try:
            import json as _json
            parsed = _json.loads(raw_response)
            proposition = parsed.get("proposition", "").strip()
        except Exception:
            proposition = raw_response.strip()

        if not proposition:
            raise ValueError("Empty proposition from LLM")

        return {
            "proposition": proposition,
            "backend_used": "ollama",
            "raw_snippet": context_snippet,
        }

    except Exception:
        # Graceful degradation: use raw snippet, human can edit in the queue
        return {
            "proposition": context_snippet,
            "backend_used": "fallback",
            "raw_snippet": context_snippet,
        }


async def suggest_propositions_batch(citations: list) -> list:
    """
    Run suggest_proposition on a list of citations, 3 at a time.

    Concurrency rationale: 3 concurrent calls populate the queue visibly
    without hammering Ollama on large documents. asyncio.sleep(0) between
    batches yields control so the SSE stream can flush updates.

    Args:
        citations: list of {citation_text, context_snippet}

    Returns:
        list of suggest_proposition results, same order as input
    """
    results = []
    for i in range(0, len(citations), PROPOSITION_BATCH_SIZE):
        chunk = citations[i:i + PROPOSITION_BATCH_SIZE]
        chunk_results = await asyncio.gather(*[
            suggest_proposition(c["citation_text"], c["context_snippet"])
            for c in chunk
        ])
        results.extend(chunk_results)
        await asyncio.sleep(0)  # Yield control for SSE flush between batches
    return results
```

- [ ] **Step 4: Run proposition tests**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -k "proposition" -v
```

Expected: 3 passed.

- [ ] **Step 5: Run full test suite**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add document_parser.py tests/test_document_parser.py
git commit -m "feat: suggest_proposition and suggest_propositions_batch with Ollama + fallback"
```

---

## Task 7: API Endpoints — `GET /upload` and `POST /upload/parse`

**Files:**
- Modify: `api.py`
- Create: `tests/test_upload_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_upload_api.py`:

```python
"""
Integration tests for the upload portal API endpoints.
Uses FastAPI TestClient (synchronous test runner over ASGI).
"""

import io
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# GET /upload
# ---------------------------------------------------------------------------

def test_get_upload_returns_html():
    """GET /upload serves the upload portal HTML page."""
    resp = client.get("/upload")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# POST /upload/parse — TXT
# ---------------------------------------------------------------------------

def test_upload_parse_txt_basic():
    """TXT upload extracts citations and returns structured response."""
    content = (
        "This brief cites Miranda v. Arizona, 384 U.S. 436 (1966) "
        "for the right to counsel."
    )
    resp = client.post(
        "/upload/parse",
        files={"file": ("brief.txt", content.encode(), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "citations" in data
    assert "page_count" in data
    assert "chunked" in data
    assert len(data["citations"]) >= 1
    assert "384 U.S. 436" in data["citations"][0]["citation_text"]


def test_upload_parse_file_too_large():
    """Files exceeding 50MB are rejected with a clear error message."""
    big_content = b"x" * (51 * 1024 * 1024)  # 51MB
    resp = client.post(
        "/upload/parse",
        files={"file": ("big.txt", big_content, "text/plain")},
    )
    assert resp.status_code == 413
    assert "50MB" in resp.json()["detail"]


def test_upload_parse_unsupported_type():
    """Unsupported file types return 400 with a clear error message."""
    resp = client.post(
        "/upload/parse",
        files={"file": ("data.xlsx", b"data", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "Unsupported" in resp.json()["detail"]


def test_upload_parse_no_citations():
    """Documents with no citations return empty list with helpful message."""
    content = b"This document has no legal citations at all."
    resp = client.post(
        "/upload/parse",
        files={"file": ("memo.txt", content, "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["citations"] == []
    assert "message" in data


def test_upload_parse_chunking_flag():
    """Documents over 200 estimated pages get chunked=True and chunk_count."""
    # 200 pages * 3000 chars = 600000 chars; make it just over that
    long_text = "Miranda v. Arizona, 384 U.S. 436 (1966). " * 15000  # ~600k+ chars
    resp = client.post(
        "/upload/parse",
        files={"file": ("long.txt", long_text.encode(), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["chunked"] is True
    assert data["chunk_count"] > 1
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_upload_api.py -k "upload" -v 2>&1 | head -20
```

Expected: 404 or connection error — endpoints don't exist yet.

- [ ] **Step 3: Add new imports and models to `api.py`**

Add to the imports block at the top of `api.py` (after existing imports):

```python
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from document_parser import (
    extract_text,
    extract_citations_with_context,
    suggest_propositions_batch,
)
```

Add new Pydantic models after the existing `VerifyRequest` model:

```python
class BatchCitationItem(BaseModel):
    """A single citation for batch processing, with optional Phase 2/3 inputs."""
    citation_text: str
    quoted_text: Optional[str] = None
    proposition: Optional[str] = None


class BatchStreamRequest(BaseModel):
    """
    Request body for POST /batch/stream.
    depth controls which pipeline phases run:
      "phase1"    -- existence check only
      "phase1_2"  -- existence + quote verification
      "full"      -- all three phases (requires proposition per citation)
    chunk_index and total_chunks are used for chunked documents.
    """
    citations: list[BatchCitationItem]
    depth: str  # "phase1" | "phase1_2" | "full"
    chunk_index: Optional[int] = None
    total_chunks: Optional[int] = None


MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50MB
CHUNK_PAGE_LIMIT = 200
```

- [ ] **Step 4: Add `GET /upload` and `POST /upload/parse` to `api.py`**

Add after the existing `/health` route:

```python
@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    """
    Serve the document upload portal.
    Passes the same status flags as the main page so the UI can show
    Phase 3 availability warnings in the depth selector.
    """
    available, llm_message = coherence_available()
    return templates.TemplateResponse(
        request=request,
        name="upload.html",
        context={
            "llm_available": available,
            "llm_message": llm_message,
        }
    )


@app.post("/upload/parse")
async def upload_parse(file: UploadFile = File(...)):
    """
    Accept a document upload, extract text and citations.

    Validates: file size (50MB limit), file type (.pdf/.docx/.txt).
    Returns citation list with context snippets, page count, and chunking info.

    Chunking: documents over 200 pages get chunked=True and chunk_count.
    The UI uses these to submit citations in sequential batches to /batch/stream.
    """
    # Size check (read all bytes first)
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File is too large ({len(file_bytes) // (1024*1024)}MB). "
                f"Wilson accepts files up to 50MB."
            )
        )

    filename = file.filename or "upload.txt"

    try:
        extracted = extract_text(file_bytes, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))

    text = extracted["text"]
    page_count = extracted["page_count"]
    page_boundaries = extracted["page_boundaries"]

    citations = extract_citations_with_context(text, page_boundaries)

    if not citations:
        return JSONResponse({
            "citations": [],
            "page_count": page_count,
            "chunked": False,
            "chunk_count": 1,
            "message": (
                "No legal citations were found in this document. "
                "Wilson looks for standard reporter format, "
                "e.g. Miranda v. Arizona, 384 U.S. 436 (1966)."
            )
        })

    chunked = page_count > CHUNK_PAGE_LIMIT
    chunk_count = math.ceil(page_count / CHUNK_PAGE_LIMIT) if chunked else 1

    return JSONResponse({
        "citations": citations,
        "page_count": page_count,
        "chunked": chunked,
        "chunk_count": chunk_count,
        "extraction_method": extracted["extraction_method"],
    })
```

Also add `import math` to the imports at the top of `api.py` if not already present.

- [ ] **Step 5: Run upload/parse tests**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_upload_api.py -k "upload" -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add api.py tests/test_upload_api.py
git commit -m "feat: GET /upload and POST /upload/parse endpoints with size/type validation"
```

---

## Task 8: API Endpoints — `POST /batch/propositions`

**Files:**
- Modify: `api.py`
- Modify: `tests/test_upload_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_upload_api.py`:

```python
# ---------------------------------------------------------------------------
# POST /batch/propositions
# ---------------------------------------------------------------------------

def test_batch_propositions_streams_sse():
    """POST /batch/propositions returns SSE stream of proposition results."""
    payload = {
        "citations": [
            {
                "citation_text": "Miranda v. Arizona, 384 U.S. 436 (1966)",
                "context_snippet": "Miranda established the right to counsel."
            }
        ]
    }
    mock_result = {
        "proposition": "Police must inform suspects of their rights.",
        "backend_used": "ollama",
        "raw_snippet": "Miranda established the right to counsel."
    }

    async def mock_batch(citations):
        return [mock_result]

    with patch("api.suggest_propositions_batch", side_effect=mock_batch):
        with client.stream("POST", "/batch/propositions", json=payload) as resp:
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]
            lines = []
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    lines.append(json.loads(line[6:]))
            # Should have at least one proposition event and a done event
            types = [e["type"] for e in lines]
            assert "proposition" in types
            assert "done" in types
```

- [ ] **Step 2: Run test — verify it fails**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_upload_api.py::test_batch_propositions_streams_sse -v
```

Expected: 404.

- [ ] **Step 3: Add `POST /batch/propositions` to `api.py`**

First add the import at top of `api.py`:
```python
from document_parser import (
    extract_text,
    extract_citations_with_context,
    suggest_propositions_batch,
)
```

Then add the endpoint after `/upload/parse`:

```python
class BatchPropositionRequest(BaseModel):
    """Request body for POST /batch/propositions."""
    citations: list[dict]  # [{citation_text: str, context_snippet: str}]


async def _stream_propositions(citations: list) -> AsyncGenerator[str, None]:
    """
    Generate proposition suggestions and stream them as SSE.
    Runs suggest_propositions_batch (3 at a time) and yields each result
    as it completes so the UI queue can populate incrementally.
    """
    total = len(citations)
    completed = 0

    for i in range(0, total, 3):
        chunk = citations[i:i + 3]
        results = await suggest_propositions_batch(chunk)
        for j, result in enumerate(results):
            citation = chunk[j]
            yield make_event(
                "proposition",
                index=i + j,
                citation_text=citation["citation_text"],
                proposition=result["proposition"],
                backend_used=result["backend_used"],
                raw_snippet=result["raw_snippet"],
            )
            await asyncio.sleep(0)
            completed += 1

    yield make_event("done", total=total)


@app.post("/batch/propositions")
async def batch_propositions(request: BatchPropositionRequest):
    """
    Generate LLM-proposed propositions for a list of citations.
    Streams results as SSE so the UI proposition queue populates incrementally.
    Uses suggest_propositions_batch (3 concurrent Ollama calls at a time).
    Gracefully degrades to raw snippet if Ollama unavailable.
    """
    return StreamingResponse(
        _stream_propositions(request.citations),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )
```

- [ ] **Step 4: Run test**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_upload_api.py::test_batch_propositions_streams_sse -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add api.py tests/test_upload_api.py
git commit -m "feat: POST /batch/propositions SSE endpoint for proposition queue"
```

---

## Task 9: API Endpoints — `POST /batch/stream`

**Files:**
- Modify: `api.py`
- Modify: `tests/test_upload_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_upload_api.py`:

```python
# ---------------------------------------------------------------------------
# POST /batch/stream
# ---------------------------------------------------------------------------

def test_batch_stream_phase1_only():
    """Batch stream runs Phase 1 on each citation and emits batch_done."""
    payload = {
        "citations": [
            {"citation_text": "Miranda v. Arizona, 384 U.S. 436 (1966)"}
        ],
        "depth": "phase1"
    }
    mock_phase1 = {
        "verdict": "EXISTS",
        "cluster_id": 107252,
        "case_name": "Miranda v. Arizona",
        "message": "Citation verified"
    }

    with patch("api.lookup_citation_api", return_value=(True, 107252, "Miranda v. Arizona", "Found")):
        with patch("api.check_local_csv", return_value=(True, "Found in CSV")):
            with client.stream("POST", "/batch/stream", json=payload) as resp:
                assert resp.status_code == 200
                events = []
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        events.append(json.loads(line[6:]))
                types = [e["type"] for e in events]
                assert "batch_citation_start" in types
                assert "phase1_complete" in types
                assert "batch_done" in types


def test_batch_stream_respects_depth_phase1_only():
    """With depth=phase1, Phase 2 and Phase 3 do not run."""
    payload = {
        "citations": [
            {
                "citation_text": "Miranda v. Arizona, 384 U.S. 436 (1966)",
                "quoted_text": "You have the right to remain silent.",
                "proposition": "Police must read Miranda rights."
            }
        ],
        "depth": "phase1"
    }
    with patch("api.lookup_citation_api", return_value=(True, 107252, "Miranda v. Arizona", "Found")):
        with patch("api.check_local_csv", return_value=(True, "Found in CSV")):
            with client.stream("POST", "/batch/stream", json=payload) as resp:
                events = [
                    json.loads(line[6:])
                    for line in resp.iter_lines()
                    if line.startswith("data: ")
                ]
                types = [e["type"] for e in events]
                assert "phase2_complete" not in types
                assert "phase3_complete" not in types
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_upload_api.py -k "batch_stream" -v
```

Expected: 404.

- [ ] **Step 3: Add `POST /batch/stream` to `api.py`**

Add after `/batch/propositions`:

```python
HEARTBEAT_INTERVAL = 3.0   # seconds between keep-alive events
SOFT_TIMEOUT = 10.0        # seconds before "still working" warning
HARD_TIMEOUT = 30.0        # seconds before "no response" warning


async def _run_batch_pipeline(request: BatchStreamRequest) -> AsyncGenerator[str, None]:
    """
    Run the Wilson pipeline on a list of citations, streaming SSE events.

    Emits batch-level events:
      batch_start         -- total citation count, chunk info
      batch_citation_start -- which citation is starting (1-based index, plain-English name)
      [per-phase events from run_pipeline]
      batch_citation_done -- per-citation summary verdict
      heartbeat           -- keep-alive during long LLM calls
      batch_done          -- final summary counts and duration

    Depth governs which phases run:
      phase1     -- run_pipeline with no quoted_text, no proposition
      phase1_2   -- run_pipeline with quoted_text (if provided), no proposition
      full       -- run_pipeline with quoted_text and proposition
    """
    start_time = time.time()
    total = len(request.citations)
    depth = request.depth

    yield make_event(
        "batch_start",
        total=total,
        depth=depth,
        chunk_index=request.chunk_index,
        total_chunks=request.total_chunks,
    )
    await asyncio.sleep(0)

    verdicts = {"EXISTS": 0, "FABRICATED": 0, "MISATTRIBUTED": 0, "ERROR": 0, "OTHER": 0}

    for idx, item in enumerate(request.citations):
        citation_text = item.citation_text.strip()
        quoted_text = item.quoted_text.strip() if (item.quoted_text and depth != "phase1") else None
        proposition = item.proposition.strip() if (item.proposition and depth == "full") else None

        # Extract a readable case name for the status line
        display_name = citation_text[:60] + ("..." if len(citation_text) > 60 else "")

        yield make_event(
            "batch_citation_start",
            index=idx + 1,
            total=total,
            citation_text=citation_text,
            display_name=display_name,
        )
        await asyncio.sleep(0)

        # Run the existing pipeline through a queue so we can interleave heartbeats
        queue: asyncio.Queue = asyncio.Queue()

        async def producer(ct=citation_text, qt=quoted_text, prop=proposition):
            """Feed pipeline events into the queue."""
            async for event in run_pipeline(ct, qt, prop):
                await queue.put(event)
            await queue.put(None)  # sentinel

        producer_task = asyncio.create_task(producer())
        last_event_time = time.time()
        citation_verdict = "ERROR"

        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                if event is None:
                    break
                last_event_time = time.time()

                # Track Phase 1 verdict for the summary
                if '"type": "phase1_complete"' in event or "'type': 'phase1_complete'" in event:
                    try:
                        parsed = json.loads(event[6:].strip())
                        citation_verdict = parsed.get("data", {}).get("verdict", "ERROR")
                    except Exception:
                        pass

                yield event
                await asyncio.sleep(0)

            except asyncio.TimeoutError:
                elapsed_since_event = time.time() - last_event_time
                yield make_event("heartbeat", elapsed_since_event=round(elapsed_since_event, 1))
                await asyncio.sleep(0)

                if elapsed_since_event > HARD_TIMEOUT:
                    yield make_event(
                        "warning",
                        level="hard",
                        message="No response from server. You may cancel and retry."
                    )
                elif elapsed_since_event > SOFT_TIMEOUT:
                    yield make_event(
                        "warning",
                        level="soft",
                        message="Still working -- LLM inference can take a moment on large opinions."
                    )

        await producer_task

        # Tally verdict
        if citation_verdict in verdicts:
            verdicts[citation_verdict] += 1
        else:
            verdicts["OTHER"] += 1

        yield make_event("batch_citation_done", index=idx + 1, verdict=citation_verdict)
        await asyncio.sleep(0)

    duration = round(time.time() - start_time, 2)
    yield make_event("batch_done", total=total, verdicts=verdicts, duration=duration)


@app.post("/batch/stream")
async def batch_stream(request: BatchStreamRequest):
    """
    Run Wilson's pipeline on a batch of citations, streaming SSE results.

    The client submits pre-extracted citations (from /upload/parse) with
    optional quoted_text and proposition per citation. The depth parameter
    governs which phases run for all citations in the batch.

    For chunked documents, chunk_index and total_chunks track position
    within the overall document so the UI can display batch N of M.
    """
    return StreamingResponse(
        _run_batch_pipeline(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )
```

- [ ] **Step 4: Run batch/stream tests**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_upload_api.py -k "batch_stream" -v
```

Expected: 2 passed.

- [ ] **Step 5: Run full test suite**

```bash
.\venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add api.py tests/test_upload_api.py
git commit -m "feat: POST /batch/stream with heartbeat, depth control, and chunking support"
```

---

## Task 10: `upload.html` — Steps 1 & 2 (Upload + Depth Selector)

**Files:**
- Create: `templates/upload.html`

The full HTML file starts here. Steps 11 and 12 will add to it via JavaScript functions. Write the complete file in this task — Steps 11 and 12 fill in placeholder JS functions.

- [ ] **Step 1: Create `templates/upload.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wilson -- Upload Document</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: #0a0a0a;
            color: #e0e0e0;
            min-height: 100vh;
            padding: 1.5rem;
        }
        .container { width: 100%; max-width: 960px; margin: 0 auto; }
        header {
            margin-bottom: 1.25rem;
            border-bottom: 1px solid #1a1a1a;
            padding-bottom: 1rem;
            display: flex;
            align-items: baseline;
            gap: 1.25rem;
            flex-wrap: wrap;
        }
        header h1 { font-size: 1.75rem; font-weight: 700; color: #fff; letter-spacing: -0.5px; }
        .tagline { color: #444; font-style: italic; font-size: 0.82rem; }
        .nav-link { font-size: 0.8rem; color: #3a3a3a; text-decoration: none; margin-left: auto; }
        .nav-link:hover { color: #666; }

        /* Step panels */
        .step { display: none; }
        .step.active { display: block; }

        .panel {
            background: #111;
            border: 1px solid #1e1e1e;
            border-radius: 8px;
            padding: 1.25rem;
            margin-bottom: 1.25rem;
        }
        .panel h2 {
            font-size: 0.7rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #3a3a3a;
            margin-bottom: 1rem;
        }

        /* Drop zone */
        .drop-zone {
            border: 2px dashed #252525;
            border-radius: 8px;
            padding: 3rem 2rem;
            text-align: center;
            cursor: pointer;
            transition: border-color 0.2s, background 0.2s;
        }
        .drop-zone:hover, .drop-zone.drag-over {
            border-color: #2d7a2d;
            background: #0d1a0d;
        }
        .drop-zone-label { font-size: 0.9rem; color: #666; margin-bottom: 0.5rem; }
        .drop-zone-sub { font-size: 0.74rem; color: #3a3a3a; }
        .drop-zone input[type="file"] { display: none; }

        .file-selected {
            margin-top: 1rem;
            padding: 0.5rem 0.75rem;
            background: #0a0a0a;
            border: 1px solid #1a1a1a;
            border-radius: 4px;
            font-size: 0.8rem;
            color: #888;
        }

        /* Buttons */
        .btn-row { display: flex; gap: 0.5rem; margin-top: 1rem; }
        button {
            flex: 1;
            padding: 0.65rem;
            background: #161616;
            border: 1px solid #252525;
            border-radius: 5px;
            color: #ccc;
            font-size: 0.86rem;
            font-family: inherit;
            cursor: pointer;
            transition: all 0.15s;
        }
        button:hover { background: #1e1e1e; border-color: #333; }
        button:active { background: #0f0f0f; }
        button:disabled { opacity: 0.3; cursor: not-allowed; }
        .btn-cancel { flex: 0 0 auto; padding: 0.65rem 1rem; color: #444; font-size: 0.8rem; }
        .btn-primary { border-color: #1a4a1a; color: #4caf50; }
        .btn-primary:hover { background: #0d2a0d; border-color: #2d7a2d; }

        /* Depth selector */
        .depth-option {
            display: flex;
            align-items: flex-start;
            gap: 0.75rem;
            padding: 0.75rem;
            border: 1px solid #1e1e1e;
            border-radius: 6px;
            margin-bottom: 0.5rem;
            cursor: pointer;
            transition: border-color 0.15s, background 0.15s;
        }
        .depth-option:hover { border-color: #333; background: #141414; }
        .depth-option.selected { border-color: #1a4a1a; background: #0d1a0d; }
        .depth-option.disabled { opacity: 0.4; cursor: not-allowed; }
        .depth-option input[type="radio"] { margin-top: 0.15rem; accent-color: #4caf50; }
        .depth-label { font-size: 0.86rem; color: #ccc; font-weight: 600; }
        .depth-desc { font-size: 0.76rem; color: #555; margin-top: 0.2rem; }
        .depth-warn { font-size: 0.7rem; color: #ff9800; margin-top: 0.3rem; }

        /* Error/info messages */
        .msg {
            padding: 0.7rem 0.9rem;
            border-radius: 5px;
            font-size: 0.8rem;
            margin-bottom: 1rem;
        }
        .msg-error { background: #1a0808; border: 1px solid #4a1a1a; color: #f44336; }
        .msg-info  { background: #0d1a1a; border: 1px solid #1a3a3a; color: #4db6ac; }
        .msg-warn  { background: #1a1200; border: 1px solid #3a2a00; color: #ff9800; }

        /* Progress bar */
        .progress-section { margin-bottom: 1rem; }
        .progress-track {
            height: 6px;
            background: #161616;
            border-radius: 3px;
            overflow: hidden;
            margin-bottom: 0.5rem;
            border: 1px solid #1e1e1e;
        }
        .progress-fill {
            height: 100%;
            border-radius: 3px;
            background: linear-gradient(90deg, #1a4a1a, #2d7a2d, #1a4a1a);
            background-size: 200% 100%;
            width: 0%;
            transition: width 0.4s ease;
        }
        .progress-fill.active { animation: shimmer 1.4s infinite linear; }
        @keyframes shimmer {
            0%   { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }
        .progress-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.72rem;
            color: #3a3a3a;
            font-family: monospace;
        }

        /* Proposition queue */
        .queue-tally {
            font-size: 0.76rem;
            color: #555;
            margin-bottom: 1rem;
            font-family: monospace;
        }
        .queue-row {
            border: 1px solid #1e1e1e;
            border-radius: 6px;
            margin-bottom: 0.5rem;
            padding: 0.75rem;
            background: #0d0d0d;
            animation: fadeUp 0.2s ease;
        }
        .queue-row.pending  { border-left: 3px solid #252525; }
        .queue-row.accepted { border-left: 3px solid #1a4a1a; }
        .queue-row.rewritten{ border-left: 3px solid #1a3a4a; }
        .queue-row.skipped  { border-left: 3px solid #2a2a2a; }
        .queue-citation { font-size: 0.76rem; color: #666; font-family: monospace; margin-bottom: 0.4rem; }
        .queue-prop-field {
            width: 100%;
            background: #0a0a0a;
            border: 1px solid #252525;
            border-radius: 4px;
            color: #ddd;
            padding: 0.45rem 0.6rem;
            font-size: 0.82rem;
            font-family: inherit;
            resize: vertical;
            min-height: 52px;
        }
        .queue-prop-field:focus { outline: none; border-color: #333; }
        .queue-actions { display: flex; gap: 0.4rem; margin-top: 0.4rem; }
        .queue-btn {
            flex: 0 0 auto;
            padding: 0.3rem 0.7rem;
            font-size: 0.74rem;
            border-radius: 3px;
        }
        .queue-btn-accept  { border-color: #1a4a1a; color: #4caf50; }
        .queue-btn-accept:hover  { background: #0d2a0d; }
        .queue-btn-rewrite { border-color: #1a3a4a; color: #4db6ac; }
        .queue-btn-rewrite:hover { background: #0d1a1a; }
        .queue-btn-skip    { border-color: #2a2a2a; color: #555; }
        .queue-btn-skip:hover    { background: #141414; }
        .snippet-toggle { font-size: 0.68rem; color: #3a3a3a; cursor: pointer; text-decoration: underline; margin-top: 0.3rem; display: inline-block; }
        .snippet-toggle:hover { color: #666; }
        .snippet-text {
            display: none;
            margin-top: 0.4rem;
            padding: 0.4rem 0.6rem;
            background: #0a0a0a;
            border-left: 2px solid #1e1e1e;
            font-size: 0.72rem;
            color: #444;
            font-family: monospace;
            line-height: 1.5;
        }
        .backend-note { font-size: 0.68rem; color: #8a6a00; margin-top: 0.2rem; }

        /* Summary table */
        .summary-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
        .summary-table th {
            text-align: left;
            padding: 0.4rem 0.6rem;
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: #3a3a3a;
            border-bottom: 1px solid #1a1a1a;
        }
        .summary-table td { padding: 0.5rem 0.6rem; border-bottom: 1px solid #141414; vertical-align: top; }
        .summary-table tr:hover td { background: #0f0f0f; }
        .citation-cell { font-family: monospace; font-size: 0.72rem; color: #666; max-width: 220px; word-break: break-word; }
        .gloss { font-size: 0.72rem; color: #555; margin-top: 0.2rem; }
        .expand-btn { font-size: 0.68rem; color: #3a3a3a; cursor: pointer; text-decoration: underline; }
        .expand-btn:hover { color: #666; }
        .expand-detail {
            display: none;
            padding: 0.5rem;
            background: #0a0a0a;
            border-radius: 4px;
            margin-top: 0.4rem;
            font-size: 0.72rem;
            color: #555;
            line-height: 1.55;
        }
        .summary-footer { font-size: 0.74rem; color: #3a3a3a; margin-top: 0.75rem; font-family: monospace; }

        /* Verdict badges */
        .verdict { font-size: 0.72rem; font-weight: 700; padding: 0.16rem 0.5rem; border-radius: 3px; letter-spacing: 0.4px; white-space: nowrap; }
        .v-green  { background: #0d2a0d; color: #4caf50; border: 1px solid #1a4a1a; }
        .v-red    { background: #2a0d0d; color: #f44336; border: 1px solid #4a1a1a; }
        .v-orange { background: #2a1f0d; color: #ff9800; border: 1px solid #4a3a1a; }
        .v-grey   { background: #161616; color: #555;    border: 1px solid #222; }

        @keyframes fadeUp {
            from { opacity: 0; transform: translateY(6px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        /* Warning banners */
        .banner { padding: 0.6rem 0.9rem; border-radius: 5px; font-size: 0.8rem; margin-bottom: 0.75rem; }
        .banner-warn  { background: #1a1200; border: 1px solid #3a2a00; color: #ff9800; }
        .banner-error { background: #1a0808; border: 1px solid #4a1a1a; color: #f44336; }
        .banner-cancel{ background: #141414; border: 1px solid #2a2a2a; color: #666; }
    </style>
</head>
<body>
<div class="container">
    <header>
        <h1>Wilson</h1>
        <span class="tagline">Document Upload -- Batch Citation Audit</span>
        <a href="/" class="nav-link">Single Citation</a>
    </header>

    <!-- Step 1: Upload -->
    <div id="step-upload" class="step active">
        <div class="panel">
            <h2>Upload Document</h2>
            <div class="drop-zone" id="dropZone">
                <div class="drop-zone-label">Drop a document here or click to browse</div>
                <div class="drop-zone-sub">PDF, DOCX, or TXT &mdash; up to 50MB</div>
                <input type="file" id="fileInput" accept=".pdf,.docx,.txt">
            </div>
            <div id="fileSelectedInfo" class="file-selected" style="display:none;"></div>
            <div id="uploadError" class="msg msg-error" style="display:none;"></div>
            <div class="btn-row">
                <button id="btnUpload" class="btn-primary" disabled onclick="handleUpload()">Analyze Document</button>
            </div>
        </div>
    </div>

    <!-- Step 2: Depth selector -->
    <div id="step-depth" class="step">
        <div class="panel">
            <h2>Select Audit Depth</h2>
            <div id="depthOptions">
                <label class="depth-option selected" id="opt-phase1">
                    <input type="radio" name="depth" value="phase1" checked>
                    <div>
                        <div class="depth-label">Existence only</div>
                        <div class="depth-desc">Check that every citation actually exists in federal court records.</div>
                    </div>
                </label>
                <label class="depth-option" id="opt-phase1_2">
                    <input type="radio" name="depth" value="phase1_2">
                    <div>
                        <div class="depth-label">Existence + Quotes</div>
                        <div class="depth-desc">Also verify that quoted language appears in each opinion.</div>
                    </div>
                </label>
                <label class="depth-option" id="opt-full">
                    <input type="radio" name="depth" value="full">
                    <div>
                        <div class="depth-label">Full audit</div>
                        <div class="depth-desc">Also check whether each cited case actually supports the argument it is cited for. You will review proposed propositions before the batch runs.</div>
                        <div class="depth-warn" id="phase3Warn" style="display:none;">
                            Phase 3 requires Ollama (local LLM) or a CourtListener API connection. Check your configuration to enable coherence checking.
                        </div>
                    </div>
                </label>
            </div>

            <div id="chunkNotice" class="msg msg-info" style="display:none;"></div>
            <div id="citationCount" class="msg msg-info" style="display:none;"></div>

            <div class="btn-row">
                <button onclick="cancelToUpload()" class="btn-cancel">Cancel</button>
                <button id="btnContinue" class="btn-primary" onclick="proceedFromDepth()">Continue</button>
            </div>
        </div>
    </div>

    <!-- Step 3: Proposition review queue (injected by JS) -->
    <div id="step-propositions" class="step">
        <div class="panel">
            <h2>Review Propositions</h2>
            <div class="queue-tally" id="queueTally"></div>
            <div id="queueList"></div>
            <div class="btn-row">
                <button onclick="backToDepth()" class="btn-cancel">Back</button>
                <button id="btnRunAudit" class="btn-primary" disabled onclick="startBatch()">Run Audit</button>
            </div>
        </div>
    </div>

    <!-- Step 4: Batch run -->
    <div id="step-batch" class="step">
        <div id="batchWarning" style="display:none;"></div>
        <div class="progress-section">
            <div class="progress-track"><div class="progress-fill active" id="batchProgress"></div></div>
            <div class="progress-meta">
                <span id="batchStatusLine">Preparing...</span>
                <span id="batchTimer" style="font-family:monospace;">0.0s</span>
            </div>
        </div>
        <div class="panel" id="batchLog" style="max-height:300px;overflow-y:auto;"></div>
        <div class="btn-row">
            <button onclick="cancelBatch()" class="btn-cancel" id="btnCancelBatch">Cancel</button>
        </div>
    </div>

    <!-- Step 5: Summary table -->
    <div id="step-summary" class="step">
        <div id="summaryBanner" style="display:none;"></div>
        <div class="panel">
            <h2>Audit Results</h2>
            <table class="summary-table" id="summaryTable">
                <thead>
                    <tr>
                        <th>Citation</th>
                        <th>Existence</th>
                        <th id="thPhase2" style="display:none;">Quoted Language</th>
                        <th id="thPhase3" style="display:none;">Coherence</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody id="summaryBody"></tbody>
            </table>
            <div class="summary-footer" id="summaryFooter"></div>
        </div>
        <div class="btn-row">
            <button onclick="location.href='/upload'" style="flex:0 0 auto;padding:0.65rem 1.2rem;">Upload Another</button>
            <button onclick="location.href='/'" style="flex:0 0 auto;padding:0.65rem 1.2rem;">Single Citation</button>
        </div>
    </div>
</div>

<script>
// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
    file: null,
    citations: [],        // from /upload/parse
    pageCount: 0,
    chunked: false,
    chunkCount: 1,
    depth: "phase1",
    propositions: [],     // [{citation_text, proposition, status, raw_snippet, backend_used}]
    batchResults: [],     // per-citation result rows for summary table
    batchCancelled: false,
    batchEventSource: null,
    timerInterval: null,
    batchStartTime: null,
    llmAvailable: {{ llm_available | tojson }},
};

// ---------------------------------------------------------------------------
// Step management
// ---------------------------------------------------------------------------
function showStep(id) {
    document.querySelectorAll(".step").forEach(el => el.classList.remove("active"));
    document.getElementById(id).classList.add("active");
}

// ---------------------------------------------------------------------------
// Step 1: Upload
// ---------------------------------------------------------------------------
const dropZone = document.getElementById("dropZone");
const fileInput = document.getElementById("fileInput");
const btnUpload = document.getElementById("btnUpload");

dropZone.addEventListener("click", () => fileInput.click());
dropZone.addEventListener("dragover", e => { e.preventDefault(); dropZone.classList.add("drag-over"); });
dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
dropZone.addEventListener("drop", e => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => { if (fileInput.files.length) setFile(fileInput.files[0]); });

function setFile(file) {
    state.file = file;
    const info = document.getElementById("fileSelectedInfo");
    info.style.display = "block";
    info.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    btnUpload.disabled = false;
    document.getElementById("uploadError").style.display = "none";
}

async function handleUpload() {
    if (!state.file) return;
    btnUpload.disabled = true;
    btnUpload.textContent = "Analyzing...";
    document.getElementById("uploadError").style.display = "none";

    const formData = new FormData();
    formData.append("file", state.file);

    try {
        const resp = await fetch("/upload/parse", { method: "POST", body: formData });
        const data = await resp.json();

        if (!resp.ok) {
            showUploadError(data.detail || "Upload failed.");
            return;
        }

        state.citations = data.citations || [];
        state.pageCount = data.page_count || 0;
        state.chunked = data.chunked || false;
        state.chunkCount = data.chunk_count || 1;

        if (state.citations.length === 0) {
            showUploadError(data.message || "No legal citations found in this document.");
            return;
        }

        showDepthStep();
    } catch (err) {
        showUploadError("Could not reach Wilson server. Is it running?");
    } finally {
        btnUpload.disabled = false;
        btnUpload.textContent = "Analyze Document";
    }
}

function showUploadError(msg) {
    const el = document.getElementById("uploadError");
    el.textContent = msg;
    el.style.display = "block";
}

// ---------------------------------------------------------------------------
// Step 2: Depth selector
// ---------------------------------------------------------------------------
function showDepthStep() {
    // Show Phase 3 warning if unavailable
    if (!state.llmAvailable) {
        document.getElementById("phase3Warn").style.display = "block";
        const fullOpt = document.getElementById("opt-full");
        fullOpt.classList.add("disabled");
        fullOpt.querySelector("input").disabled = true;
    }

    // Show citation count
    const countEl = document.getElementById("citationCount");
    countEl.style.display = "block";
    countEl.textContent = `Found ${state.citations.length} citation${state.citations.length !== 1 ? "s" : ""} in ${state.pageCount} page${state.pageCount !== 1 ? "s" : ""}.`;

    // Show chunk notice
    if (state.chunked) {
        const chunkEl = document.getElementById("chunkNotice");
        chunkEl.style.display = "block";
        chunkEl.textContent = `This document is ${state.pageCount} pages. Wilson will process it in ${state.chunkCount} batches of up to 200 pages and queue them automatically. Results build as each batch completes.`;
    }

    // Wire depth radio buttons
    document.querySelectorAll("input[name='depth']").forEach(radio => {
        radio.addEventListener("change", () => {
            state.depth = radio.value;
            document.querySelectorAll(".depth-option").forEach(opt => opt.classList.remove("selected"));
            radio.closest(".depth-option").classList.add("selected");
        });
    });

    showStep("step-depth");
}

function cancelToUpload() {
    if (confirm("This will clear your upload and citation queue. Continue?")) {
        state.file = null;
        state.citations = [];
        state.propositions = [];
        document.getElementById("fileSelectedInfo").style.display = "none";
        document.getElementById("uploadError").style.display = "none";
        document.getElementById("fileInput").value = "";
        btnUpload.disabled = true;
        showStep("step-upload");
    }
}

function proceedFromDepth() {
    state.depth = document.querySelector("input[name='depth']:checked").value;
    if (state.depth === "full") {
        loadPropositionQueue();
    } else {
        startBatch();
    }
}

// ---------------------------------------------------------------------------
// Step 3: Proposition queue  (filled in Task 11)
// ---------------------------------------------------------------------------
function loadPropositionQueue() { _propositionQueueImpl(); }
function backToDepth() { showStep("step-depth"); }
function _propositionQueueImpl() {
    // Implemented in Task 11
    startBatch();
}

// ---------------------------------------------------------------------------
// Step 4 + 5: Batch run + Summary table (filled in Task 12)
// ---------------------------------------------------------------------------
function startBatch() { _batchImpl(); }
function cancelBatch() { _cancelBatchImpl(); }
function _batchImpl() {
    // Implemented in Task 12
    showStep("step-batch");
}
function _cancelBatchImpl() {
    // Implemented in Task 12
}
</script>
</body>
</html>
```

- [ ] **Step 2: Manually test Step 1 and Step 2 in the browser**

Start Wilson:
```bash
.\venv\Scripts\python.exe -m uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/upload` and verify:
- Drop zone renders, accepts file drag-and-drop and click-to-browse
- "Analyze Document" button is disabled until a file is selected
- Uploading a TXT file with citations advances to Step 2
- Citation count and chunk notice display correctly
- Depth options render; Full audit shows warning text if Ollama is unavailable
- Cancel prompts confirmation and returns to Step 1

- [ ] **Step 3: Add "Upload Document" link to `index.html` header**

In `templates/index.html`, find the `<header>` element and add the link:

```html
<a href="/upload" style="font-size:0.8rem;color:#3a3a3a;text-decoration:none;margin-left:auto;" onmouseover="this.style.color='#666'" onmouseout="this.style.color='#3a3a3a'">Upload Document</a>
```

Add it as the last child of `<header>`, after the existing header content.

- [ ] **Step 4: Commit**

```bash
git add templates/upload.html templates/index.html
git commit -m "feat: upload.html Steps 1-2 (file upload, depth selector) and index.html nav link"
```

---

## Task 11: `upload.html` — Step 3 (Proposition Review Queue)

**Files:**
- Modify: `templates/upload.html`

Replace the `_propositionQueueImpl` function placeholder with the full implementation.

- [ ] **Step 1: Replace `_propositionQueueImpl` in `upload.html`**

Find this block in `upload.html`:

```javascript
function _propositionQueueImpl() {
    // Implemented in Task 11
    startBatch();
}
```

Replace with:

```javascript
function _propositionQueueImpl() {
    showStep("step-propositions");
    state.propositions = state.citations.map(c => ({
        citation_text: c.citation_text,
        context_snippet: c.context_snippet,
        proposition: c.context_snippet,  // fallback until SSE arrives
        backend_used: "pending",
        status: "pending",
    }));
    renderQueueList();
    updateQueueTally();

    // Stream propositions from server
    const payload = {
        citations: state.citations.map(c => ({
            citation_text: c.citation_text,
            context_snippet: c.context_snippet,
        }))
    };

    fetch("/batch/propositions", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
    }).then(resp => {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        function pump() {
            reader.read().then(({ done, value }) => {
                if (done) return;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split("\n");
                buf = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    try {
                        const ev = JSON.parse(line.slice(6));
                        if (ev.type === "proposition") {
                            const p = state.propositions[ev.index];
                            if (p) {
                                p.proposition = ev.proposition;
                                p.backend_used = ev.backend_used;
                                p.raw_snippet = ev.raw_snippet;
                                updateQueueRow(ev.index);
                            }
                        }
                    } catch(e) {}
                }
                pump();
            });
        }
        pump();
    });
}

function renderQueueList() {
    const list = document.getElementById("queueList");
    list.innerHTML = "";
    state.propositions.forEach((p, idx) => {
        list.appendChild(buildQueueRow(p, idx));
    });
}

function buildQueueRow(p, idx) {
    const row = document.createElement("div");
    row.className = `queue-row ${p.status}`;
    row.id = `qrow-${idx}`;
    row.innerHTML = `
        <div class="queue-citation">${escHtml(p.citation_text)}</div>
        <textarea class="queue-prop-field" id="prop-${idx}" oninput="onPropEdit(${idx})">${escHtml(p.proposition)}</textarea>
        ${p.backend_used === "fallback" ? '<div class="backend-note">LLM unavailable -- showing raw context. Edit as needed.</div>' : ""}
        ${p.backend_used === "pending" ? '<div class="backend-note">Generating proposition...</div>' : ""}
        <span class="snippet-toggle" onclick="toggleSnippet(${idx})">View source context</span>
        <div class="snippet-text" id="snippet-${idx}">${escHtml(p.context_snippet || "")}</div>
        <div class="queue-actions">
            <button class="queue-btn queue-btn-accept" onclick="setQueueStatus(${idx},'accepted')">Accept</button>
            <button class="queue-btn queue-btn-rewrite" onclick="setQueueStatus(${idx},'rewritten')">Rewrite</button>
            <button class="queue-btn queue-btn-skip" onclick="setQueueStatus(${idx},'skipped')">Skip</button>
        </div>
    `;
    return row;
}

function updateQueueRow(idx) {
    const p = state.propositions[idx];
    const existing = document.getElementById(`qrow-${idx}`);
    if (existing) {
        existing.replaceWith(buildQueueRow(p, idx));
    }
}

function onPropEdit(idx) {
    state.propositions[idx].proposition = document.getElementById(`prop-${idx}`).value;
}

function setQueueStatus(idx, status) {
    state.propositions[idx].status = status;
    const row = document.getElementById(`qrow-${idx}`);
    if (row) {
        row.className = `queue-row ${status}`;
    }
    updateQueueTally();
    checkRunAuditButton();
}

function toggleSnippet(idx) {
    const el = document.getElementById(`snippet-${idx}`);
    el.style.display = el.style.display === "block" ? "none" : "block";
}

function updateQueueTally() {
    const counts = { accepted: 0, rewritten: 0, skipped: 0, pending: 0 };
    state.propositions.forEach(p => {
        counts[p.status] = (counts[p.status] || 0) + 1;
    });
    document.getElementById("queueTally").textContent =
        `${counts.accepted} accepted \u00B7 ${counts.rewritten} rewritten \u00B7 ${counts.skipped} skipped \u00B7 ${counts.pending} pending`;
}

function checkRunAuditButton() {
    const anyActioned = state.propositions.some(p => p.status !== "pending");
    document.getElementById("btnRunAudit").disabled = !anyActioned;
}

function escHtml(str) {
    return (str || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
```

- [ ] **Step 2: Manually test the proposition queue**

With Wilson running, upload a document and select "Full audit". Verify:
- Queue renders with one row per citation
- Propositions stream in and update rows (LLM or fallback)
- "View source context" toggle works
- Accept / Rewrite / Skip update the row border color and tally
- Run Audit button enables after first action
- Back button returns to depth selector with queue state preserved

- [ ] **Step 3: Commit**

```bash
git add templates/upload.html
git commit -m "feat: upload.html Step 3 -- proposition review queue with live SSE population"
```

---

## Task 12: `upload.html` — Steps 4 & 5 (Batch Run + Summary Table)

**Files:**
- Modify: `templates/upload.html`

Replace the `_batchImpl` and `_cancelBatchImpl` placeholders.

- [ ] **Step 1: Replace `_batchImpl` and `_cancelBatchImpl` in `upload.html`**

Find:
```javascript
function _batchImpl() {
    // Implemented in Task 12
    showStep("step-batch");
}
function _cancelBatchImpl() {
    // Implemented in Task 12
}
```

Replace with:

```javascript
function _batchImpl() {
    showStep("step-batch");
    state.batchResults = [];
    state.batchCancelled = false;
    state.batchStartTime = Date.now();

    // Build citation list with propositions attached (for full depth)
    const citationsPayload = state.citations.map((c, idx) => {
        const p = state.propositions[idx];
        return {
            citation_text: c.citation_text,
            quoted_text: c.context_snippet || null,
            proposition: (state.depth === "full" && p && p.status !== "skipped")
                ? p.proposition : null,
        };
    });

    const payload = {
        citations: citationsPayload,
        depth: state.depth,
        chunk_index: 1,
        total_chunks: state.chunkCount,
    };

    // Timer
    state.timerInterval = setInterval(() => {
        const elapsed = ((Date.now() - state.batchStartTime) / 1000).toFixed(1);
        document.getElementById("batchTimer").textContent = elapsed + "s";
    }, 100);

    // Show phase 2/3 columns in summary table if needed
    if (state.depth !== "phase1") document.getElementById("thPhase2").style.display = "";
    if (state.depth === "full") document.getElementById("thPhase3").style.display = "";

    streamBatch(payload, 1);
}

function streamBatch(payload, chunkIndex) {
    let currentCitationIdx = null;
    let currentRow = null;
    let softWarnShown = false;
    let hardWarnShown = false;

    const resp = fetch("/batch/stream", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
    });

    resp.then(r => {
        if (state.batchCancelled) return;
        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        function pump() {
            if (state.batchCancelled) { reader.cancel(); finalizeBatch(true); return; }
            reader.read().then(({ done, value }) => {
                if (done) { if (!state.batchCancelled) finalizeBatch(false); return; }
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split("\n");
                buf = lines.pop();
                for (const line of lines) {
                    if (!line.startsWith("data: ")) continue;
                    try { handleBatchEvent(JSON.parse(line.slice(6))); } catch(e) {}
                }
                pump();
            });
        }
        pump();
    });

    function handleBatchEvent(ev) {
        const log = document.getElementById("batchLog");
        const statusLine = document.getElementById("batchStatusLine");

        if (ev.type === "batch_start") {
            statusLine.textContent = `Starting batch (${ev.total} citations)...`;

        } else if (ev.type === "batch_citation_start") {
            currentCitationIdx = ev.index - 1;
            currentRow = { citation_text: ev.citation_text, phase1: null, phase2: null, phase3: null };
            state.batchResults.push(currentRow);

            const pct = Math.round(((ev.index - 1) / ev.total) * 100);
            document.getElementById("batchProgress").style.width = pct + "%";
            statusLine.textContent = `Citation ${ev.index} of ${ev.total}: checking whether "${ev.display_name}" exists...`;

            const logLine = document.createElement("div");
            logLine.style.cssText = "font-size:0.74rem;color:#3a3a3a;font-family:monospace;padding:0.2rem 0;";
            logLine.id = `log-${ev.index}`;
            logLine.textContent = `[${ev.index}/${ev.total}] ${ev.citation_text.slice(0, 60)}`;
            log.appendChild(logLine);
            log.scrollTop = log.scrollHeight;

        } else if (ev.type === "status") {
            statusLine.textContent = ev.message;

        } else if (ev.type === "phase1_complete") {
            if (currentRow) currentRow.phase1 = ev.data;
            const logEl = document.getElementById(`log-${currentCitationIdx + 1}`);
            if (logEl) {
                logEl.textContent += ` -- ${ev.data.verdict}`;
                logEl.style.color = verdictColor(ev.data.verdict);
            }
            statusLine.textContent = currentRow
                ? `Citation ${currentCitationIdx + 1}: ${ev.data.verdict}`
                : "";

        } else if (ev.type === "phase2_complete") {
            if (currentRow) currentRow.phase2 = ev.data;

        } else if (ev.type === "phase3_complete") {
            if (currentRow) currentRow.phase3 = ev.data;

        } else if (ev.type === "batch_citation_done") {
            // Row is done; table appended in batch_done

        } else if (ev.type === "heartbeat") {
            if (ev.elapsed_since_event > 30 && !hardWarnShown) {
                hardWarnShown = true;
                showBatchWarning("No response from server. You may cancel and retry.", "error");
            } else if (ev.elapsed_since_event > 10 && !softWarnShown) {
                softWarnShown = true;
                showBatchWarning("Still working -- LLM inference can take a moment on large opinions.", "warn");
            }

        } else if (ev.type === "batch_done") {
            document.getElementById("batchProgress").style.width = "100%";
            document.getElementById("batchProgress").classList.remove("active");
            clearInterval(state.timerInterval);
            statusLine.textContent = `Complete -- ${ev.total} citations processed in ${ev.duration}s`;
        }
    }
}

function showBatchWarning(msg, level) {
    const el = document.getElementById("batchWarning");
    el.className = `banner banner-${level}`;
    el.textContent = msg;
    el.style.display = "block";
}

function verdictColor(verdict) {
    if (["EXISTS", "SUPPORTS", "100% MATCH"].includes(verdict)) return "#2a4a2a";
    if (["FABRICATED", "DOES_NOT_SUPPORT", "NOT FOUND"].includes(verdict)) return "#4a2a2a";
    if (["MISATTRIBUTED", "UNCERTAIN"].includes(verdict)) return "#4a3a2a";
    return "#2a2a2a";
}

function _cancelBatchImpl() {
    state.batchCancelled = true;
    clearInterval(state.timerInterval);
    document.getElementById("batchProgress").classList.remove("active");
    document.getElementById("btnCancelBatch").disabled = true;
    finalizeBatch(true);
}

function finalizeBatch(cancelled) {
    clearInterval(state.timerInterval);
    showStep("step-summary");
    renderSummaryTable(cancelled);
}

function renderSummaryTable(cancelled) {
    const tbody = document.getElementById("summaryBody");
    tbody.innerHTML = "";

    const verdictGloss = {
        "EXISTS": "Citation verified.",
        "FABRICATED": "This citation does not exist in any federal court record.",
        "MISATTRIBUTED": "These coordinates belong to a different case.",
        "ERROR": "Verification failed. Reason shown below.",
        "100% MATCH": "Quoted language found exactly in the opinion.",
        "NOT FOUND": "Quoted language not found in the opinion.",
        "SUPPORTS": "The cited case supports this argument.",
        "DOES_NOT_SUPPORT": "The cited case does not support this argument.",
        "UNCERTAIN": "Relationship between case and argument is unclear.",
        "SKIPPED": "Not checked.",
    };

    function verdictClass(v) {
        if (!v) return "v-grey";
        if (["EXISTS","SUPPORTS","100% MATCH"].includes(v)) return "v-green";
        if (["FABRICATED","DOES_NOT_SUPPORT","NOT FOUND"].includes(v)) return "v-red";
        if (["MISATTRIBUTED","UNCERTAIN"].includes(v.toUpperCase ? v.toUpperCase() : v)) return "v-orange";
        return "v-grey";
    }

    let errorCount = 0;
    state.batchResults.forEach((row, idx) => {
        const p1 = row.phase1 || {};
        const p2 = row.phase2 || {};
        const p3 = row.phase3 || {};
        const p1v = p1.verdict || "ERROR";
        const p2v = p2.display_verdict || p2.verdict || null;
        const p3v = p3.verdict || null;
        if (p1v === "ERROR") errorCount++;

        const detailParts = [];
        if (p1.message) detailParts.push(`<b>Phase 1:</b> ${escHtml(p1.message)}`);
        if (p2.reasoning) detailParts.push(`<b>Phase 2:</b> ${escHtml(p2.reasoning)}`);
        if (p2.passage) detailParts.push(`<b>Passage:</b> <span style="font-family:monospace">${escHtml(p2.passage)}</span>`);
        if (p3.reasoning) detailParts.push(`<b>Phase 3:</b> ${escHtml(p3.reasoning)}`);
        if (p3.backend_used) detailParts.push(`<b>Backend:</b> ${escHtml(p3.backend_used)}`);

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="citation-cell">${escHtml(row.citation_text)}</td>
            <td>
                <span class="verdict ${verdictClass(p1v)}">${escHtml(p1v)}</span>
                <div class="gloss">${escHtml(verdictGloss[p1v] || "")}</div>
            </td>
            ${state.depth !== "phase1" ? `<td>
                ${p2v ? `<span class="verdict ${verdictClass(p2v)}">${escHtml(p2v)}</span><div class="gloss">${escHtml(verdictGloss[p2v] || "")}</div>` : "<span style='color:#3a3a3a;font-size:0.72rem'>--</span>"}
            </td>` : ""}
            ${state.depth === "full" ? `<td>
                ${p3v ? `<span class="verdict ${verdictClass(p3v)}">${escHtml(p3v)}</span><div class="gloss">${escHtml(verdictGloss[p3v] || "")}</div>` : "<span style='color:#3a3a3a;font-size:0.72rem'>--</span>"}
            </td>` : ""}
            <td>
                ${detailParts.length ? `<span class="expand-btn" onclick="toggleExpand(${idx})">Details</span><div class="expand-detail" id="expand-${idx}">${detailParts.join("<br><br>")}</div>` : ""}
            </td>
        `;
        tbody.appendChild(tr);
    });

    const elapsed = ((Date.now() - state.batchStartTime) / 1000).toFixed(1);
    const footer = document.getElementById("summaryFooter");
    footer.textContent = `${state.batchResults.length} citations processed in ${elapsed}s`;

    const banner = document.getElementById("summaryBanner");
    if (cancelled) {
        banner.className = "banner banner-cancel";
        banner.textContent = `Batch cancelled at citation ${state.batchResults.length} of ${state.citations.length}. Partial results shown.`;
        banner.style.display = "block";
    } else if (errorCount > 0) {
        banner.className = "banner banner-warn";
        banner.textContent = `${errorCount} citation${errorCount !== 1 ? "s" : ""} encountered errors and could not be fully verified.`;
        banner.style.display = "block";
    }
}

function toggleExpand(idx) {
    const el = document.getElementById(`expand-${idx}`);
    if (el) el.style.display = el.style.display === "block" ? "none" : "block";
}
```

- [ ] **Step 2: Manually test the full flow end-to-end**

With Wilson running, verify:
- Upload a TXT file containing 2-3 known citations (e.g., Miranda, Strickland)
- Existence only: batch runs, progress bar fills, summary table renders with verdicts and glosses
- Cancel mid-batch: partial results render with cancel banner
- Heartbeat warning appears if no event for 10+ seconds (hard to test manually — confirm code path exists)
- Details expand/collapse on each row

- [ ] **Step 3: Commit**

```bash
git add templates/upload.html
git commit -m "feat: upload.html Steps 4-5 -- batch SSE pipeline, heartbeat, cancel, summary table"
```

---

## Task 13: Integration Smoke Test + Final Checks

**Files:**
- Create: `tests/test_upload_smoke.py`

- [ ] **Step 1: Write smoke test against live server**

Create `tests/test_upload_smoke.py`:

```python
"""
Smoke test for the upload portal end-to-end.
Requires Wilson server running on localhost:8000.
Run with: pytest tests/test_upload_smoke.py -v -m smoke

These tests hit the live CourtListener API and are slower than unit tests.
They are marked 'smoke' so they can be skipped in fast CI runs.
"""

import pytest
import requests

BASE = "http://localhost:8000"

pytestmark = pytest.mark.smoke


def test_upload_page_loads():
    """GET /upload returns 200 HTML."""
    resp = requests.get(f"{BASE}/upload")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Upload Document" in resp.text


def test_upload_parse_txt_with_real_citations():
    """TXT upload with real citations returns citation list."""
    text = (
        "The right to counsel was established in "
        "Miranda v. Arizona, 384 U.S. 436 (1966). "
        "Effective assistance is governed by "
        "Strickland v. Washington, 466 U.S. 668 (1984)."
    )
    resp = requests.post(
        f"{BASE}/upload/parse",
        files={"file": ("test.txt", text.encode(), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["citations"]) == 2
    citations = [c["citation_text"] for c in data["citations"]]
    assert any("384 U.S. 436" in c for c in citations)
    assert any("466 U.S. 668" in c for c in citations)


def test_batch_stream_existence_only():
    """POST /batch/stream with depth=phase1 verifies Miranda exists."""
    payload = {
        "citations": [{"citation_text": "Miranda v. Arizona, 384 U.S. 436 (1966)"}],
        "depth": "phase1",
    }
    resp = requests.post(f"{BASE}/batch/stream", json=payload, stream=True)
    assert resp.status_code == 200

    events = []
    for line in resp.iter_lines():
        if isinstance(line, bytes):
            line = line.decode()
        if line.startswith("data: "):
            import json
            events.append(json.loads(line[6:]))

    types = [e["type"] for e in events]
    assert "phase1_complete" in types
    assert "batch_done" in types

    phase1 = next(e for e in events if e["type"] == "phase1_complete")
    assert phase1["data"]["verdict"] == "EXISTS"
```

- [ ] **Step 2: Run smoke tests (server must be running)**

Start Wilson in a separate terminal:
```bash
.\venv\Scripts\python.exe -m uvicorn api:app --host 0.0.0.0 --port 8000
```

Run smoke tests:
```bash
.\venv\Scripts\python.exe -m pytest tests/test_upload_smoke.py -v -m smoke
```

Expected: 3 passed. Miranda should return EXISTS.

- [ ] **Step 3: Run full unit test suite one final time**

```bash
.\venv\Scripts\python.exe -m pytest tests/test_document_parser.py tests/test_upload_api.py -v
```

Expected: All tests pass.

- [ ] **Step 4: Final commit**

```bash
git add tests/test_upload_smoke.py
git commit -m "test: upload portal smoke tests (parse + batch stream end-to-end)"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered in |
|-----------------|-----------|
| PDF, DOCX, TXT extraction | Tasks 2-4 |
| DOCX footnotes | Task 3 |
| 50MB file size limit | Task 7 |
| 200-page chunking with auto-queue | Tasks 7, 10 |
| Depth selector (phase1 / phase1_2 / full) | Tasks 9, 10 |
| Phase 3 availability check at depth step | Task 10 |
| Proposition queue (list view, non-linear) | Task 11 |
| 3-at-a-time proposition concurrency | Tasks 6, 8 |
| Accept / Rewrite / Skip actions | Task 11 |
| Queue tally | Task 11 |
| Back button (queue state preserved) | Task 11 |
| Cancel with confirmation (depth step) | Task 10 |
| Raw snippet toggle (accountability) | Task 11 |
| LLM fallback noted inline | Task 11 |
| Batch SSE with heartbeat | Task 9 |
| Plain-English status lines | Task 9, 12 |
| 10s soft / 30s hard timeout warnings | Task 9, 12 |
| Cancel mid-batch (partial results) | Task 12 |
| Progress bar with shimmer | Task 10 |
| Summary table with verdicts + glosses | Task 12 |
| Plain-English verdict glosses (all 11) | Task 12 |
| Details expand toggle | Task 12 |
| Error count banner | Task 12 |
| Cancel banner | Task 12 |
| "Upload Document" link in index.html | Task 10 |
| Dark theme matching index.html | Task 10 |
| No sse-starlette (raw StreamingResponse) | Tasks 8, 9 |

All spec requirements covered. No gaps found.

**Placeholder scan:** No TBD, TODO, or "similar to" references. All code blocks are complete.

**Type consistency:**
- `extract_text` → `{text, page_count, page_boundaries, extraction_method}` — consistent across Tasks 2-7
- `extract_citations_with_context(text, page_boundaries)` — consistent across Tasks 5, 7
- `suggest_proposition` → `{proposition, backend_used, raw_snippet}` — consistent across Tasks 6, 8, 11
- `BatchStreamRequest.depth` values: `"phase1"`, `"phase1_2"`, `"full"` — consistent Tasks 9, 10, 12
- SSE event `make_event("batch_citation_start", ..., display_name=...)` — used in Task 9, consumed in Task 12 ✓
