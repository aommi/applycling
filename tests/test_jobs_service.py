"""
Tests for applycling.jobs_service.

All tests use an isolated in-memory SQLite store so they never touch the
production tracker.db or require Postgres.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from applycling.tracker import TrackerError
from applycling.tracker.sqlite_store import SQLiteStore
from applycling import jobs_service


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def isolated_store(monkeypatch, tmp_path: Path):
    """Replace get_store() with a SQLiteStore backed by a temp file."""
    db = tmp_path / "test_tracker.db"
    store = SQLiteStore(db_path=db)

    def _mock_get_store():
        return store

    monkeypatch.setattr(jobs_service, "get_store", _mock_get_store)
    return store


@pytest.fixture
def inbox_job(isolated_store):
    """Create a job via the service and return its dict."""
    job = jobs_service.create_job_from_url("https://example.com/jobs/123")
    return job


# ── Test: create_job_from_url ─────────────────────────────────────────

def test_create_job_from_url_creates_inbox(isolated_store):
    job = jobs_service.create_job_from_url("https://example.com/jobs/456")
    assert "id" in job
    assert job["status"] == "new"
    assert job["source_url"] == "https://example.com/jobs/456"
    # Title / company are empty until the pipeline runs.
    assert job["title"] == ""
    assert job["company"] == ""


def test_create_job_from_url_persists(isolated_store):
    j1 = jobs_service.create_job_from_url("https://a.com")
    j2 = jobs_service.create_job_from_url("https://b.com")
    assert j1["id"] != j2["id"]
    assert len(jobs_service.list_jobs()) == 2


# ── Test: list_jobs ───────────────────────────────────────────────────

def test_list_jobs_no_filter(inbox_job, isolated_store):
    jobs = jobs_service.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == inbox_job["id"]


def test_list_jobs_filter_matching(inbox_job, isolated_store):
    jobs = jobs_service.list_jobs(status="new")
    assert len(jobs) == 1
    assert jobs[0]["status"] == "new"


def test_list_jobs_filter_non_matching(inbox_job, isolated_store):
    jobs = jobs_service.list_jobs(status="reviewing")
    assert len(jobs) == 0


def test_list_jobs_multiple_statuses(isolated_store):
    jobs_service.create_job_from_url("https://a.com")
    jobs_service.create_job_from_url("https://b.com")

    # Set second job to a different status manually (bypass service validation)
    all_jobs = jobs_service.list_jobs()
    isolated_store.update_job(all_jobs[1]["id"], status="archived")

    assert len(jobs_service.list_jobs(status="new")) == 1
    assert len(jobs_service.list_jobs(status="archived")) == 1
    assert len(jobs_service.list_jobs()) == 2


# ── Test: get_job ─────────────────────────────────────────────────────

def test_get_job_returns_correct(inbox_job, isolated_store):
    job = jobs_service.get_job(inbox_job["id"])
    assert job["id"] == inbox_job["id"]
    assert job["status"] == "new"
    assert job["source_url"] == inbox_job["source_url"]


def test_get_job_missing_raises(isolated_store):
    with pytest.raises(TrackerError, match="No job found"):
        jobs_service.get_job("nonexistent")


# ── Test: set_job_status ──────────────────────────────────────────────

def test_set_job_status_valid_transition(inbox_job, isolated_store):
    updated = jobs_service.set_job_status(inbox_job["id"], "generating")
    assert updated["status"] == "generating"


def test_set_job_status_invalid_status_value(inbox_job, isolated_store):
    with pytest.raises(ValueError, match="Unknown status"):
        jobs_service.set_job_status(inbox_job["id"], "bogus")


def test_set_job_status_disallowed_transition(inbox_job, isolated_store):
    # new -> applied is not allowed (must go through generating/reviewing/reviewed)
    with pytest.raises(ValueError, match="Cannot transition"):
        jobs_service.set_job_status(inbox_job["id"], "applied")


def test_set_job_status_allowed_chain(isolated_store):
    j = jobs_service.create_job_from_url("https://example.com/x")

    j = jobs_service.set_job_status(j["id"], "generating")
    assert j["status"] == "generating"

    j = jobs_service.set_job_status(j["id"], "reviewing")
    assert j["status"] == "reviewing"

    j = jobs_service.set_job_status(j["id"], "reviewed")
    assert j["status"] == "reviewed"

    j = jobs_service.set_job_status(j["id"], "applied")
    assert j["status"] == "applied"


def test_set_job_status_failed_to_inbox(isolated_store):
    j = jobs_service.create_job_from_url("https://example.com/x")
    isolated_store.update_job(j["id"], status="failed")  # bypass validation

    j = jobs_service.set_job_status(j["id"], "new")
    assert j["status"] == "new"


def test_set_job_status_with_reason(inbox_job, isolated_store, tmp_path):
    # Override artifacts path to use tmp_path so we can inspect it
    def _fake_path(job_id: str) -> Path:
        p = tmp_path / "artifacts" / f"{job_id}_artifacts.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    with patch.object(jobs_service, "_artifacts_path_for_job", side_effect=_fake_path):
        updated = jobs_service.set_job_status(
            inbox_job["id"], "generating", reason="Pipeline started"
        )
        assert updated["status"] == "generating"

        # Verify the reason was recorded
        data = jobs_service._read_artifacts_json(inbox_job["id"])
        reasons = data.get("status_reasons", [])
        assert len(reasons) == 1
        assert reasons[0]["status"] == "generating"
        assert reasons[0]["reason"] == "Pipeline started"


# ── Test: attach_artifact / list_artifacts ─────────────────────────────

def test_attach_and_list_artifacts(inbox_job, isolated_store, tmp_path):
    def _fake_path(job_id: str) -> Path:
        p = tmp_path / "artifacts" / f"{job_id}_artifacts.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    with patch.object(jobs_service, "_artifacts_path_for_job", side_effect=_fake_path):
        # Initially empty
        assert jobs_service.list_artifacts(inbox_job["id"]) == []

        # Attach a resume PDF
        art = jobs_service.attach_artifact(
            inbox_job["id"],
            kind="resume_pdf",
            path="/fake/path/to/resume.pdf",
        )
        assert art["kind"] == "resume_pdf"
        assert art["path"] == "/fake/path/to/resume.pdf"

        # Attach a cover letter markdown
        jobs_service.attach_artifact(
            inbox_job["id"],
            kind="cover_letter_md",
            path="/fake/path/to/cover_letter.md",
        )

        arts = jobs_service.list_artifacts(inbox_job["id"])
        assert len(arts) == 2
        kinds = {a["kind"] for a in arts}
        assert kinds == {"resume_pdf", "cover_letter_md"}


def test_attach_artifact_invalid_kind(inbox_job, isolated_store):
    with pytest.raises(ValueError, match="Invalid artifact kind"):
        jobs_service.attach_artifact(
            inbox_job["id"], kind="not_a_real_kind", path="/x"
        )


def test_artifacts_persist_across_reads(inbox_job, isolated_store, tmp_path):
    def _fake_path(job_id: str) -> Path:
        p = tmp_path / "artifacts" / f"{job_id}_artifacts.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    with patch.object(jobs_service, "_artifacts_path_for_job", side_effect=_fake_path):
        jobs_service.attach_artifact(inbox_job["id"], "fit_summary", "/fit.md")

        # Read again — should still be there
        arts = jobs_service.list_artifacts(inbox_job["id"])
        assert len(arts) == 1
        assert arts[0]["kind"] == "fit_summary"


# ── Test: service works with SQLite default ───────────────────────────

def test_service_functions_chain_with_sqlite(isolated_store, tmp_path):
    """End-to-end walk through the service with SQLite only."""
    # Isolate artifacts path to tmp_path to avoid cross-test pollution
    def _fake_path(job_id: str) -> Path:
        p = tmp_path / "artifacts" / f"{job_id}_artifacts.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    with patch.object(jobs_service, "_artifacts_path_for_job", side_effect=_fake_path):
        # Create
        j = jobs_service.create_job_from_url("https://example.com/jobs/chain-test")
        job_id = j["id"]
        assert j["status"] == "new"

        # Get
        j2 = jobs_service.get_job(job_id)
        assert j2["id"] == job_id

        # List — should appear
        jobs = jobs_service.list_jobs()
        assert any(x["id"] == job_id for x in jobs)

        # Status transitions
        jobs_service.set_job_status(job_id, "generating")
        jobs_service.set_job_status(job_id, "reviewing")
        jobs_service.set_job_status(job_id, "reviewed")

        j3 = jobs_service.get_job(job_id)
        assert j3["status"] == "reviewed"

        # Artifacts
        jobs_service.attach_artifact(job_id, "job_description", "/some/path/jd.md")
        arts = jobs_service.list_artifacts(job_id)
        assert len(arts) == 1

        # List by status
        assert len(jobs_service.list_jobs(status="reviewed")) == 1
        assert len(jobs_service.list_jobs(status="new")) == 0
