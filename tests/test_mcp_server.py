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

    def load_job_notes(self, job_id: str) -> str:
        return ""


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


# ---------------------------------------------------------------------------
# MCP-T3: Action tools (update_job_status, interview_prep, refine_package)
# ---------------------------------------------------------------------------


def test_update_job_status_success(monkeypatch):
    """update_job_status returns success dict when transition is valid."""
    from applycling.mcp_server import update_job_status

    expected_job = {"job_id": "job_001", "status": "applied", "title": "SE"}
    monkeypatch.setattr(
        "applycling.jobs_service.set_job_status",
        lambda job_id, status, reason=None: expected_job,
    )

    result = update_job_status("job_001", "applied")
    assert result["status"] == "complete"
    assert result["job"] == expected_job


def test_update_job_status_invalid_transition(monkeypatch):
    """update_job_status returns error on invalid transition."""
    from applycling.mcp_server import update_job_status

    def _raise(*args, **kwargs):
        raise ValueError("Cannot transition from 'new' to 'applied'")

    monkeypatch.setattr("applycling.jobs_service.set_job_status", _raise)

    result = update_job_status("job_001", "applied")
    assert result["error"] == "invalid_status_transition"
    assert result["job_id"] == "job_001"


def test_update_job_status_job_not_found(monkeypatch):
    """update_job_status returns error when job not found."""
    from applycling.mcp_server import update_job_status
    from applycling.tracker import TrackerError

    def _raise(*args, **kwargs):
        raise TrackerError("No job found for id: bad")

    monkeypatch.setattr("applycling.jobs_service.set_job_status", _raise)

    result = update_job_status("bad", "applied")
    assert result["error"] == "job_not_found"
    assert result["job_id"] == "bad"


def test_interview_prep_missing_job_returns_error(monkeypatch):
    """interview_prep returns structured error for missing job."""
    from applycling.mcp_server import interview_prep
    from applycling.tracker import TrackerError

    monkeypatch.setattr(
        "applycling.tracker.get_store",
        lambda: _FakeStore(
            raise_load_job=TrackerError("No job found for id: bad")
        ),
    )

    result = interview_prep("bad")
    assert result["error"] == "job_not_found"
    assert result["job_id"] == "bad"


def test_interview_prep_success_writes_artifact(monkeypatch, tmp_path):
    """interview_prep writes interview_prep.md and returns metadata."""
    from applycling.mcp_server import interview_prep

    # Setup fake package folder with required files
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("# Resume\n\nContent.")
    (pkg / "job_description.md").write_text("# JD\n\nJob content.")

    job = _make_job(id="job_prep", title="PM", company="Acme", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])

    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)
    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe",
        lambda: {"model": "test-model", "provider": "test"},
    )
    monkeypatch.setattr(
        "applycling.package_actions._resolve_model_provider",
        lambda cfg, model, provider: ("test-model", "test-provider"),
    )
    monkeypatch.setattr(
        "applycling.package_actions._read_intel_folder",
        lambda folder, vision_model="", vision_provider="": ("", []),
    )

    # Mock LLM to return deterministic chunks
    class _MockLLM:
        def interview_prep(self, *args, **kwargs):
            yield "# Interview Prep\n\nSome content.\n"

    monkeypatch.setattr("applycling.llm.interview_prep", _MockLLM().interview_prep)

    result = interview_prep("job_prep")
    assert result["status"] == "complete"
    assert result["job_id"] == "job_prep"
    assert result["artifacts"][0]["kind"] == "interview_prep"
    assert (pkg / "interview_prep.md").exists()


def test_interview_prep_rejects_invalid_stage(monkeypatch):
    """interview_prep returns structured error for invalid stage."""
    from applycling.mcp_server import interview_prep

    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe",
        lambda: {"model": "test-model", "provider": "test"},
    )
    monkeypatch.setattr(
        "applycling.package_actions._resolve_model_provider",
        lambda cfg, model, provider: ("test-model", "test-provider"),
    )

    # Create a valid package so it reaches stage validation
    pkg_dir = "/tmp/pkg_test_invalid_stage_t3"
    import os
    os.makedirs(pkg_dir, exist_ok=True)
    (Path(pkg_dir) / "resume.md").write_text("test")
    (Path(pkg_dir) / "job_description.md").write_text("test")

    job = _make_job(id="job_001", package_folder=pkg_dir)
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = interview_prep("job_001", stage="invalid-stage")
    assert result["error"] == "invalid_request"
    assert result["job_id"] == "job_001"


def test_interview_prep_configuration_error(monkeypatch, tmp_path):
    """interview_prep returns configuration_error for missing config."""
    from applycling.mcp_server import interview_prep
    from applycling.package_actions import ConfigurationError

    # Setup a valid job + package so it reaches config resolution
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("test")
    (pkg / "job_description.md").write_text("test")

    job = _make_job(id="job_cfg", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    def _raise_cfg():
        raise ConfigurationError("No config found.")

    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe", _raise_cfg
    )

    result = interview_prep("job_cfg")
    assert result["error"] == "configuration_error"


def test_refine_package_requires_feedback(monkeypatch):
    """refine_package returns error for empty feedback."""
    from applycling.mcp_server import refine_package

    result = refine_package("job_001", feedback="")
    assert result["error"] == "invalid_request"


def test_refine_package_missing_package_returns_error(monkeypatch):
    """refine_package returns structured error when package folder is missing."""
    from applycling.mcp_server import refine_package

    job = _make_job(package_folder=None)
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)
    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe",
        lambda: {"model": "test-model", "provider": "test"},
    )
    monkeypatch.setattr(
        "applycling.package_actions._resolve_model_provider",
        lambda cfg, model, provider: ("test-model", "test-provider"),
    )

    result = refine_package("job_001", feedback="improve it")
    assert result["error"] == "package_file_missing"


def test_refine_package_versions_before_writing(monkeypatch, tmp_path):
    """refine_package creates v{n}/ snapshot before writing changed files."""
    from applycling.mcp_server import refine_package

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("# Old Resume\n\nold content\n")
    (pkg / "job_description.md").write_text("# JD\n\njob\n")
    (pkg / "cover_letter.md").write_text("# Old CL\n\nold\n")

    job = _make_job(id="job_r", title="SE", company="ACME", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])

    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)
    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe",
        lambda: {"model": "test-model", "provider": "test"},
    )
    monkeypatch.setattr(
        "applycling.package_actions._resolve_model_provider",
        lambda cfg, model, provider: ("test-model", "test-provider"),
    )

    def _mock_refine_resume(*args, **kwargs):
        yield "# New Resume\n\nnew content\n"

    def _mock_format_resume(*args, **kwargs):
        yield "# New Resume\n\nnew content\n"

    def _mock_refine_cl(*args, **kwargs):
        yield "New cover letter."

    monkeypatch.setattr("applycling.llm.refine_resume", _mock_refine_resume)
    monkeypatch.setattr("applycling.llm.format_resume", _mock_format_resume)
    monkeypatch.setattr("applycling.llm.refine_cover_letter", _mock_refine_cl)
    monkeypatch.setattr(
        "applycling.render.render_resume",
        lambda *args, **kwargs: None,
    )

    # Mock profile loading
    monkeypatch.setattr(
        "applycling.storage.load_profile",
        lambda: {"name": "Test", "email": "t@t.com"},
    )

    result = refine_package("job_r", feedback="improve it")
    assert result["status"] == "complete"
    # Check v{n}/ snapshot was created and contains old content
    v_folders = [d for d in pkg.iterdir() if d.is_dir() and d.name.startswith("v")]
    assert len(v_folders) >= 1
    assert "version_folder" in result

    v_folder = v_folders[0]
    assert (v_folder / "resume.md").exists()
    assert "Old Resume" in (v_folder / "resume.md").read_text()
    assert (v_folder / "cover_letter.md").exists()
    assert "Old CL" in (v_folder / "cover_letter.md").read_text()


def test_refine_package_artifact_filter(monkeypatch, tmp_path):
    """refine_package with artifacts=["resume"] only changes resume."""
    from applycling.mcp_server import refine_package

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("# Old Resume\n\nold content\n")
    (pkg / "job_description.md").write_text("# JD\n\njob\n")
    (pkg / "cover_letter.md").write_text("# Old CL\n\nold\n")

    job = _make_job(id="job_r", title="SE", company="ACME", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])

    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)
    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe",
        lambda: {"model": "test-model", "provider": "test"},
    )
    monkeypatch.setattr(
        "applycling.package_actions._resolve_model_provider",
        lambda cfg, model, provider: ("test-model", "test-provider"),
    )

    def _mock_refine_resume(*args, **kwargs):
        yield "# New Resume\n\nnew content\n"

    def _mock_format_resume(*args, **kwargs):
        yield "# New Resume\n\nnew content\n"

    monkeypatch.setattr("applycling.llm.refine_resume", _mock_refine_resume)
    monkeypatch.setattr("applycling.llm.format_resume", _mock_format_resume)
    monkeypatch.setattr(
        "applycling.render.render_resume",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "applycling.storage.load_profile",
        lambda: {},
    )

    result = refine_package("job_r", feedback="improve it", artifacts=["resume"], cascade=False)
    assert result["status"] == "complete"
    # cover_letter.md should NOT have been touched
    artifact_names = [a["name"] for a in result["artifacts"]]
    assert "resume.md" in artifact_names
    assert "cover_letter.md" not in artifact_names


def test_package_actions_has_no_cli_ui_imports():
    """applycling/package_actions.py imports no CLI/UI dependencies."""
    import ast

    path = Path(__file__).parent.parent / "applycling" / "package_actions.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden = {"click", "rich", "Prompt", "Panel", "console"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in forbidden, f"Banned import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base = node.module.split(".")[0]
                assert base not in forbidden, f"Banned import: {node.module}"


def test_mcp_server_imports_all_tools():
    """MCP server exports all 8 v1 tools — any missing import fails fast."""
    from applycling.mcp_server import (
        add_job,          # MCP-T1
        list_jobs,        # MCP-T2
        get_package,      # MCP-T2
        update_job_status,  # MCP-T3
        interview_prep,   # MCP-T3
        refine_package,   # MCP-T3
        answer_questions, # MCP-T5
        critique_package, # MCP-T5
        generate_questions, # MCP-T5
    )
    for name, fn in [
        ("add_job", add_job),
        ("list_jobs", list_jobs),
        ("get_package", get_package),
        ("update_job_status", update_job_status),
        ("interview_prep", interview_prep),
        ("refine_package", refine_package),
        ("answer_questions", answer_questions),
        ("critique_package", critique_package),
        ("generate_questions", generate_questions),
    ]:
        assert callable(fn), f"{name} is not callable"


def test_mcp_parity():
    """Every pipeline capability exposed via CLI has a matching MCP tool.

    All 8 pipeline capabilities are now covered. When adding a new
    CLI command, add its MCP counterpart here to keep parity enforced.
    """
    import asyncio
    from applycling.mcp_server import mcp

    # Currently matched pairs. Add new entries here when a pipeline
    # capability ships — the test will force you to add the MCP tool.
    expected = {
        "add": "add_job",
        "list": "list_jobs",
        "status": "update_job_status",
        "prep": "interview_prep",
        "refine": "refine_package",
        "answer": "answer_questions",
        "critique": "critique_package",
        "questions": "generate_questions",
    }

    tools = asyncio.run(mcp.list_tools())
    tool_names = {t.name for t in tools}

    for cli_cmd, mcp_name in expected.items():
        assert mcp_name in tool_names, (
            f"CLI '{cli_cmd}' has no MCP tool '{mcp_name}'. "
            f"Add @mcp.tool() in mcp_server.py."
        )


# ---------------------------------------------------------------------------
# MCP-T5: answer_questions / critique_package / generate_questions
# ---------------------------------------------------------------------------


# --- answer_questions ---


def test_answer_questions_missing_job(monkeypatch):
    """answer_questions returns job_not_found for nonexistent job_id."""
    from applycling.mcp_server import answer_questions
    from applycling.tracker import TrackerError

    store = _FakeStore(raise_load_job=TrackerError("No job found for id: bad"))
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = answer_questions("bad_id", questions="Tell me about yourself")
    assert result["error"] == "job_not_found"


def test_answer_questions_empty_questions(monkeypatch):
    """answer_questions returns invalid_request for empty questions."""
    from applycling.mcp_server import answer_questions

    result = answer_questions("job_001", questions="   ")
    assert result["error"] == "invalid_request"


def test_answer_questions_missing_package(monkeypatch):
    """answer_questions returns package_file_missing when no package folder."""
    from applycling.mcp_server import answer_questions

    job = _make_job(package_folder=None)
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = answer_questions("job_001", questions="What is your background?")
    assert result["error"] == "package_file_missing"


def test_answer_questions_configuration_error(monkeypatch, tmp_path):
    """answer_questions returns configuration_error for missing config."""
    from applycling.mcp_server import answer_questions
    from applycling.package_actions import ConfigurationError

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("test")
    (pkg / "job_description.md").write_text("test")

    job = _make_job(id="job_cfg", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    def _raise_cfg():
        raise ConfigurationError("No config found.")

    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe", _raise_cfg
    )

    result = answer_questions("job_cfg", questions="text")
    assert result["error"] == "configuration_error"


def test_answer_questions_success(monkeypatch, tmp_path):
    """answer_questions writes answers.md and returns metadata."""
    from applycling.mcp_server import answer_questions

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("# Resume\n\ntest resume\n")
    (pkg / "job_description.md").write_text("# JD\n\njob desc\n")

    job = _make_job(id="job_a", title="SWE", company="ACME", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])

    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)
    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe",
        lambda: {"model": "test-model", "provider": "test"},
    )
    monkeypatch.setattr(
        "applycling.package_actions._resolve_model_provider",
        lambda cfg, model, provider: ("test-model", "test-provider"),
    )
    monkeypatch.setattr(
        "applycling.storage.load_profile", lambda: None
    )
    monkeypatch.setattr(
        "applycling.storage.load_stories", lambda: ""
    )

    # Mock the LLM to return answers
    def _fake_answer(*args, **kwargs):
        yield "Sure, here are your answers."

    monkeypatch.setattr(
        "applycling.llm.answer_questions", _fake_answer
    )

    result = answer_questions("job_a", questions="Tell me about yourself")
    assert result["status"] == "complete"
    assert result["title"] == "SWE"
    assert result["company"] == "ACME"
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["kind"] == "answers"

    # Verify file was written
    answers_path = Path(result["package_folder"]) / "answers.md"
    assert answers_path.exists()
    content = answers_path.read_text()
    assert "Sure, here are your answers." in content


# --- critique_package ---


def test_critique_missing_job(monkeypatch):
    """critique_package returns job_not_found for nonexistent job_id."""
    from applycling.mcp_server import critique_package
    from applycling.tracker import TrackerError

    store = _FakeStore(raise_load_job=TrackerError("No job found for id: bad"))
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = critique_package("bad_id")
    assert result["error"] == "job_not_found"


def test_critique_missing_package(monkeypatch):
    """critique_package returns package_file_missing when no package folder."""
    from applycling.mcp_server import critique_package

    job = _make_job(package_folder=None)
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = critique_package("job_001")
    assert result["error"] == "package_file_missing"


def test_critique_configuration_error(monkeypatch, tmp_path):
    """critique_package returns configuration_error for missing config."""
    from applycling.mcp_server import critique_package
    from applycling.package_actions import ConfigurationError

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("test")
    (pkg / "job_description.md").write_text("test")

    job = _make_job(id="job_cfg", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    def _raise_cfg():
        raise ConfigurationError("No config found.")

    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe", _raise_cfg
    )

    result = critique_package("job_cfg")
    assert result["error"] == "configuration_error"


def test_critique_success(monkeypatch, tmp_path):
    """critique_package writes critique.md and returns metadata."""
    from applycling.mcp_server import critique_package

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("# Resume\n\ntest\n")
    (pkg / "job_description.md").write_text("# JD\n\ntest\n")

    job = _make_job(id="job_c", title="SWE", company="ACME", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])

    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)
    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe",
        lambda: {"model": "test-model", "provider": "test"},
    )

    def _fake_critique(*args, **kwargs):
        yield "This resume is excellent."

    monkeypatch.setattr("applycling.llm.critique", _fake_critique)

    result = critique_package("job_c")
    assert result["status"] == "complete"
    assert result["title"] == "SWE"
    assert result["company"] == "ACME"
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["kind"] == "critique"

    critique_path = Path(result["package_folder"]) / "critique.md"
    assert critique_path.exists()
    content = critique_path.read_text()
    assert "This resume is excellent." in content


# --- generate_questions ---


def test_generate_questions_missing_job(monkeypatch):
    """generate_questions returns job_not_found for nonexistent job_id."""
    from applycling.mcp_server import generate_questions
    from applycling.tracker import TrackerError

    store = _FakeStore(raise_load_job=TrackerError("No job found for id: bad"))
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = generate_questions("bad_id")
    assert result["error"] == "job_not_found"


def test_generate_questions_invalid_stage(monkeypatch, tmp_path):
    """generate_questions returns invalid_request for unknown stage."""
    from applycling.mcp_server import generate_questions

    # Need a valid package to reach stage validation
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("test")
    (pkg / "job_description.md").write_text("test")

    job = _make_job(id="job_stg", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = generate_questions("job_stg", stage="invalid-stage")
    assert result["error"] == "invalid_request"


def test_generate_questions_missing_package(monkeypatch):
    """generate_questions returns package_file_missing when no package folder."""
    from applycling.mcp_server import generate_questions

    job = _make_job(package_folder=None)
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    result = generate_questions("job_001")
    assert result["error"] == "package_file_missing"


def test_generate_questions_configuration_error(monkeypatch, tmp_path):
    """generate_questions returns configuration_error for missing config."""
    from applycling.mcp_server import generate_questions
    from applycling.package_actions import ConfigurationError

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("test")
    (pkg / "job_description.md").write_text("test")

    job = _make_job(id="job_cfg", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])
    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)

    def _raise_cfg():
        raise ConfigurationError("No config found.")

    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe", _raise_cfg
    )

    result = generate_questions("job_cfg")
    assert result["error"] == "configuration_error"


def test_generate_questions_success(monkeypatch, tmp_path):
    """generate_questions writes questions.md and returns metadata."""
    from applycling.mcp_server import generate_questions

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "resume.md").write_text("# Resume\n\ntest\n")
    (pkg / "job_description.md").write_text("# JD\n\ntest\n")

    job = _make_job(id="job_q", title="SWE", company="ACME", package_folder=str(pkg))
    store = _FakeStore(jobs=[job])

    monkeypatch.setattr("applycling.tracker.get_store", lambda: store)
    monkeypatch.setattr(
        "applycling.package_actions._load_config_safe",
        lambda: {"model": "test-model", "provider": "test"},
    )
    monkeypatch.setattr(
        "applycling.package_actions._resolve_model_provider",
        lambda cfg, model, provider: ("test-model", "test-provider"),
    )

    def _fake_questions(*args, **kwargs):
        yield "1. Tell me about a time you resolved a conflict."

    monkeypatch.setattr(
        "applycling.llm.generate_questions", _fake_questions
    )

    result = generate_questions("job_q", stage="recruiter")
    assert result["status"] == "complete"
    assert result["title"] == "SWE"
    assert result["company"] == "ACME"
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["kind"] == "questions"

    questions_path = Path(result["package_folder"]) / "questions.md"
    assert questions_path.exists()
    content = questions_path.read_text()
    assert "Tell me about a time" in content
