"""MCP server for applycling — exposes pipeline capabilities as MCP tools.

All logging goes to stderr. stdout is reserved for JSON-RPC (MCP transport).
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Context
from applycling.pipeline import run_add_notify

mcp = FastMCP("applycling")


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
        try:
            self._ctx.report_progress(
                self._step, self._total, message=text[:200]
            )
        except Exception:
            pass  # progress is best-effort; never crash the tool

    def send_document(self, path: Path, caption: str = "") -> None:
        self.artifacts.append(path)
        try:
            self._ctx.info(f"Artifact: {path.name}")
        except Exception:
            pass  # best-effort logging


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
        ctx.error(f"Profile incomplete: {pstate}")
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
        ctx.info(f"Starting pipeline for {url}")
        package_path = run_add_notify(url, notifier)
        ctx.info(f"Package generated: {package_path}")
        return {
            "package_folder": str(package_path),
            "artifacts": [str(p) for p in notifier.artifacts],
            "status": "complete",
        }
    except Exception as e:
        ctx.error(f"Pipeline failed: {e}")
        return {
            "error": str(e),
            "status": "failed",
            "detail": traceback.format_exc(),
        }
