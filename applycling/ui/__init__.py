"""FastAPI app factory for the applycling local workbench."""

from __future__ import annotations

import os

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

app = FastAPI(title="applycling workbench")

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ── Auth middleware ─────────────────────────────────────────────────────

_UNAUTH_ROUTES: frozenset[str] = frozenset(
    {"/healthz", "/api/intake", "/api/forward", "/login", "/onboarding/submit-resume"}
)


class SessionMiddleware(BaseHTTPMiddleware):
    """Per-user session auth for the hosted workbench.

    - Auth is ON by default in hosted mode (fail closed).
    - Local dev bypass via ``APPLYCLING_NO_AUTH`` env var.
    - Sessions are HMAC-signed cookies (``applycling_session``).
    - Unauthenticated requests redirect to ``/login``.
    - ``/healthz``, ``/api/intake``, ``/api/forward``, ``/login``, and
      ``/onboarding/submit-resume`` are exempted from auth.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._is_auth_disabled = bool(
            os.environ.get("APPLYCLING_NO_AUTH", "").strip()
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        from applycling.auth import verify_session_token
        from urllib.parse import quote

        # Static files don't go through the middleware.
        if request.url.path.startswith("/static/"):
            return await call_next(request)

        # Auth disabled for local dev.
        if self._is_auth_disabled:
            return await call_next(request)

        # Exempt liveness, intake, forwarding, login, and onboarding submit.
        if request.url.path in _UNAUTH_ROUTES:
            return await call_next(request)

        # Check session cookie.
        session = request.cookies.get("applycling_session", "")
        if session:
            user_id = verify_session_token(session)
            if user_id:
                request.state.user_id = user_id
                return await call_next(request)

        # Not authenticated — redirect to login.
        from fastapi.responses import RedirectResponse

        next_url = quote(str(request.url.path), safe="")
        if request.url.query:
            next_url += "?" + request.url.query
        return RedirectResponse(
            f"/login?next={next_url}", status_code=303,
        )


app.add_middleware(SessionMiddleware)


# ── Startup validation ──────────────────────────────────────────────────

def _validate_hosted_secrets() -> None:
    """Fail fast if hosted Postgres mode is active and required secrets are
    missing or misconfigured.

    Checks:
    - APPLYCLING_SESSION_SECRET must be set.
    - APPLYCLING_NO_AUTH must not be set in Postgres mode (prod bypass).
    - APPLYCLING_INTAKE_SECRET must be set.

    Raises RuntimeError with a list of all missing vars at once.
    """
    import sys

    db_backend = os.environ.get("APPLYCLING_DB_BACKEND", "").strip().lower()
    if db_backend != "postgres":
        return

    missing: list[str] = []

    if not os.environ.get("APPLYCLING_SESSION_SECRET", "").strip():
        missing.append("APPLYCLING_SESSION_SECRET")

    # NO_AUTH is a dev convenience — refuse it in production.
    no_auth = os.environ.get("APPLYCLING_NO_AUTH", "").strip()
    if no_auth:
        missing.append(
            "APPLYCLING_NO_AUTH (must NOT be set in hosted Postgres mode)"
        )

    if not os.environ.get("APPLYCLING_INTAKE_SECRET"):
        missing.append("APPLYCLING_INTAKE_SECRET")

    if missing:
        msg = (
            f"Hosted Postgres mode requires the following env vars: "
            f"{', '.join(missing)}. "
            f"See docs/deploy/DEPLOY.md § Environment Variables."
        )
        print(f"[startup] ERROR: {msg}", file=sys.stderr, flush=True)
        raise RuntimeError(msg)


@app.on_event("startup")
async def _startup_validate() -> None:
    """Validate hosted secrets at startup, not at module import time.

    Running at startup avoids breaking tests and CLI commands that import
    ``applycling.ui`` without a full hosted env configured.
    """
    _validate_hosted_secrets()

# ── Startup sweep ───────────────────────────────────────────────────────

from applycling.tracker import register_startup_sweep

register_startup_sweep(app)

# ── Routes ──────────────────────────────────────────────────────────────

from . import routes  # noqa: E402

routes.init_app(app)
