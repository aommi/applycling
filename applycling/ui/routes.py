"""UI routes for the applycling local workbench.

All routes call applycling.jobs_service functions — never raw DB.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Body, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl

from applycling import jobs_service
from applycling.db_seed import get_or_create_user_by_telegram
from applycling.forward_endpoint import (
    APPROVAL_KEYWORDS,
    handle_active_user_non_url,
    handle_active_user_url,
    handle_confirming_approval,
    handle_confirming_correction,
    handle_new_user_resume,
    handle_new_user_resume_rejected,
    handle_new_user_url,
    is_url_like,
    looks_like_resume_text,
    verify_localhost,
)
from applycling.pipeline import PipelineContext, run_add_notify
from applycling.statuses import STATUS_VALUES, status_color, status_label, job_actions
from applycling.telegram_notify import (
    TelegramNotifier,
    _get_chat_id_for_user,
    notify_error_to_user,
)
from applycling.tracker import check_active_run
from applycling.tracker.postgres_store import PostgresStore
from applycling.auth import create_session_token, verify_password
from applycling.user_admin import (
    TelegramLinkError,
    consume_telegram_link_code,
    parse_telegram_link_code,
)

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


def _web_readonly() -> bool:
    """Return whether the browser workbench should block write actions."""
    return os.environ.get("APPLYCLING_WEB_READONLY", "").lower() == "true"


def _safe_next_url(next_url: str | None) -> str:
    """Return a local redirect target, rejecting absolute/protocol-relative URLs."""
    if not next_url:
        return "/"
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc or not next_url.startswith("/"):
        return "/"
    return next_url


def schedule_pipeline_run(job_id: str, user_id: str | None = None) -> None:
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
            await asyncio.to_thread(jobs_service.run_pipeline, job_id, user_id=user_id)
        except Exception as exc:
            # Belt: catch any unhandled exception in the background task path
            # (asyncio.to_thread failure, cancellation, etc.).
            # run_pipeline already sets status to "failed" on known errors,
            # but an unhandled exception would otherwise leave the job stuck
            # in "generating" forever.
            try:
                jobs_service.set_job_status(
                    job_id,
                    "failed",
                    reason=f"Unexpected error: {exc}",
                    user_id=user_id,
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


# ── Login ───────────────────────────────────────────────────────────────

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    """Show the login form."""
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login", response_model=None)
async def login_submit(
    request: Request,
    email: str = Form(""),
    password: str = Form(""),
) -> Response:
    """Validate credentials and set a signed session cookie."""
    error = "Invalid email or password."

    if not email or not password:
        return templates.TemplateResponse(
            request, "login.html", {"error": error, "email": email}, status_code=401,
        )

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        return templates.TemplateResponse(
            request, "login.html", {"error": error, "email": email}, status_code=401,
        )

    store = PostgresStore(user_id="00000000-0000-0000-0000-000000000001", database_url=db_url)
    with store._conn() as conn:
        row = conn.execute(
            "SELECT id, password_hash FROM users WHERE email = %s AND deleted_at IS NULL",
            (email,),
        ).fetchone()

    if row is None or row["password_hash"] is None:
        return templates.TemplateResponse(
            request, "login.html", {"error": error, "email": email}, status_code=401,
        )

    if not verify_password(password, row["password_hash"]):
        return templates.TemplateResponse(
            request, "login.html", {"error": error, "email": email}, status_code=401,
        )

    token = create_session_token(str(row["id"]))
    next_url = _safe_next_url(request.query_params.get("next", "/"))

    response = RedirectResponse(next_url, status_code=303)
    response.set_cookie(
        "applycling_session",
        token,
        httponly=True,
        secure=os.environ.get("APPLYCLING_SECURE_COOKIES", "true").lower() != "false",
        samesite="lax",
        path="/",
        max_age=86400 * 30,  # 30 days
    )
    return response


# ── Admin ────────────────────────────────────────────────────────────────

def _is_admin(request: Request) -> bool:
    """Return True if the current user is the configured admin."""
    admin_id = os.environ.get("APPLYCLING_ADMIN_USER_ID", "").strip()
    user_id = _current_user_id(request)
    return bool(admin_id and user_id and user_id == admin_id)


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    """Admin: invite alpha users."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required")
    return templates.TemplateResponse(request, "admin.html", {
        "admin_id": _current_user_id(request),
    })


class InviteBody(BaseModel):
    email: str
    display_name: str | None = None


@router.post("/admin/invite")
async def admin_invite(
    request: Request,
    body: InviteBody,
) -> JSONResponse:
    """Create a new user with a password. Admin-only."""
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required")

    import uuid
    import secrets as _secrets
    import psycopg

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")

    from applycling.auth import hash_password

    user_id = str(uuid.uuid4())
    password = _secrets.token_urlsafe(12)
    password_hash = hash_password(password)

    email_addr = body.email.strip().lower()
    display_name = (body.display_name or "").strip() or email_addr.split("@")[0]

    with psycopg.connect(db_url) as conn:
        conn.execute(
            "INSERT INTO users (id, email, display_name, password_hash, onboarding_state, "
            "daily_generation_limit, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, 'active', 10, NOW(), NOW())",
            (user_id, email_addr, display_name, password_hash),
        )

    return JSONResponse({
        "user_id": user_id,
        "email": email_addr,
        "password": password,
        "login_url": f"https://app.applycling.com/login",
    })


# ── Current user helper ────────────────────────────────────────────────

def _current_user_id(request: Request) -> str | None:
    """Return the authenticated user_id from the session, or None.

    In local dev (APPLYCLING_NO_AUTH), the session middleware is disabled
    and request.state.user_id is not set — returns None so routes fall back
    to the shared default store.
    """
    return getattr(request.state, "user_id", None)


# ── Job board ──────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def job_board(request: Request, status: str | None = None) -> HTMLResponse:
    """Show all jobs, optionally filtered by status."""
    user_id = _current_user_id(request)
    jobs = jobs_service.list_jobs(status=status, user_id=user_id)
    return templates.TemplateResponse(request, "jobs.html", {
        "jobs": jobs,
        "current_status": status,
        "readonly": _web_readonly(),
    })


# ── Job detail ─────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_detail(request: Request, job_id: str, error: str = "") -> HTMLResponse:
    """Show a single job with its artifacts and status actions."""
    try:
        job = jobs_service.get_job(job_id, user_id=_current_user_id(request))
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")
    user_id = _current_user_id(request)
    artifacts = jobs_service.list_artifacts(job_id, user_id=user_id)
    error_msg = "Another generation is already running." if error == "already_running" else ""
    return templates.TemplateResponse(request, "job_detail.html", {
        "job": job,
        "artifacts": artifacts,
        "error": error_msg,
        "readonly": _web_readonly(),
    })


# ── Status update ──────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/status")
async def update_job_status(
    request: Request,  # noqa: ARG001
    job_id: str,
    status: str = Form(...),
) -> RedirectResponse:
    """Update a job's workbench status."""
    if _web_readonly():
        raise HTTPException(status_code=403, detail="Web UI is read-only")
    try:
        jobs_service.set_job_status(job_id, status, user_id=_current_user_id(request))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ── Artifact serving ───────────────────────────────────────────────────

@router.get("/artifacts/{job_id}/{filename}")
async def serve_artifact(request: Request, job_id: str, filename: str) -> FileResponse:
    """Serve a generated artifact file for download/view."""
    job = jobs_service.get_job(job_id, user_id=_current_user_id(request))
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
    if _web_readonly():
        raise HTTPException(status_code=403, detail="Web UI is read-only")
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
    if _web_readonly():
        raise HTTPException(status_code=403, detail="Web UI is read-only")

    # Sync pre-check — reject BEFORE creating any job.
    user_id = _current_user_id(request)
    if check_active_run(user_id=user_id):
        return templates.TemplateResponse(
            request,
            "submit.html",
            {"error": "Another generation is already running. "
                       "Please wait for it to complete."},
            status_code=409,
        )

    # Create job (status defaults to "new").
    job = jobs_service.create_job_from_url(url, user_id=user_id)
    job_id = job["id"]

    # Set generating synchronously — eliminates redirect race.
    jobs_service.set_job_status(job_id, "generating", user_id=user_id)

    # Fire and forget.
    schedule_pipeline_run(job_id, user_id=user_id)

    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


# ── Regenerate (command, not status transition) ──────────────────────

@router.post("/jobs/{job_id}/regenerate")
async def regenerate_job(request: Request, job_id: str) -> RedirectResponse:  # noqa: ARG001
    """Run the pipeline on an existing job — fire-and-forget."""
    if _web_readonly():
        raise HTTPException(status_code=403, detail="Web UI is read-only")

    # Sync pre-check — reject BEFORE changing any status.
    user_id = _current_user_id(request)
    if check_active_run(user_id=user_id):
        # Highlight the error on the detail page.
        return RedirectResponse(
            f"/jobs/{job_id}?error=already_running", status_code=303
        )

    # Set generating synchronously.
    jobs_service.set_job_status(job_id, "generating", user_id=user_id)

    # Fire and forget.
    schedule_pipeline_run(job_id, user_id=user_id)

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


class ForwardBody(BaseModel):
    """Request body for the Hermes forwarding endpoint."""

    telegram_id: int
    chat_id: int
    first_name: str | None = None
    message_text: str


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
    """Store a user's chat_id for outbound delivery if missing or invalid."""
    from applycling.tracker.postgres_store import PostgresStore
    store = PostgresStore(
        user_id=user_id,
        database_url=os.environ.get("DATABASE_URL"),
    )
    with store._conn() as conn:
        conn.execute(
            "UPDATE users SET chat_id = %s, updated_at = NOW() "
            "WHERE id = %s AND (chat_id IS NULL OR chat_id = 0)",
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


_verify_localhost = verify_localhost


def _onboarding_token_secret() -> str:
    """Return the server-only secret used to sign web onboarding tokens."""
    secret = (
        os.environ.get("APPLYCLING_ONBOARDING_TOKEN_SECRET")
        or os.environ.get("APPLYCLING_SESSION_SECRET")
        or os.environ.get("APPLYCLING_INTAKE_SECRET")
    )
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="Onboarding token secret is not configured",
        )
    return secret


def _sign_onboarding_user_id(user_id: str) -> str:
    """Create a tamper-resistant token for the web onboarding confirmation step."""
    encoded = base64.urlsafe_b64encode(user_id.encode()).decode().rstrip("=")
    sig = hmac.new(
        _onboarding_token_secret().encode(),
        user_id.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{sig}"


def _verify_onboarding_token(token: str) -> str:
    """Return the signed user_id or reject tampered web onboarding tokens."""
    try:
        encoded, sig = token.split(".", 1)
        padded = encoded + "=" * (-len(encoded) % 4)
        user_id = base64.urlsafe_b64decode(padded.encode()).decode()
    except Exception:
        raise HTTPException(status_code=403, detail="Invalid onboarding token")

    expected = hmac.new(
        _onboarding_token_secret().encode(),
        user_id.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=403, detail="Invalid onboarding token")
    return user_id


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

    # Active-run guard — clean 409 before we start a new generation
    if check_active_run(user_id=db_user_id):
        return JSONResponse(
            {"error": "Another generation is already running. "
                       "Please wait for it to complete."},
            status_code=409,
        )

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
        chat_id = _get_chat_id_for_user(ctx.user_id) if token and ctx.user_id else None
        notifier = (
            TelegramNotifier(token, str(chat_id))
            if chat_id is not None
            else jobs_service._NullNotifier()
        )
        run_add_notify(
            url=ctx.job_url,
            notifier=notifier,
            context=ctx,
            persist_job=ctx.persist_job,
        )
    except Exception as e:
        import sys
        print(
            f"[intake] Pipeline failed for user {ctx.user_id}: {e}",
            file=sys.stderr, flush=True,
        )
        if token and ctx.user_id:
            notify_error_to_user(token, ctx.user_id, ctx.job_url, str(e))


# ── Forwarding route (Hermes dumb relay) ───────────────────────────────

@router.post("/api/forward")
async def forward(
    body: ForwardBody,
    background_tasks: BackgroundTasks,
    _: None = Depends(_verify_localhost),
) -> JSONResponse:
    """Relay endpoint for Hermes Telegram messages.

    The endpoint owns onboarding state. Hermes forwards one Telegram message
    plus metadata and relays only ``relay_message`` back to the user.
    """
    telegram_id = body.telegram_id
    chat_id = body.chat_id
    first_name = body.first_name
    message_text = body.message_text
    is_url = is_url_like(message_text)
    link_code = parse_telegram_link_code(message_text)

    if link_code:
        try:
            linked = consume_telegram_link_code(
                link_code,
                telegram_id=telegram_id,
                chat_id=chat_id,
                first_name=first_name,
            )
        except TelegramLinkError as exc:
            return JSONResponse(
                {
                    "relay_message": (
                        f"I couldn't link this Telegram account: {exc}. "
                        "Ask the applycling admin for a new link code."
                    )
                },
                status_code=409,
            )
        return JSONResponse(
            {
                "relay_message": (
                    "Telegram is linked. Send me a job URL and I'll generate "
                    "your package."
                ),
                "onboarding_state": "active",
                "user_id": linked["user_id"],
                "trigger_pipeline": False,
                "profile_preview": None,
                "actions": ["linked_telegram"],
            }
        )

    try:
        user_data = get_or_create_user_by_telegram(
            telegram_id=telegram_id,
            chat_id=chat_id,
            first_name=first_name,
        )
    except ValueError as exc:
        if "exists but is deleted" in str(exc):
            return JSONResponse(
                {
                    "relay_message": (
                        "This Telegram account was previously removed. "
                        "Ask the applycling admin to restore access."
                    )
                },
                status_code=409,
            )
        raise HTTPException(status_code=503, detail="Forwarding is not configured")
    user_id = user_data["user_id"]
    current_state = user_data["onboarding_state"]
    store: PostgresStore | None = None

    def _store() -> PostgresStore:
        nonlocal store
        if store is None:
            store = PostgresStore(
                user_id=user_id,
                database_url=os.environ.get("DATABASE_URL"),
            )
        return store

    if current_state == "active":
        if is_url:
            _update_chat_id(user_id, chat_id)
            if check_active_run(user_id=user_id):
                return JSONResponse(
                    {"relay_message": "A generation is already running. Please wait."},
                    status_code=409,
                )
            ctx = PipelineContext.from_user_id(user_id, message_text)
            if not _try_increment_daily_generation(user_id):
                return JSONResponse(
                    {"relay_message": "Daily generation limit reached. Try again tomorrow."},
                    status_code=429,
                )
            response = handle_active_user_url(user_id, message_text)
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            background_tasks.add_task(_run_scoped_pipeline, ctx, token)
        else:
            response = handle_active_user_non_url(user_id)

    elif current_state == "confirming":
        msg = message_text.strip().lower()
        if msg in APPROVAL_KEYWORDS:
            response = handle_confirming_approval(user_id)
            _store().save_user_profile(onboarding_state="active")
        else:
            response = handle_confirming_correction(user_id, message_text)
            current = _store().load_user_profile()
            profile = current.get("profile") or {}
            pending = list(profile.get("pending_corrections") or [])
            pending.append(message_text)
            pending = pending[-10:]
            profile["pending_corrections"] = pending
            _store().save_user_profile(profile=profile)

    elif current_state == "new":
        if is_url:
            if check_active_run(user_id=user_id):
                return JSONResponse(
                    {"relay_message": "A generation is already running."},
                    status_code=409,
                )
            ctx = PipelineContext.from_user_id(user_id, message_text)
            if not _try_increment_daily_generation(user_id):
                return JSONResponse(
                    {"relay_message": "Daily generation limit reached."},
                    status_code=429,
                )
            response = handle_new_user_url(user_id, message_text, first_name)
            _store().save_user_profile(onboarding_state="active")
            token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
            background_tasks.add_task(_run_scoped_pipeline, ctx, token)
        else:
            if looks_like_resume_text(message_text):
                _store().save_user_profile(
                    resume=message_text,
                    display_name=first_name,
                    onboarding_state="confirming",
                )
                response = handle_new_user_resume(user_id, message_text, first_name)
            else:
                response = handle_new_user_resume_rejected(user_id)

    else:
        return JSONResponse(
            {
                "relay_message": (
                    "I need to reset your onboarding state. "
                    "Please send your resume again to restart."
                ),
                "onboarding_state": "new",
                "user_id": user_id,
                "trigger_pipeline": False,
                "profile_preview": None,
                "actions": ["restart_onboarding"],
            },
            status_code=409,
        )

    return JSONResponse(
        {
            "relay_message": response.relay_message,
            "onboarding_state": response.onboarding_state,
            "user_id": response.user_id,
            "trigger_pipeline": response.trigger_pipeline,
            "profile_preview": response.profile_preview,
            "actions": response.actions,
        }
    )


# ── Web onboarding flow ───────────────────────────────────────────────

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_landing(request: Request) -> HTMLResponse:
    """Show the web onboarding resume-paste screen."""
    telegram_enabled = bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
    return templates.TemplateResponse(
        request,
        "onboarding.html",
        {
            "telegram_enabled": telegram_enabled,
            "telegram_link": os.environ.get("APPLYCLING_TELEGRAM_LINK", ""),
        },
    )


@router.post("/onboarding/submit-resume")
async def onboarding_submit_resume(
    request: Request,  # noqa: ARG001
    resume_text: str = Form(...),
) -> RedirectResponse:
    """Create a web-only user row and store resume text server-side."""
    import uuid

    import psycopg

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise HTTPException(
            status_code=503,
            detail="Postgres DATABASE_URL is required for onboarding",
        )

    user_id = str(uuid.uuid4())

    with psycopg.connect(db_url) as conn:
        conn.execute(
            "INSERT INTO users (id, email, onboarding_state, display_name, "
            "resume, daily_generation_limit, created_at, updated_at) "
            "VALUES (%s, %s, 'confirming', %s, %s, 10, NOW(), NOW())",
            (user_id, f"web_{user_id}@applycling.local", "", resume_text),
        )
        conn.commit()

    return RedirectResponse(
        f"/onboarding/confirm?token={_sign_onboarding_user_id(user_id)}",
        status_code=303,
    )


@router.get("/onboarding/confirm", response_class=HTMLResponse)
async def onboarding_confirm(request: Request) -> HTMLResponse:
    """Show the consolidated profile confirmation screen."""
    token = request.query_params.get("token", "")
    if not token:
        raise HTTPException(status_code=403, detail="Invalid onboarding token")
    user_id = _verify_onboarding_token(token)
    db_url = os.environ.get("DATABASE_URL")
    resume_text = ""

    if user_id and db_url:
        store = PostgresStore(user_id=user_id, database_url=db_url)
        stored = store.load_user_profile()
        resume_text = stored.get("resume", "")

    profile = {
        "token": token,
        "display_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "linkedin": "",
        "portfolio": "",
    }

    return templates.TemplateResponse(
        request,
        "confirm.html",
        {
            "profile": profile,
            "resume_text": resume_text,
        },
    )


@router.post("/onboarding/confirm")
async def onboarding_save_profile(
    request: Request,  # noqa: ARG001
    token: str = Form(""),
    display_name: str = Form(...),
    email: str = Form(""),
    phone: str = Form(""),
    location: str = Form(""),
    linkedin: str = Form(""),
    portfolio: str = Form(""),
) -> RedirectResponse:
    """Save confirmed profile fields and mark onboarding active."""
    if not token:
        raise HTTPException(status_code=403, detail="Invalid onboarding token")
    user_id = _verify_onboarding_token(token)
    db_url = os.environ.get("DATABASE_URL")
    if user_id and db_url:
        store = PostgresStore(user_id=user_id, database_url=db_url)
        store.save_user_profile(
            profile={
                "name": display_name,
                "email": email,
                "phone": phone,
                "location": location,
                "linkedin": linkedin,
                "portfolio": portfolio,
                "schema_version": "1.0",
            },
            display_name=display_name,
            onboarding_state="active",
        )

    return RedirectResponse("/", status_code=303)


# ── Init ───────────────────────────────────────────────────────────────

def init_app(app):  # type: ignore[no-untyped-def]
    """Register all routes on the FastAPI app."""
    app.include_router(router)
