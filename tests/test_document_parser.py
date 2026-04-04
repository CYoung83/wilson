"""
Tests for document_parser.py

Covers text extraction (TXT, DOCX, PDF), citation extraction with context,
and proposition suggestion (mocked Ollama).
"""

import pytest
from document_parser import extract_text, extract_citations_with_context


# ---------------------------------------------------------------------------
# TXT extraction
# --------------------------------------------------------------------------


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

# ---------------------------------------------------------------------------
# Task 6: Proposition Suggestion
# ---------------------------------------------------------------------------

from unittest.mock import patch, MagicMock


def test_suggest_proposition_returns_required_keys():
    """suggest_proposition always returns proposition, backend_used, raw_snippet."""
    from document_parser import suggest_proposition
    with patch("document_parser.OLLAMA_HOST", "http://localhost:99999"):
        result = suggest_proposition("384 U.S. 436", "some context")
    assert "proposition" in result
    assert "backend_used" in result
    assert "raw_snippet" in result


def test_suggest_proposition_fallback():
    """When Ollama is unavailable, returns raw_snippet as proposition."""
    from document_parser import suggest_proposition
    with patch("document_parser.OLLAMA_HOST", "http://localhost:99999"):
        result = suggest_proposition(
            "Miranda v. Arizona, 384 U.S. 436 (1966)",
            "The court held suspects must be informed of their rights."
        )
    assert result["backend_used"] == "fallback"
    assert result["raw_snippet"] == "The court held suspects must be informed of their rights."
    assert result["proposition"] == "The court held suspects must be informed of their rights."


def test_suggest_proposition_fallback_on_bad_json():
    """When Ollama returns non-JSON, falls back gracefully."""
    from document_parser import suggest_proposition
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": "not json at all"}
    with patch("document_parser.http_requests.post", return_value=mock_resp):
        result = suggest_proposition("384 U.S. 436", "some context")
    assert result["backend_used"] == "fallback"
    assert result["raw_snippet"] == "some context"


def test_suggest_propositions_batch_returns_all():
    """suggest_propositions_batch returns one result per citation."""
    import asyncio
    from document_parser import suggest_propositions_batch
    citations = [
        {"citation_text": "384 U.S. 436", "context_snippet": "context one"},
        {"citation_text": "466 U.S. 668", "context_snippet": "context two"},
    ]
    with patch("document_parser.OLLAMA_HOST", "http://localhost:99999"):
        results = asyncio.run(suggest_propositions_batch(citations))
    assert len(results) == 2
    assert all("proposition" in r for r in results)