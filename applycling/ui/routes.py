"""UI routes for the applycling local workbench.

All routes call applycling.jobs_service functions — never raw DB.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from applycling import jobs_service
from applycling.statuses import STATUS_VALUES, status_color, status_label, job_actions
from applycling.tracker import check_active_run

router = APIRouter()

# Jinja2 templates — resolved relative to this file
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# Register template globals — data-driven from canonical state machine
templates.env.globals["statuses"] = lambda: STATUS_VALUES
templates.env.globals["status_color"] = status_color
templates.env.globals["status_label"] = status_label
templates.env.globals["job_actions"] = job_actions

# Background task tracking — prevents asyncio from GC-ing fire-and-forget tasks.
_background_tasks: set[asyncio.Task] = set()


def schedule_pipeline_run(job_id: str) -> None:
    """Schedule pipeline execution as a fire-and-forget background task.

    Contract: caller has already set the job status to ``'generating'``.
    This function only schedules/wraps background execution, owns task
    retention and error surfacing, and does NOT perform status pre-checks
    or initial status transitions.

    Reusable by PR 6 (H1 intake endpoint) so background-task logic
    is not duplicated.
    """

    async def _run_and_surface_errors() -> None:
        try:
            await asyncio.to_thread(jobs_service.run_pipeline, job_id)
        except Exception as exc:
            # Belt: catch any unhandled exception in the background task path
            # (asyncio.to_thread failure, cancellation, etc.).
            # run_pipeline already sets status to "failed" on known errors,
            # but an unhandled exception would otherwise leave the job stuck
            # in "generating" forever.
            try:
                jobs_service.set_job_status(
                    job_id, "failed", reason=f"Unexpected error: {exc}"
                )
            except Exception:
                pass

    task = asyncio.create_task(_run_and_surface_errors())
    _background_tasks.add(task)
    task.add_done_callback(_on_pipeline_done)


def _on_pipeline_done(task: asyncio.Task) -> None:
    """Suspenders: catch any exception missed by the wrapper."""
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        import sys

        print(
            f"[pipeline] Unhandled background task exception: {exc}",
            file=sys.stderr,
            flush=True,
        )


# ── Job board ──────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def job_board(request: Request, status: str | None = None) -> HTMLResponse:
    """Show all jobs, optionally filtered by status."""
    jobs = jobs_service.list_jobs(status=status)
    return templates.TemplateResponse(request, "jobs.html", {
        "jobs": jobs,
        "current_status": status,
    })


# ── Job detail ─────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: str, error: str = "") -> HTMLResponse:
    """Show a single job with its artifacts and status actions."""
    try:
        job = jobs_service.get_job(job_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")
    artifacts = jobs_service.list_artifacts(job_id)
    error_msg = "Another generation is already running." if error == "already_running" else ""
    return templates.TemplateResponse(request, "job_detail.html", {
        "job": job,
        "artifacts": artifacts,
        "error": error_msg,
    })


# ── Status update ──────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/status")
async def update_job_status(
    request: Request,  # noqa: ARG001
    job_id: str,
    status: str = Form(...),
) -> RedirectResponse:
    """Update a job's workbench status."""
    try:
        jobs_service.set_job_status(job_id, status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ── Artifact serving ───────────────────────────────────────────────────

@router.get("/artifacts/{job_id}/{filename}")
async def serve_artifact(job_id: str, filename: str) -> FileResponse:
    """Serve a generated artifact file for download/view."""
    job = jobs_service.get_job(job_id)
    package_folder = job.get("package_folder", "")
    if package_folder:
        pkg = Path(package_folder).resolve()
        filepath = (pkg / filename).resolve()
        if filepath.is_relative_to(pkg) and filepath.exists():
            return FileResponse(str(filepath))
    raise HTTPException(status_code=404, detail="Artifact not found")


# ── URL submission form ────────────────────────────────────────────────

@router.get("/submit", response_class=HTMLResponse)
async def submit_form(request: Request) -> HTMLResponse:
    """Show the URL submission form."""
    return templates.TemplateResponse(request, "submit.html", {})


@router.post("/submit")
async def submit_job(request: Request, url: str = Form(...)) -> RedirectResponse:  # noqa: ARG001
    """Create a job from URL, fire pipeline in background, redirect immediately.

    - Sync pre-check: if an active run exists, render the form with an error
      BEFORE creating any job row.  No dead "new" jobs left behind.
    - Set status to ``'generating'`` synchronously to eliminate the redirect
      race — the detail page always sees the correct status.
    - Pipeline runs as a fire-and-forget background task.
    """
    # Sync pre-check — reject BEFORE creating any job.
    if check_active_run():
        return templates.TemplateResponse(
            request,
            "submit.html",
            {"error": "Another generation is already running. "
                       "Please wait for it to complete."},
            status_code=409,
        )

    # Create job (status defaults to "new").
    job = jobs_service.create_job_from_url(url)
    job_id = job["id"]

    # Set generating synchronously — eliminates redirect race.
    jobs_service.set_job_status(job_id, "generating")

    # Fire and forget.
    schedule_pipeline_run(job_id)

    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ── Regenerate (command, not status transition) ──────────────────────

@router.post("/jobs/{job_id}/regenerate")
async def regenerate_job(request: Request, job_id: str) -> RedirectResponse:  # noqa: ARG001
    """Run the pipeline on an existing job — fire-and-forget."""
    # Sync pre-check — reject BEFORE changing any status.
    if check_active_run():
        # Highlight the error on the detail page.
        return RedirectResponse(
            f"/jobs/{job_id}?error=already_running", status_code=303
        )

    # Set generating synchronously.
    jobs_service.set_job_status(job_id, "generating")

    # Fire and forget.
    schedule_pipeline_run(job_id)

    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ── Health check ───────────────────────────────────────────────────────

@router.get("/healthz")
async def healthz() -> JSONResponse:
    """Liveness check — returns 200 when app is alive and DB is reachable.

    Uses a simple ``list_jobs()`` call to exercise the store connection.
    Transient DB blips are acceptable — decoupling liveness from readiness
    is future work.
    """
    try:
        jobs_service.list_jobs()
        return JSONResponse({"status": "ok", "db": "reachable"}, status_code=200)
    except Exception as e:
        import sys

        print(
            f"[healthz] DB unreachable: {e}",
            file=sys.stderr, flush=True,
        )
        return JSONResponse(
            {"status": "unhealthy", "db": "unreachable"},
            status_code=503,
        )


# ── Hermes intake endpoint ─────────────────────────────────────────────

import hmac
import os

from fastapi import Body

_INTAKE_SECRET = os.environ.get("APPLYCLING_INTAKE_SECRET", "")


@router.post("/api/intake")
async def intake(request: Request, body: dict = Body(...)) -> dict[str, Any]:
    """Protected endpoint for Hermes to submit job URLs to hosted applycling.

    Requires ``X-Intake-Secret`` header matching ``APPLYCLING_INTAKE_SECRET``.
    Protected by auth middleware exemption in ``ui/__init__.py``.

    Request body: ``{"job_url": "https://..."}``
    Response (success): ``{"job_id": "...", "status": "generating"}``
    Response (conflict): ``{"error": "Another generation is already running"}`` → 409
    """
    # Validate intake secret — constant-time comparison.
    provided_secret = request.headers.get("X-Intake-Secret", "")
    if not _INTAKE_SECRET or not hmac.compare_digest(
        provided_secret, _INTAKE_SECRET
    ):
        raise HTTPException(status_code=401, detail="Invalid intake secret")

    url = body.get("job_url", "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing job_url")

    # Sync pre-check BEFORE creating any job — no dead "new" jobs.
    if check_active_run():
        return JSONResponse(
            {"error": "Another generation is already running. "
                       "Please wait for it to complete."},
            status_code=409,
        )

    # Create job, set generating, schedule pipeline.
    job = jobs_service.create_job_from_url(url)
    job_id = job["id"]
    jobs_service.set_job_status(job_id, "generating")
    schedule_pipeline_run(job_id)

    return {"job_id": job_id, "status": "generating"}


# ── Init ───────────────────────────────────────────────────────────────

def init_app(app):  # type: ignore[no-untyped-def]
    """Register all routes on the FastAPI app."""
    app.include_router(router)
