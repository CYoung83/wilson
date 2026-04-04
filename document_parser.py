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
                    pass  # Footnotes optional -- don't fail the whole extraction

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