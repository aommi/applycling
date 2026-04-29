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


# ── Test: artifact kind vocabulary consistency ─────────────────────────

def test_all_inferred_kinds_in_artifact_kinds():
    """Every kind produced by _INFER_KIND must be in _ARTIFACT_KINDS.

    If this fails, a scan-fallback will return kinds that attach_artifact
    (and the UI) will reject.
    """
    for filename, kind in jobs_service._INFER_KIND.items():
        assert kind in jobs_service._ARTIFACT_KINDS, (
            f"_INFER_KIND maps '{filename}' → '{kind}', "
            f"but '{kind}' is not in _ARTIFACT_KINDS"
        )


def test_all_artifact_files_kinds_in_artifact_kinds():
    """Every kind in _ARTIFACT_FILES must be in _ARTIFACT_KINDS."""
    for kind in jobs_service._ARTIFACT_FILES:
        assert kind in jobs_service._ARTIFACT_KINDS, (
            f"_ARTIFACT_FILES key '{kind}' is not in _ARTIFACT_KINDS"
        )


def test_all_artifact_kinds_have_file_mapping():
    """Every kind in _ARTIFACT_KINDS must have an entry in _ARTIFACT_FILES."""
    for kind in jobs_service._ARTIFACT_KINDS:
        assert kind in jobs_service._ARTIFACT_FILES, (
            f"_ARTIFACT_KINDS contains '{kind}' but _ARTIFACT_FILES has no mapping"
        )


def test_attach_artifact_accepts_all_inferred_kinds(inbox_job, isolated_store, tmp_path):
    """attach_artifact() must accept every kind that _INFER_KIND can produce."""
    def _fake_path(job_id: str) -> Path:
        p = tmp_path / "artifacts" / f"{job_id}_artifacts.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    with patch.object(jobs_service, "_artifacts_path_for_job", side_effect=_fake_path):
        for kind in set(jobs_service._INFER_KIND.values()):
            art = jobs_service.attach_artifact(
                inbox_job["id"], kind=kind, path=f"/fake/{kind}"
            )
            assert art["kind"] == kind

        # All should be recorded
        arts = jobs_service.list_artifacts(inbox_job["id"])
        expected = set(jobs_service._INFER_KIND.values())
        actual = {a["kind"] for a in arts}
        assert actual == expected


def test_scan_fallback_produces_valid_kinds(inbox_job, isolated_store, tmp_path):
    """Scan-fallback should only produce kinds that are in _ARTIFACT_KINDS."""
    import json

    store = isolated_store
    job_id = inbox_job["id"]

    # Simulate a package folder with all known artifact files
    pkg = tmp_path / "packages" / "scan-test"
    pkg.mkdir(parents=True)

    # Write placeholder files for every filename in _INFER_KIND
    for filename in jobs_service._INFER_KIND:
        (pkg / filename).write_text("placeholder", encoding="utf-8")

    # Also write job.json (manifest)
    (pkg / "job.json").write_text(json.dumps({"id": job_id}), encoding="utf-8")

    # Point the job's package_folder at our temp dir
    store.update_job(job_id, package_folder=str(pkg))

    # list_artifacts should fallback to scan
    arts = jobs_service.list_artifacts(job_id)

    # Every returned kind must be valid
    for art in arts:
        kind = art["kind"]
        assert kind in jobs_service._ARTIFACT_KINDS, (
            f"Scan-fallback returned kind '{kind}' which is not in _ARTIFACT_KINDS"
        )

    # All expected kinds should be present (minus any that didn't match the suffix filter)
    returned_kinds = {a["kind"] for a in arts}
    for kind in set(jobs_service._INFER_KIND.values()):
        assert kind in returned_kinds, (
            f"Scan-fallback did not return expected kind '{kind}'"
        )


# ── Test: run_pipeline with persist_job=False ──────────────────────────

def test_run_pipeline_no_duplicate_job(isolated_store, tmp_path):
    """run_pipeline with persist_job=False leaves exactly one tracker job
    and copies title/company/fit_summary from the package folder."""
    import json

    # Create a job first
    job = jobs_service.create_job_from_url("https://example.com/jobs/test-pipeline")
    job_id = job["id"]

    # Build a fake package folder with job.json containing metadata
    pkg = tmp_path / "packages" / "Acme Corp - Software Engineer"
    pkg.mkdir(parents=True)
    job_json = {
        "id": job_id,
        "title": "Software Engineer",
        "company": "Acme Corp",
        "status": "reviewing",
        "source_url": "https://example.com/jobs/test-pipeline",
        "fit_summary": "Strong match — 8/10",
        "files": {},
    }
    (pkg / "job.json").write_text(json.dumps(job_json), encoding="utf-8")

    # Mock run_add_notify to return our fake package folder
    with patch("applycling.pipeline.run_add_notify", return_value=pkg):
        # Mock _artifacts_path_for_job to keep artifacts in tmp_path
        def _fake_artifacts_path(jid: str) -> Path:
            p = tmp_path / "artifacts" / f"{jid}_artifacts.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p

        with patch.object(
            jobs_service, "_artifacts_path_for_job", side_effect=_fake_artifacts_path
        ):
            result = jobs_service.run_pipeline(job_id)

    # No error
    assert "error" not in result, f"Unexpected error: {result.get('error')}"

    # Status is reviewing
    assert result["status"] == "reviewing"

    # Metadata copied from job.json
    assert result["title"] == "Software Engineer"
    assert result["company"] == "Acme Corp"
    assert result["fit_summary"] == "Strong match — 8/10"

    # Package folder recorded
    assert result["package_folder"] == str(pkg)

    # Exactly one job in the tracker (no duplicate)
    all_jobs = jobs_service.list_jobs()
    assert len(all_jobs) == 1
    assert all_jobs[0]["id"] == job_id

    # The tracker row has the updated data
    tracker_job = isolated_store.load_job(job_id)
    assert tracker_job.status == "reviewing"
    assert tracker_job.title == "Software Engineer"
    assert tracker_job.company == "Acme Corp"
    assert tracker_job.fit_summary == "Strong match — 8/10"
    assert tracker_job.package_folder == str(pkg)


def test_run_pipeline_no_source_url(isolated_store):
    """run_pipeline on a job without source_url returns an error."""
    store = isolated_store
    # Create a job and wipe its source_url
    job = jobs_service.create_job_from_url("https://example.com/jobs/temp")
    store.update_job(job["id"], source_url=None)

    result = jobs_service.run_pipeline(job["id"])
    assert "error" in result
    assert "source_url" in result["error"].lower()


def test_run_pipeline_package_folder_on_job_id(isolated_store, tmp_path):
    """When persist_job=False with job_id, the package folder name
    incorporates the real job id (not empty string)."""
    import json

    job = jobs_service.create_job_from_url("https://example.com/jobs/test-id")
    job_id = job["id"]

    # Mock run_add_notify — the real one would pass job_id through to
    # PipelineContext, which run_add uses for the Job(id=...). We verify
    # our mock was called with the right job_id.
    def _fake_run_add_notify(url, notifier, *, persist_job=False, job_id="", **kw):
        # Verify job_id was passed through
        assert job_id == job["id"], (
            f"Expected job_id={job['id']}, got job_id={job_id}"
        )
        pkg = tmp_path / "packages" / "TestCo - Tester"
        pkg.mkdir(parents=True)
        job_json = {
            "id": job_id,
            "title": "Tester",
            "company": "TestCo",
            "fit_summary": "OK",
            "files": {},
        }
        (pkg / "job.json").write_text(json.dumps(job_json), encoding="utf-8")
        return pkg

    with patch("applycling.pipeline.run_add_notify", side_effect=_fake_run_add_notify):
        def _fake_artifacts_path(jid: str) -> Path:
            p = tmp_path / "artifacts" / f"{jid}_artifacts.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p

        with patch.object(
            jobs_service, "_artifacts_path_for_job", side_effect=_fake_artifacts_path
        ):
            result = jobs_service.run_pipeline(job_id)

    assert "error" not in result
    assert result["title"] == "Tester"


def test_run_pipeline_guards_starting_status(isolated_store):
    """run_pipeline rejects jobs not in new/reviewing/failed."""
    store = isolated_store
    job = jobs_service.create_job_from_url("https://example.com/jobs/guard-test")
    job_id = job["id"]

    # Move job to applied (not allowed for regenerate)
    store.update_job(job_id, status="applied")

    result = jobs_service.run_pipeline(job_id)
    assert "error" in result
    assert "applied" in result["error"]
    assert "pipeline can only run" in result["error"]

    # Status should NOT have changed to generating
    tracker_job = store.load_job(job_id)
    assert tracker_job.status == "applied"


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
