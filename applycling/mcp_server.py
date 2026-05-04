"""MCP server for applycling — exposes pipeline capabilities as MCP tools.

All logging goes to stderr. stdout is reserved for JSON-RPC (MCP transport).
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Context
from applycling.pipeline import run_add_notify

mcp = FastMCP("applycling")


def _schedule(coro):
    """Schedule an async MCP context call on the running event loop.

    All ctx methods (info, error, report_progress, etc.) are coroutines in
    mcp>=1.27.0. Since the pipeline runs synchronously, we bridge via
    run_coroutine_threadsafe — the coroutine is submitted to FastMCP's event
    loop and executed there. Fire-and-forget; progress/logging is best-effort.
    """
    try:
        asyncio.run_coroutine_threadsafe(coro, asyncio.get_running_loop())
    except Exception:
        pass


class _MCPNotifier:
    """Adapter: forwards pipeline status messages to MCP progress updates.

    Accumulates artifact paths during the run so they can be returned in the
    add_job result dict. These paths are in-memory only (discarded after the
    tool returns) — MCP-T2's get_package will read from the tracker/package
    folder on disk.
    """

    def __init__(self, ctx: Context):
        self._ctx = ctx
        self._step = 0
        self._total = 20  # safe upper bound; clamp to prevent >100% progress
        self.artifacts: list[Path] = []  # returned in add_job result

    def notify(self, text: str) -> None:
        self._step = min(self._step + 1, self._total - 1)
        _schedule(
            self._ctx.report_progress(
                self._step, self._total, message=text[:200]
            )
        )

    def send_document(self, path: Path, caption: str = "") -> None:
        self.artifacts.append(path)
        _schedule(self._ctx.info(f"Artifact: {path.name}"))


@mcp.tool()
def add_job(url: str, ctx: Context) -> dict:
    """Generate a complete application package for a job URL.

    Runs the full pipeline: scrape → role intel → resume → cover letter →
    email → positioning brief → fit summary. Takes 2–5 minutes.
    Returns the package folder path, artifact list, and status.

    The profile must be set up (name, email, resume) before calling this.
    Run 'applycling setup' if you haven't already.

    Note for MCP client authors: this tool blocks for the duration of the
    pipeline run (2–5 minutes). Progress notifications are sent during the
    wait. Ensure your client has a sufficient request timeout.
    """
    from applycling.storage import load_profile, profile_completeness

    # --- Profile completeness guard (uses PROFILE-T1's single source of truth) ---
    profile = load_profile() or {}
    pstate = profile_completeness(profile)
    if pstate in ("missing_resume", "missing_contact"):
        _schedule(ctx.error(f"Profile incomplete: {pstate}"))
        return {
            "error": "profile_incomplete",
            "status": pstate,
            "message": (
                f"Your Application Profile is {pstate}. "
                "Run 'applycling setup' to complete it, then try again."
            ),
        }

    # --- Run pipeline ---
    notifier = _MCPNotifier(ctx)
    try:
        _schedule(ctx.info(f"Starting pipeline for {url}"))
        package_path = run_add_notify(url, notifier)
        _schedule(ctx.info(f"Package generated: {package_path}"))
        return {
            "package_folder": str(package_path),
            "artifacts": [str(p) for p in notifier.artifacts],
            "status": "complete",
        }
    except Exception as e:
        _schedule(ctx.error(f"Pipeline failed: {e}"))
        return {
            "error": str(e),
            "status": "failed",
            "detail": traceback.format_exc(),
        }
