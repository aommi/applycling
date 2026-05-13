"""Resume text extraction helpers for uploaded profile documents."""

from __future__ import annotations

from pathlib import Path

from applycling import pdf_import


class ResumeImportError(ValueError):
    """Raised when an uploaded resume cannot be converted to text."""


_TEXT_EXTS = {".txt", ".md", ".markdown"}


def extract_resume_text(path: Path) -> str:
    """Extract plain text from a PDF, DOCX, Markdown, or text resume file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            return pdf_import.extract_text(path)
        except pdf_import.PDFImportError as exc:
            raise ResumeImportError(str(exc)) from exc

    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise ResumeImportError(
                "python-docx is not installed; cannot read DOCX resumes."
            ) from exc
        try:
            doc = Document(str(path))
        except Exception as exc:
            raise ResumeImportError(f"Could not read DOCX resume: {exc}") from exc
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs).strip()
        if not text:
            raise ResumeImportError("No text could be extracted from this DOCX resume.")
        return text

    if suffix in _TEXT_EXTS:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError as exc:
            raise ResumeImportError("Text resume must be UTF-8 encoded.") from exc
        if not text:
            raise ResumeImportError("Resume file is empty.")
        return text

    raise ResumeImportError(
        "Unsupported resume format. Upload a PDF, DOCX, Markdown, or text file."
    )
