"""UI routes for the applycling local workbench.

All routes call applycling.jobs_service functions — never raw DB.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from applycling import jobs_service
from applycling.statuses import STATUS_VALUES, status_color, status_label, job_actions

router = APIRouter()

# Jinja2 templates — resolved relative to this file
_templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

# Register template globals — data-driven from canonical state machine
templates.env.globals["statuses"] = lambda: STATUS_VALUES
templates.env.globals["status_color"] = status_color
templates.env.globals["status_label"] = status_label
templates.env.globals["job_actions"] = job_actions


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
    try:
        job = jobs_service.get_job(job_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")
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
    import asyncio

    # 1. Create job (status defaults to "new")
    job = jobs_service.create_job_from_url(url)
    job_id = job["id"]

    # 2. Run pipeline in a thread — Playwright uses sync API, conflicts with asyncio
    try:
        await asyncio.to_thread(jobs_service.run_pipeline, job_id)
    except Exception:
        jobs_service.set_job_status(job_id, "failed", reason="Unexpected error")
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ── Init ───────────────────────────────────────────────────────────────

def init_app(app):  # type: ignore[no-untyped-def]
    """Register all routes on the FastAPI app."""
    app.include_router(router)
