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