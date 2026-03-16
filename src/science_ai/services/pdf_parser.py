"""PDF text extraction using PyMuPDF."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract full text from a PDF file using PyMuPDF.

    Returns the concatenated text of all pages.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n\n".join(pages)


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract full text from PDF bytes."""
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages: list[str] = []
    for page in doc:
        pages.append(page.get_text())
    doc.close()
    return "\n\n".join(pages)


async def download_and_extract(url: str) -> str:
    """Download a PDF from URL and extract text."""
    import httpx

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()

    return extract_text_from_pdf_bytes(resp.content)
