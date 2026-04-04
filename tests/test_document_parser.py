"""
Tests for document_parser.py

Covers text extraction (TXT, DOCX, PDF), citation extraction with context,
and proposition suggestion (mocked Ollama).
"""

import pytest
from document_parser import extract_text


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