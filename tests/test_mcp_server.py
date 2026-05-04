from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def _mock_loop(monkeypatch):
    """Mock get_running_loop so _MCPNotifier.__init__ works in sync tests.

    _MCPNotifier captures the event loop for run_coroutine_threadsafe.
    In tests, we provide a mock loop that accepts any coroutine.
    """
    monkeypatch.setattr(
        "asyncio.get_running_loop",
        lambda: MagicMock(),
    )


def test_mcp_server_imports():
    """from applycling.mcp_server import mcp succeeds."""
    from applycling.mcp_server import mcp

    assert mcp is not None


def test_mcp_notifier_notify(_mock_loop):
    """_MCPNotifier doesn't crash on notify, step increments and clamps."""
    from applycling.mcp_server import _MCPNotifier

    ctx = MagicMock()
    notifier = _MCPNotifier(ctx)

    # Call notify 25 times with total=20 — must clamp at 19 (total - 1)
    for i in range(25):
        notifier.notify(f"step {i}")

    assert notifier._step == 19  # clamped to total - 1
    # verify report_progress was called (its return value passed to run_coroutine_threadsafe)
    assert ctx.report_progress.call_count == 25


def test_mcp_notifier_send_document(_mock_loop):
    """send_document appends to artifacts and doesn't crash."""
    from applycling.mcp_server import _MCPNotifier

    ctx = MagicMock()
    notifier = _MCPNotifier(ctx)

    notifier.send_document(Path("/tmp/test.pdf"), caption="resume")

    assert len(notifier.artifacts) == 1
    assert notifier.artifacts[0] == Path("/tmp/test.pdf")
    assert ctx.info.call_count == 1


def test_mcp_notifier_report_complete(_mock_loop):
    """report_complete sends final 100% progress."""
    from applycling.mcp_server import _MCPNotifier

    ctx = MagicMock()
    notifier = _MCPNotifier(ctx)

    notifier.report_complete()

    assert notifier._step == notifier._total
    ctx.report_progress.assert_called_once_with(
        notifier._total, notifier._total, message="Complete"
    )


def test_mcp_serve_command_registered():
    """python -m applycling.cli --help lists mcp, not mcp-group."""
    result = subprocess.run(
        [sys.executable, "-m", "applycling.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "mcp" in result.stdout
    assert "mcp-group" not in result.stdout


def test_mcp_config_output():
    """mcp_config() prints valid JSON with cwd pointing to repo root."""
    from applycling.storage import ROOT

    result = subprocess.run(
        [sys.executable, "-m", "applycling.cli", "mcp", "config"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0

    config = json.loads(result.stdout)
    server = config["mcpServers"]["applycling"]

    assert server["command"] == sys.executable
    assert server["args"] == ["-m", "applycling.cli", "mcp", "serve"]
    assert server["cwd"] == str(ROOT)


def test_add_job_incomplete_profile(monkeypatch):
    """add_job returns error when profile is incomplete."""
    from applycling.mcp_server import add_job

    # Mock load_profile to return empty dict (incomplete profile)
    monkeypatch.setattr(
        "applycling.storage.load_profile",
        lambda: {},
    )

    ctx = MagicMock()
    # ctx.error is an async method — make it return an awaitable
    async def _mock_error(msg):
        return None
    ctx.error = _mock_error

    result = asyncio.run(add_job("http://example.com/job", ctx))

    assert result["error"] == "profile_incomplete"
    assert result["status"] in ("missing_resume", "missing_contact")


def test_add_job_success(monkeypatch, tmp_path):
    """add_job runs pipeline and returns package folder + artifact list."""
    from applycling.mcp_server import add_job

    # Mock load_profile to return a complete profile
    monkeypatch.setattr(
        "applycling.storage.load_profile",
        lambda: {"name": "Test", "email": "t@t.com", "resume_text": "..."},
    )
    # profile_completeness() also checks RESUME_PATH.exists()
    # — point it at a temp file that actually exists
    resume = tmp_path / "resume.md"
    resume.write_text("# Resume\n")
    import applycling.storage as _st
    monkeypatch.setattr(_st, "RESUME_PATH", resume)
    # Mock run_add_notify to return a fixed path
    pkg = tmp_path / "packages" / "job_123"
    pkg.mkdir(parents=True)
    monkeypatch.setattr(
        "applycling.mcp_server.run_add_notify",
        lambda url, notifier, **kw: pkg,
    )

    ctx = MagicMock()
    async def _mock_async(msg):
        return None
    ctx.info = _mock_async
    ctx.error = _mock_async

    result = asyncio.run(add_job("http://example.com/job", ctx))

    assert result["status"] == "complete"
    assert result["package_folder"] == str(pkg)
    assert "artifacts" in result
    assert "error" not in result


# ---------------------------------------------------------------------------
# MCP-T2: Read tools (list_jobs, get_package)
# ---------------------------------------------------------------------------


class _FakeStore:
    """Minimal fake tracker store for MCP-T2 tests."""

    def __init__(self, jobs=None, raise_load_job=None):
        self._jobs = jobs or []
        self._raise_load_job = raise_load_job

    def load_jobs(self):
        return list(self._jobs)

    def load_job(self, job_id):
        if self._raise_load_job:
            raise self._raise_load_job
        for j in self._jobs:
            if j.id == job_id:
                return j
        from applycling.tracker import TrackerError
        raise TrackerError(f"No job found for id: {job_id}")


def _make_job(**overrides):
    """Factory for a Job dataclass with sensible defaults."""
    from applycling.tracker import Job
    defaults = {
        "id": "job_001",
        "title": "Software Engineer",
        "company": "Acme Corp",
        "date_added": "2026-01-15",
        "date_updated": "2026-01-20",
        "status": "reviewing",
        "source_url": "https://example.com/jobs/123",
        "application_url": None,
        "fit_summary": None,
        "package_folder": None,
    }
    defaults.update(overrides)
    return Job(**defaults)


def test_list_jobs_returns_limited_jobs(monkeypatch):
    """list_jobs returns at most 'limit' dicts with correct fields."""
    from applycling.mcp_server import list_jobs

    jobs = [_make_job(id=f"job_{i:03d}", title=f"Engineer {i}") for i in range(5)]
    store = _FakeStore(jobs=jobs)
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = list_jobs(limit=2)
    assert len(result) == 2
    assert result[0]["job_id"] == "job_000"
    assert result[0]["title"] == "Engineer 0"
    assert result[0]["company"] == "Acme Corp"
    # Verify all expected fields are present
    for key in ("job_id", "title", "company", "status", "date_added",
                "date_updated", "package_folder"):
        assert key in result[0], f"Missing key: {key}"


def test_list_jobs_filters_status(monkeypatch):
    """list_jobs filters by status when provided."""
    from applycling.mcp_server import list_jobs

    jobs = [
        _make_job(id="job_001", status="new"),
        _make_job(id="job_002", status="reviewing"),
        _make_job(id="job_003", status="reviewing"),
        _make_job(id="job_004", status="applied"),
    ]
    store = _FakeStore(jobs=jobs)
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = list_jobs(status="reviewing")
    assert len(result) == 2
    assert all(j["status"] == "reviewing" for j in result)
    assert {j["job_id"] for j in result} == {"job_002", "job_003"}


def test_get_package_missing_job_returns_error(monkeypatch):
    """get_package returns error dict when job is not found."""
    from applycling.mcp_server import get_package
    from applycling.tracker import TrackerError

    store = _FakeStore(raise_load_job=TrackerError("No job found for id: bad"))
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = get_package("bad")
    assert result["error"] == "job_not_found"
    assert result["job_id"] == "bad"


def test_get_package_missing_package_folder_returns_error(monkeypatch):
    """get_package returns error when job has no package_folder."""
    from applycling.mcp_server import get_package

    job = _make_job(package_folder=None)
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = get_package("job_001")
    assert result["error"] == "package_missing"
    assert result["job_id"] == "job_001"


def test_get_package_folder_not_found_returns_error(monkeypatch):
    """get_package returns error when package folder doesn't exist."""
    from applycling.mcp_server import get_package

    job = _make_job(package_folder="/nonexistent/path")
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = get_package("job_001")
    assert result["error"] == "package_folder_not_found"
    assert result["job_id"] == "job_001"


def test_get_package_returns_empty_artifacts_for_empty_folder(monkeypatch, tmp_path):
    """get_package returns artifacts=[] when package folder has no markdown files."""
    from applycling.mcp_server import get_package

    pkg = tmp_path / "empty_pkg"
    pkg.mkdir()
    # Create a non-markdown file — should be ignored
    (pkg / "notes.txt").write_text("not markdown")

    job = _make_job(package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = get_package("job_001")
    assert result["artifacts"] == []
    assert result["artifact_count"] == 0
    assert result["truncated"] is False
    assert "error" not in result


def test_get_package_returns_bounded_markdown_artifacts(monkeypatch, tmp_path):
    """get_package returns only .md files with structured metadata."""
    from applycling.mcp_server import get_package

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("# Resume\n\nExperienced engineer.")
    (pkg / "cover_letter.md").write_text("# Cover Letter\n\nI am excited...")
    (pkg / "notes.txt").write_text("plain text note")
    (pkg / "strategy.md").write_text("# Strategy")

    job = _make_job(package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = get_package("job_001")
    assert result["job_id"] == "job_001"
    assert result["artifact_count"] == 3
    # notes.txt is excluded
    names = [a["name"] for a in result["artifacts"]]
    assert "notes.txt" not in names
    assert names == ["cover_letter.md", "resume.md", "strategy.md"]  # sorted

    for a in result["artifacts"]:
        for key in ("name", "path", "kind", "size_bytes", "truncated", "content"):
            assert key in a, f"Missing key: {key}"
        assert a["kind"] == Path(a["name"]).stem


def test_get_package_truncates_large_file(monkeypatch, tmp_path):
    """get_package truncates files exceeding MAX_PACKAGE_FILE_BYTES."""
    from applycling.mcp_server import get_package

    # Monkeypatch the bounds to tiny values
    monkeypatch.setattr("applycling.mcp_server.MAX_PACKAGE_FILE_BYTES", 100)
    monkeypatch.setattr("applycling.mcp_server.MAX_PACKAGE_TOTAL_BYTES", 1_000_000)

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("x" * 200)  # 200 bytes, > 100 limit

    job = _make_job(package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = get_package("job_001")
    assert result["artifact_count"] == 1
    a = result["artifacts"][0]
    assert a["truncated"] is True
    assert "[truncated]" in a["content"]
    assert a["size_bytes"] == 200  # original size, not truncated size


def test_get_package_total_limit(monkeypatch, tmp_path):
    """get_package stops collecting when total bytes cap is hit."""
    from applycling.mcp_server import get_package

    # Set total cap low enough that only one file fits
    monkeypatch.setattr("applycling.mcp_server.MAX_PACKAGE_FILE_BYTES", 10_000)
    monkeypatch.setattr("applycling.mcp_server.MAX_PACKAGE_TOTAL_BYTES", 200)

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    # Each file ~150 bytes of content (content_bytes ~= file bytes since ASCII)
    (pkg / "a_resume.md").write_text("# " + "R" * 140)
    (pkg / "b_cover_letter.md").write_text("# " + "C" * 140)
    (pkg / "c_brief.md").write_text("# " + "B" * 140)

    job = _make_job(package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = get_package("job_001")
    # First file fits (150 bytes), second would push over 200 → stop
    assert result["artifact_count"] < 3
    assert result["truncated"] is True
