"""Tests for uploaded resume extraction helpers."""

from __future__ import annotations

from applycling.resume_import import ResumeImportError, extract_resume_text


def test_extract_resume_text_reads_markdown(tmp_path):
    path = tmp_path / "resume.md"
    path.write_text("# Jane Doe\n\nExperience: Engineer", encoding="utf-8")

    assert "Jane Doe" in extract_resume_text(path)


def test_extract_resume_text_rejects_unsupported_format(tmp_path):
    path = tmp_path / "resume.rtf"
    path.write_text("Jane", encoding="utf-8")

    try:
        extract_resume_text(path)
    except ResumeImportError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("expected ResumeImportError")
