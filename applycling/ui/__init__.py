"""FastAPI app factory for the applycling local workbench."""

from __future__ import annotations

import os
import secrets

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

_UNAUTH_ROUTES: frozenset[str] = frozenset({"/healthz", "/api/intake"})


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """Simple personal auth gate for the hosted workbench.

    - Auth is ON by default in hosted mode (fail closed).
    - Local dev bypass via ``APPLYCLING_NO_AUTH`` env var (NOT IP-based).
    - Credentials from ``APPLYCLING_UI_AUTH_USER`` / ``APPLYCLING_UI_AUTH_PASSWORD``.
    - ``/healthz`` and ``/api/intake`` are exempted from auth.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._is_auth_disabled = bool(os.environ.get("APPLYCLING_NO_AUTH", "").strip())
        self._expected_user = os.environ.get("APPLYCLING_UI_AUTH_USER", "")
        self._expected_password = os.environ.get("APPLYCLING_UI_AUTH_PASSWORD", "")

    async def dispatch(self, request: Request, call_next) -> Response:
        # Static files and templates don't go through the middleware.
        if request.url.path.startswith("/static"):
            return await call_next(request)

        # Auth disabled for local dev.
        if self._is_auth_disabled:
            return await call_next(request)

        # Exempt liveness and intake endpoints.
        if request.url.path in _UNAUTH_ROUTES:
            return await call_next(request)

        # Require credentials in hosted mode.
        if not self._expected_user or not self._expected_password:
            # No credentials configured — allow unauthenticated access
            # (local dev, tests, or misconfigured hosted).
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return self._auth_required_response()

        try:
            import base64

            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            user, _, password = decoded.partition(":")
        except Exception:
            return self._auth_required_response()

        if not secrets.compare_digest(user, self._expected_user):
            return self._auth_required_response()
        if not secrets.compare_digest(password, self._expected_password):
            return self._auth_required_response()

        return await call_next(request)

    @staticmethod
    def _auth_required_response() -> Response:
        return Response(
            content="Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="applycling"'},
        )


app.add_middleware(BasicAuthMiddleware)


# ── Startup validation ──────────────────────────────────────────────────

def _validate_hosted_secrets() -> None:
    """Fail fast if hosted Postgres mode is active and required secrets are missing.

    PR 1 forward-declares APPLYCLING_INTAKE_SECRET as a required hosted env var,
    so this check does not block workbench deployment before PR 6 lands.
    """
    db_backend = os.environ.get("APPLYCLING_DB_BACKEND", "").strip().lower()
    if db_backend != "postgres":
        return

    missing: list[str] = []
    if not os.environ.get("APPLYCLING_UI_AUTH_USER"):
        missing.append("APPLYCLING_UI_AUTH_USER")
    if not os.environ.get("APPLYCLING_UI_AUTH_PASSWORD"):
        missing.append("APPLYCLING_UI_AUTH_PASSWORD")
    if not os.environ.get("APPLYCLING_INTAKE_SECRET"):
        missing.append("APPLYCLING_INTAKE_SECRET")

    if missing:
        raise RuntimeError(
            f"Hosted Postgres mode requires the following env vars: "
            f"{', '.join(missing)}. "
            f"See docs/deploy/DEPLOY.md § Environment Variables."
        )


_validate_hosted_secrets()

# ── Startup sweep ───────────────────────────────────────────────────────

from applycling.tracker import register_startup_sweep

register_startup_sweep(app)

# ── Routes ──────────────────────────────────────────────────────────────

from . import routes  # noqa: E402

routes.init_app(app)
