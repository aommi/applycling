"""UI routes for the applycling local workbench.

All routes call applycling.jobs_service functions — never raw DB.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from applycling import jobs_service

router = APIRouter()

# Jinja2 templates — resolved relative to this file
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# ── Status badge color mapping ────────────────────────────────────────
STATUS_COLORS: dict[str, str] = {
    "inbox": "#6b7280",
    "running": "#3b82f6",
    "generated": "#10b981",
    "reviewing": "#f59e0b",
    "applied": "#8b5cf6",
    "skipped": "#ef4444",
    "failed": "#dc2626",
}

_STATUSES: list[str] = [
    "inbox", "running", "generated", "reviewing", "applied", "skipped", "failed",
]

# Register template globals so base.html can use them in any template.
templates.env.globals["statuses"] = lambda: _STATUSES
templates.env.globals["status_color"] = lambda s: STATUS_COLORS.get(s, "#6b7280")


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
async def job_detail(request: Request, job_id: str) -> HTMLResponse:
    """Show a single job with its artifacts and status actions."""
    job = jobs_service.get_job(job_id)
    artifacts = jobs_service.list_artifacts(job_id)
    return templates.TemplateResponse(request, "job_detail.html", {
        "job": job,
        "artifacts": artifacts,
    })


# ── Status update ──────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/status")
async def update_job_status(
    request: Request,  # noqa: ARG001
    job_id: str,
    status: str = Form(...),
) -> RedirectResponse:
    """Update a job's workbench status."""
    jobs_service.set_job_status(job_id, status)
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ── Artifact serving ───────────────────────────────────────────────────

@router.get("/artifacts/{job_id}/{filename}")
async def serve_artifact(job_id: str, filename: str) -> FileResponse:
    """Serve a generated artifact file for download/view."""
    job = jobs_service.get_job(job_id)
    package_folder = job.get("package_folder", "")
    if package_folder:
        filepath = Path(package_folder) / filename
        if filepath.exists():
            return FileResponse(str(filepath))
    raise HTTPException(status_code=404, detail="Artifact not found")


# ── URL submission form ────────────────────────────────────────────────

@router.get("/submit", response_class=HTMLResponse)
async def submit_form(request: Request) -> HTMLResponse:
    """Show the URL submission form."""
    return templates.TemplateResponse(request, "submit.html", {})


@router.post("/submit")
async def submit_job(request: Request, url: str = Form(...)) -> RedirectResponse:  # noqa: ARG001
    """Create a job from URL, trigger the pipeline, redirect to detail page."""
    # 1. Create job in inbox
    job = jobs_service.create_job_from_url(url)
    job_id = job["id"]

    # 2. Set status to running
    jobs_service.set_job_status(job_id, "running")

    # 3. Run pipeline (synchronous for local single user)
    #    run_pipeline() handles its own error catching internally and
    #    updates the status to "generated" or "failed" accordingly.
    try:
        jobs_service.run_pipeline(job_id)
    except Exception:
        # Unexpected crash (programming error, not pipeline failure).
        # run_pipeline already sets failed status for known pipeline errors,
        # so this only fires for truly unexpected exceptions.
        jobs_service.set_job_status(job_id, "failed", reason="Unexpected error during pipeline execution")

    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ── Init ───────────────────────────────────────────────────────────────

def init_app(app):  # type: ignore[no-untyped-def]
    """Register all routes on the FastAPI app."""
    app.include_router(router)
