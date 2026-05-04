"""MCP server for applycling — exposes pipeline capabilities as MCP tools.

All logging goes to stderr. stdout is reserved for JSON-RPC (MCP transport).
"""

from __future__ import annotations

import asyncio
import traceback
from pathlib import Path
from mcp.server.fastmcp import FastMCP, Context
from applycling.pipeline import run_add_notify

# --- Bounds for get_package artifact content ---
MAX_PACKAGE_FILE_BYTES = 50_000
MAX_PACKAGE_TOTAL_BYTES = 200_000


def _job_to_mcp_dict(job) -> dict:
    return {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "status": job.status,
        "date_added": job.date_added,
        "date_updated": job.date_updated,
        "source_url": job.source_url,
        "application_url": job.application_url,
        "fit_summary": job.fit_summary,
        "package_folder": job.package_folder,
    }


def _read_text_bounded(path: Path, max_bytes: int) -> tuple[str, bool, int]:
    raw = path.read_bytes()
    size = len(raw)
    truncated = size > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text = text + "\n\n[truncated]"
    return text, truncated, size


mcp = FastMCP("applycling")


class _MCPNotifier:
    """Adapter: forwards pipeline status messages to MCP progress updates.

    Accumulates artifact paths during the run so they can be returned in the
    add_job result dict. These paths are in-memory only (discarded after the
    tool returns) — MCP-T2's get_package will read from the tracker/package
    folder on disk.

    run_add_notify() runs in a thread (via asyncio.to_thread) so the event
    loop stays free to process progress/logging coroutines. This notifier
    schedules ctx calls onto the captured main loop from the worker thread.
    """

    def __init__(self, ctx: Context):
        self._ctx = ctx
        self._loop = asyncio.get_running_loop()  # captured in async add_job
        self._step = 0
        self._total = 20  # safe upper bound; clamp to prevent >100% progress
        self.artifacts: list[Path] = []  # returned in add_job result

    def _schedule(self, coro):
        """Schedule a coroutine on the main event loop, fire-and-forget."""
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            pass

    def notify(self, text: str) -> None:
        self._step = min(self._step + 1, self._total - 1)
        self._schedule(
            self._ctx.report_progress(
                self._step, self._total, message=text[:200]
            )
        )

    def send_document(self, path: Path, caption: str = "") -> None:
        self.artifacts.append(path)
        self._schedule(self._ctx.info(f"Artifact: {path.name}"))

    def report_complete(self) -> None:
        """Send final 100% progress — compensates for the total-1 clamp."""
        self._step = self._total
        self._schedule(
            self._ctx.report_progress(self._total, self._total, message="Complete")
        )


@mcp.tool()
async def add_job(url: str, ctx: Context) -> dict:
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
        await ctx.error(f"Profile incomplete: {pstate}")
        return {
            "error": "profile_incomplete",
            "status": pstate,
            "message": (
                f"Your Application Profile is {pstate}. "
                "Run 'applycling setup' to complete it, then try again."
            ),
        }

    # --- Run pipeline in a thread so the event loop stays free for progress ---
    notifier = _MCPNotifier(ctx)
    try:
        await ctx.info(f"Starting pipeline for {url}")
        package_path = await asyncio.to_thread(run_add_notify, url, notifier)
        notifier.report_complete()
        await ctx.info(f"Package generated: {package_path}")
        return {
            "package_folder": str(package_path),
            "artifacts": [str(p) for p in notifier.artifacts],
            "status": "complete",
        }
    except Exception as e:
        await ctx.error(f"Pipeline failed: {e}")
        return {
            "error": str(e),
            "status": "failed",
            "detail": traceback.format_exc(),
        }


@mcp.tool()
def list_jobs(limit: int = 20, status: str | None = None) -> list[dict]:
    """List tracked job applications. Optionally filter by status."""
    from applycling.tracker import get_store

    safe_limit = max(1, min(limit, 100))
    jobs = get_store().load_jobs()

    if status:
        jobs = [job for job in jobs if job.status == status]

    return [_job_to_mcp_dict(job) for job in jobs[:safe_limit]]


@mcp.tool()
def get_package(job_id: str) -> dict:
    """Return bounded artifact metadata and text content for a job package."""
    from applycling.tracker import TrackerError, get_store

    try:
        job = get_store().load_job(job_id)
    except TrackerError as e:
        return {
            "error": "job_not_found",
            "message": str(e),
            "job_id": job_id,
        }

    if not job.package_folder:
        return {
            "error": "package_missing",
            "message": f"No package folder recorded for job {job_id}",
            "job_id": job_id,
        }

    folder = Path(job.package_folder)
    if not folder.exists() or not folder.is_dir():
        return {
            "error": "package_folder_not_found",
            "message": f"Package folder not found: {folder}",
            "job_id": job_id,
            "package_folder": str(folder),
        }

    artifacts = []
    total_bytes = 0
    total_truncated = False

    for md_file in sorted(folder.glob("*.md")):
        try:
            content, file_truncated, size_bytes = _read_text_bounded(
                md_file, MAX_PACKAGE_FILE_BYTES
            )
        except OSError:
            continue

        content_bytes = len(content.encode("utf-8", errors="replace"))
        if total_bytes + content_bytes > MAX_PACKAGE_TOTAL_BYTES:
            total_truncated = True
            break

        artifacts.append(
            {
                "name": md_file.name,
                "path": str(md_file),
                "kind": md_file.stem,
                "size_bytes": size_bytes,
                "truncated": file_truncated,
                "content": content,
            }
        )
        total_bytes += content_bytes
        total_truncated = total_truncated or file_truncated

    return {
        "job_id": job.id,
        "title": job.title,
        "company": job.company,
        "status": job.status,
        "package_folder": str(folder),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
        "limits": {
            "max_file_bytes": MAX_PACKAGE_FILE_BYTES,
            "max_total_bytes": MAX_PACKAGE_TOTAL_BYTES,
        },
        "truncated": total_truncated,
    }


@mcp.tool()
def update_job_status(job_id: str, status: str, reason: str | None = None) -> dict:
    """Update a tracked job's status using the canonical state machine."""
    from applycling.jobs_service import set_job_status
    from applycling.tracker import TrackerError

    try:
        job = set_job_status(job_id, status, reason=reason)
    except TrackerError as e:
        return {"error": "job_not_found", "message": str(e), "job_id": job_id}
    except ValueError as e:
        return {
            "error": "invalid_status_transition",
            "message": str(e),
            "job_id": job_id,
            "requested_status": status,
        }

    return {"status": "complete", "job": job}


@mcp.tool()
def interview_prep(
    job_id: str,
    stage: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> dict:
    """Generate interview prep materials for an existing job package."""
    from applycling.package_actions import (
        ConfigurationError,
        generate_interview_prep_for_job,
    )
    from applycling.tracker import TrackerError

    try:
        return generate_interview_prep_for_job(
            job_id, stage=stage, model=model, provider=provider
        )
    except TrackerError as e:
        return {"error": "job_not_found", "message": str(e), "job_id": job_id}
    except ConfigurationError as e:
        return {"error": "configuration_error", "message": str(e), "job_id": job_id}
    except ValueError as e:
        return {"error": "invalid_request", "message": str(e), "job_id": job_id}
    except FileNotFoundError as e:
        return {"error": "package_file_missing", "message": str(e), "job_id": job_id}
    except RuntimeError as e:
        return {"error": "generation_failed", "message": str(e), "job_id": job_id}


@mcp.tool()
def refine_package(
    job_id: str,
    feedback: str,
    artifacts: list[str] | None = None,
    cascade: bool = False,
    model: str | None = None,
    provider: str | None = None,
) -> dict:
    """Refine generated package artifacts using explicit feedback."""
    from applycling.package_actions import ConfigurationError, refine_package_for_job
    from applycling.tracker import TrackerError

    try:
        return refine_package_for_job(
            job_id,
            feedback=feedback,
            artifacts=artifacts,
            cascade=cascade,
            model=model,
            provider=provider,
        )
    except TrackerError as e:
        return {"error": "job_not_found", "message": str(e), "job_id": job_id}
    except ConfigurationError as e:
        return {"error": "configuration_error", "message": str(e), "job_id": job_id}
    except ValueError as e:
        return {"error": "invalid_request", "message": str(e), "job_id": job_id}
    except FileNotFoundError as e:
        return {"error": "package_file_missing", "message": str(e), "job_id": job_id}
    except RuntimeError as e:
        return {"error": "generation_failed", "message": str(e), "job_id": job_id}
