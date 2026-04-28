"""Tests for applycling/import_existing.py — Index Existing Output Folders."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from applycling.import_existing import (
    _parse_job_description_md,
    _scan_folder,
    index_output_dir,
    REQUIRED_ONE_OF,
)
from applycling.tracker import get_store, TrackerError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_output_root():
    """Create a temp directory mimicking an output/ folder structure."""
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


def _make_package(
    root: Path,
    dirname: str,
    *,
    job_json: dict | None = None,
    job_description_md: str | None = None,
    source_url_txt: str | None = None,
    artifacts: list[str] | None = None,
) -> Path:
    """Create a package subdirectory with given files."""
    pkg = root / dirname
    pkg.mkdir(parents=True, exist_ok=True)

    if job_json is not None:
        (pkg / "job.json").write_text(json.dumps(job_json), encoding="utf-8")

    if job_description_md is not None:
        (pkg / "job_description.md").write_text(
            job_description_md, encoding="utf-8"
        )

    if source_url_txt is not None:
        (pkg / "source_url.txt").write_text(source_url_txt, encoding="utf-8")

    if artifacts is not None:
        for art in artifacts:
            # Don't overwrite files already written by explicit params.
            if art == "job_description.md" and job_description_md is not None:
                continue
            (pkg / art).write_text(f"content of {art}", encoding="utf-8")

    return pkg


# ---------------------------------------------------------------------------
# Unit: _parse_job_description_md
# ---------------------------------------------------------------------------

class TestParseJobDescriptionMd:
    def test_standard_format(self, temp_output_root):
        md = temp_output_root / "test.md"
        md.write_text(
            "# Job Description — Senior Engineer @ Acme Corp\n\nSome body text.",
            encoding="utf-8",
        )
        result = _parse_job_description_md(md)
        assert result["title"] == "Senior Engineer"
        assert result["company"] == "Acme Corp"

    def test_dash_separator(self, temp_output_root):
        md = temp_output_root / "test.md"
        md.write_text(
            "# Job Description - Product Manager at BigCo\n",
            encoding="utf-8",
        )
        result = _parse_job_description_md(md)
        assert result["title"] == "Product Manager"
        assert result["company"] == "BigCo"

    def test_no_company(self, temp_output_root):
        md = temp_output_root / "test.md"
        md.write_text(
            "# Job Description — Freelance Gig\n",
            encoding="utf-8",
        )
        result = _parse_job_description_md(md)
        assert result["title"] == "Freelance Gig"
        assert "company" not in result

    def test_missing_file(self, temp_output_root):
        result = _parse_job_description_md(temp_output_root / "nonexistent.md")
        assert result == {}


# ---------------------------------------------------------------------------
# Unit: _scan_folder
# ---------------------------------------------------------------------------

class TestScanFolder:
    def test_valid_package_with_job_json(self, temp_output_root):
        pkg = _make_package(
            temp_output_root,
            "job_001-acme-senior-engineer-2026-01-01",
            job_json={
                "id": "job_001",
                "title": "Senior Engineer",
                "company": "Acme Corp",
                "source_url": "https://example.com/job/1",
            },
            artifacts=["resume.pdf", "cover_letter.pdf", "job_description.md"],
        )
        info = _scan_folder(pkg)
        assert info is not None
        assert info["title"] == "Senior Engineer"
        assert info["company"] == "Acme Corp"
        assert info["source_url"] == "https://example.com/job/1"
        assert "resume.pdf" in info["artifacts"]
        assert "cover_letter.pdf" in info["artifacts"]

    def test_folder_name_fallback(self, temp_output_root):
        """When no job.json or job_description.md, infer from folder name."""
        pkg = _make_package(
            temp_output_root,
            "job_002-microsoft-product-manager-2026-04-01",
            artifacts=["resume.pdf"],
        )
        info = _scan_folder(pkg)
        assert info is not None
        assert "microsoft" in info["company"].lower() or "Microsoft" in info["company"]
        assert "product" in info["title"].lower() or "Product" in info["title"]

    def test_source_url_txt(self, temp_output_root):
        pkg = _make_package(
            temp_output_root,
            "test-pkg",
            job_json={"title": "Dev", "company": "Co"},
            source_url_txt="https://jobs.example.com/42",
            artifacts=["resume.md"],
        )
        info = _scan_folder(pkg)
        assert info is not None
        assert info["source_url"] == "https://jobs.example.com/42"

    def test_placeholder_url_when_no_source(self, temp_output_root):
        pkg = _make_package(
            temp_output_root,
            "test-pkg",
            job_json={"title": "Dev", "company": "Co"},
            artifacts=["resume.md"],
        )
        info = _scan_folder(pkg)
        assert info is not None
        assert info["source_url"].startswith("file://imported/")

    def test_malformed_folder_no_artifacts(self, temp_output_root):
        pkg = temp_output_root / "empty"
        pkg.mkdir()
        (pkg / "notes.txt").write_text("just notes")
        info = _scan_folder(pkg)
        assert info is None

    def test_dotfolder_skipped(self, temp_output_root):
        pkg = _make_package(
            temp_output_root,
            ".hidden_pkg",
            artifacts=["resume.pdf"],
        )
        info = _scan_folder(pkg)
        assert info is None

    def test_parse_from_job_description_md(self, temp_output_root):
        pkg = _make_package(
            temp_output_root,
            "some-folder",
            job_description_md="# Job Description — Staff Engineer @ Google\n\nDesc...",
            artifacts=["resume.pdf", "job_description.md"],
        )
        info = _scan_folder(pkg)
        assert info is not None
        assert info["title"] == "Staff Engineer"
        assert info["company"] == "Google"

    def test_job_json_overrides_md(self, temp_output_root):
        """job.json should take priority over job_description.md."""
        pkg = _make_package(
            temp_output_root,
            "test-pkg",
            job_json={"title": "From JSON", "company": "JsonCo", "source_url": ""},
            job_description_md="# Job Description — From MD @ MdCo",
            artifacts=["resume.pdf", "job_description.md"],
        )
        info = _scan_folder(pkg)
        assert info is not None
        assert info["title"] == "From JSON"
        assert info["company"] == "JsonCo"


# ---------------------------------------------------------------------------
# Integration: index_output_dir
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_import_store(monkeypatch, tmp_path):
    """Replace get_store() with an isolated SQLiteStore for import tests."""
    from applycling.tracker.sqlite_store import SQLiteStore
    import applycling.import_existing as mod

    db = tmp_path / "test_tracker.db"
    store = SQLiteStore(db_path=db)

    def _mock_get_store():
        return store

    monkeypatch.setattr(mod, "get_store", _mock_get_store)
    return store


class TestIndexOutputDir:
    def test_imports_valid_packages(self, isolated_import_store, temp_output_root):
        _make_package(
            temp_output_root,
            "job_001-acme-engineer-2026-01-01",
            job_json={
                "id": "job_001",
                "title": "Software Engineer",
                "company": "Acme Corp",
                "source_url": "https://acme.example.com/jobs/1",
            },
            artifacts=["resume.pdf", "cover_letter.pdf", "fit_summary.md"],
        )
        _make_package(
            temp_output_root,
            "job_002-globaldev-designer-2026-02-01",
            job_json={
                "id": "job_002",
                "title": "UX Designer",
                "company": "GlobalDev",
                "source_url": "https://globaldev.example.com/jobs/2",
            },
            artifacts=["resume.pdf"],
        )

        result = index_output_dir(str(temp_output_root))
        assert result["imported"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_idempotency(self, isolated_import_store, temp_output_root):
        """Running index twice must not create duplicate jobs."""
        _make_package(
            temp_output_root,
            "job_001-acme-engineer-2026-01-01",
            job_json={
                "id": "job_001",
                "title": "DevOps Engineer",
                "company": "Acme Corp",
                "source_url": "https://acme.example.com/jobs/3",
            },
            artifacts=["resume.pdf"],
        )

        first = index_output_dir(str(temp_output_root))
        assert first["imported"] == 1
        assert first["skipped"] == 0

        second = index_output_dir(str(temp_output_root))
        assert second["imported"] == 0
        assert second["skipped"] == 1
        assert second["errors"] == []

    def test_malformed_folder_skipped(self, isolated_import_store, temp_output_root):
        """Folders without required artifacts should produce warnings, not crashes."""
        bad = temp_output_root / "not-a-package"
        bad.mkdir()
        (bad / "readme.txt").write_text("hello")

        _make_package(
            temp_output_root,
            "good-one",
            job_json={"title": "Good", "company": "Corp"},
            artifacts=["resume.pdf"],
        )

        result = index_output_dir(str(temp_output_root))
        assert result["imported"] == 1
        assert result["errors"]  # malformed warning
        assert any("not-a-package" in e for e in result["errors"])

    def test_empty_output_dir(self, temp_output_root):
        result = index_output_dir(str(temp_output_root))
        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == []

    def test_missing_output_dir(self):
        result = index_output_dir("/tmp/nonexistent_applycling_test_dir_xyz")
        assert result["imported"] == 0
        assert result["skipped"] == 0
        assert len(result["errors"]) == 1

    def test_multiple_runs_same_title_different_company(self, isolated_import_store, temp_output_root):
        """Same title + different company = new job (not a duplicate)."""
        _make_package(
            temp_output_root,
            "job_a",
            job_json={"title": "Engineer", "company": "Acme"},
            artifacts=["resume.pdf"],
        )
        _make_package(
            temp_output_root,
            "job_b",
            job_json={"title": "Engineer", "company": "BetaCorp"},
            artifacts=["resume.pdf"],
        )

        result = index_output_dir(str(temp_output_root))
        assert result["imported"] == 2
        assert result["skipped"] == 0
