"""PDF resume importer.

Reads a user-supplied PDF resume, extracts the raw text with pypdf, and uses
the local Ollama model to clean it into canonical Markdown. The caller is
expected to show the result to the user for confirmation before storing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from . import llm
from .prompts import PDF_RESUME_CLEANUP_PROMPT


class PDFImportError(Exception):
    """Raised when a PDF cannot be read or extracted."""


def extract_text(pdf_path: Path) -> str:
    """Extract raw text from a PDF using pypdf.

    Returns the concatenated text of all pages, joined by newlines.
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise PDFImportError(
            "pypdf is not installed. Run `pip install pypdf` inside your venv."
        ) from e

    if not pdf_path.exists():
        raise PDFImportError(f"PDF not found: {pdf_path}")

    try:
        reader = PdfReader(str(pdf_path))
    except Exception as e:
        raise PDFImportError(f"Could not read PDF: {e}") from e

    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:
            raise PDFImportError(f"Failed extracting page {i + 1}: {e}") from e
    text = "\n".join(parts).strip()
    if not text:
        raise PDFImportError(
            "No text could be extracted from this PDF. It may be image-only "
            "(scanned). Try a text-based PDF, or paste your resume manually."
        )
    return text


def clean_to_markdown(extracted_text: str, model: str) -> Iterator[str]:
    """Stream Markdown chunks from the LLM that clean the extracted text.

    Yields token strings as they arrive. Caller joins them.
    """
    prompt = PDF_RESUME_CLEANUP_PROMPT.format(extracted_text=extracted_text)
    yield from llm._stream_chat(model, prompt)


def import_pdf(pdf_path: Path, model: str) -> str:
    """Convenience: extract + clean in one call. Returns the cleaned Markdown."""
    raw = extract_text(pdf_path)
    parts: list[str] = []
    for chunk in clean_to_markdown(raw, model):
        parts.append(chunk)
    return "".join(parts).strip()
