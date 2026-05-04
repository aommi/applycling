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
