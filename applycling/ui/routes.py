"""UI routes for the applycling local workbench.

All routes call applycling.jobs_service functions — never raw DB.
"""

from __future__ import annotations

import asyncio
import hmac
import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Body, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl

from applycling import jobs_service
from applycling.pipeline import PipelineContext, run_add_notify
from applycling.statuses import STATUS_VALUES, status_color, status_label, job_actions
from applycling.telegram_notify import notify_error_to_user
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
    if os.environ.get("APPLYCLING_WEB_READONLY", "").lower() == "true":
        raise HTTPException(status_code=503, detail="Web UI disabled in this mode")
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

class IntakeBody(BaseModel):
    """Request body for the Hermes intake endpoint (multi-tenant)."""

    job_url: HttpUrl
    telegram_id: int | None = None
    chat_id: int | None = None
    first_name: str | None = None


# ── Intake helpers ────────────────────────────────────────────────────

def _resolve_user_by_intake_secret(secret: str):
    """Return (user_id, telegram_id) for a valid intake secret, or None."""
    import hashlib

    if not secret:
        return None
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    from applycling.tracker.postgres_store import PostgresStore
    store = PostgresStore(
        user_id="00000000-0000-0000-0000-000000000001",
        database_url=os.environ.get("DATABASE_URL"),
    )
    with store._conn() as conn:
        row = conn.execute(
            "SELECT id, telegram_id FROM users "
            "WHERE intake_secret_hash = %s AND deleted_at IS NULL",
            (secret_hash,),
        ).fetchone()
    return (str(row["id"]), row["telegram_id"]) if row else None


def _update_chat_id(user_id: str, chat_id: int) -> None:
    """Store a user's chat_id for outbound delivery if not already set."""
    from applycling.tracker.postgres_store import PostgresStore
    store = PostgresStore(
        user_id=user_id,
        database_url=os.environ.get("DATABASE_URL"),
    )
    with store._conn() as conn:
        conn.execute(
            "UPDATE users SET chat_id = %s WHERE id = %s AND chat_id IS NULL",
            (chat_id, user_id),
        )


def _try_increment_daily_generation(user_id: str) -> bool:
    """Atomically check and increment daily generation count. Returns True if allowed."""
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    from applycling.tracker.postgres_store import PostgresStore
    store = PostgresStore(
        user_id=user_id,
        database_url=os.environ.get("DATABASE_URL"),
    )
    with store._conn() as conn:
        result = conn.execute(
            """UPDATE users
               SET generation_count = CASE
                   WHEN generation_date IS NULL OR generation_date != %s THEN 1
                   ELSE generation_count + 1
               END,
               generation_date = %s
               WHERE id = %s
                 AND (generation_date IS NULL OR generation_date != %s
                      OR generation_count < daily_generation_limit)
               RETURNING generation_count""",
            (today, today, user_id, today),
        )
        return result.fetchone() is not None


# ── Intake route ──────────────────────────────────────────────────────

@router.post("/api/intake")
async def intake(
    request: Request, body: IntakeBody,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Protected endpoint for Hermes to submit job URLs (multi-tenant).

    Resolves the user by their intake secret hash (bound to users row),
    then verifies the body telegram_id matches. Pre-seeded users only —
    unknown telegram_ids are rejected.
    """
    # Resolve user by secret hash — do NOT trust body telegram_id
    secret = request.headers.get("X-Intake-Secret", "")
    user_row = _resolve_user_by_intake_secret(secret)
    if not user_row:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db_user_id, db_telegram_id = user_row

    # Verify body telegram_id matches the user bound to this secret
    body_telegram_id = body.telegram_id
    if body_telegram_id is None or str(body_telegram_id) != str(db_telegram_id):
        raise HTTPException(status_code=403, detail="telegram_id mismatch")

    url = str(body.job_url)

    # Store chat_id for outbound delivery
    if body.chat_id:
        _update_chat_id(db_user_id, body.chat_id)

    # Atomic daily cap — checked BEFORE pipeline starts
    if not _try_increment_daily_generation(db_user_id):
        raise HTTPException(status_code=429, detail="Daily generation limit reached")

    # Build scoped pipeline context for this user
    ctx = PipelineContext.from_user_id(db_user_id, url)

    # Run pipeline in background — pipeline handles job creation, status, notifications
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    background_tasks.add_task(_run_scoped_pipeline, ctx, token)

    return {"status": "generating", "user_id": db_user_id}


def _run_scoped_pipeline(ctx: PipelineContext, token: str) -> None:
    """Background task: run the pipeline for a scoped user with error surfacing."""
    try:
        run_add_notify(ctx)
    except Exception as e:
        import sys
        print(
            f"[intake] Pipeline failed for user {ctx.user_id}: {e}",
            file=sys.stderr, flush=True,
        )
        if token and ctx.user_id:
            notify_error_to_user(token, ctx.user_id, ctx.job_url, str(e))


# ── Init ───────────────────────────────────────────────────────────────

def init_app(app):  # type: ignore[no-untyped-def]
    """Register all routes on the FastAPI app."""
    app.include_router(router)
