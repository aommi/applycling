"""Tests for applycling UI routes — canonical state machine integration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from applycling.ui import app
from applycling.ui import routes as ui_routes


@pytest.fixture
def client(monkeypatch):
    """Return a TestClient for the applycling workbench app.
    
    Auth is disabled by default for route-level testing.  Auth-specific tests
    build their own app instances with session middleware enabled.
    """
    monkeypatch.setenv("APPLYCLING_NO_AUTH", "true")
    monkeypatch.setenv("APPLYCLING_SESSION_SECRET", "test-secret")
    return TestClient(app)


# ── Smoke tests ──────────────────────────────────────────────────────

def test_root_returns_200_and_contains_applycling(client):
    """GET / renders the job board with the applycling brand."""
    with patch("applycling.ui.routes.jobs_service.list_jobs", return_value=[]):
        response = client.get("/")
    assert response.status_code == 200
    assert "applycling" in response.text.lower()


def test_root_still_renders_in_readonly_mode(monkeypatch, client):
    """GET / remains usable when write actions are disabled."""
    monkeypatch.setenv("APPLYCLING_WEB_READONLY", "true")
    with patch("applycling.ui.routes.jobs_service.list_jobs", return_value=[]):
        response = client.get("/")
    assert response.status_code == 200
    assert "submit url" not in response.text.lower()


def test_submit_form_returns_200(client):
    """GET /submit renders the URL submission form."""
    response = client.get("/submit")
    assert response.status_code == 200


def test_submit_form_rejected_in_readonly_mode(monkeypatch, client):
    """GET /submit is blocked when write actions are disabled."""
    monkeypatch.setenv("APPLYCLING_WEB_READONLY", "true")
    response = client.get("/submit")
    assert response.status_code == 403


def test_job_detail_nonexistent_returns_404(client):
    """GET /jobs/nonexistent returns 404 when the job is not found."""
    with patch(
        "applycling.ui.routes.jobs_service.get_job",
        side_effect=Exception("Job not found"),
    ):
        response = client.get("/jobs/nonexistent")
    assert response.status_code == 404


# ── Health check ───────────────────────────────────────────────────────

def test_healthz_returns_200_when_db_healthy(client):
    """GET /healthz returns 200 when list_jobs() succeeds."""
    with patch("applycling.ui.routes.jobs_service.list_jobs", return_value=[]):
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["db"] == "reachable"


def test_healthz_returns_503_when_db_unhealthy(client):
    """GET /healthz returns 503 when list_jobs() raises."""
    with patch(
        "applycling.ui.routes.jobs_service.list_jobs",
        side_effect=Exception("DB down"),
    ):
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
    assert response.json()["db"] == "unreachable"


# ── Submit guard rejection ────────────────────────────────────────────

def test_submit_rejects_with_active_run(client):
    """POST /submit renders form + 409 without creating a job when active run exists."""
    with patch(
        "applycling.ui.routes.check_active_run", return_value=True
    ):
        response = client.post("/submit", data={"url": "https://example.com/jobs/test"})
    assert response.status_code == 409
    assert "html" in response.headers.get("content-type", "").lower()
    assert "already running" in response.text.lower()


def test_submit_does_not_create_job_when_guard_blocks(client):
    """POST /submit does NOT call create_job_from_url when active run exists."""
    with (
        patch("applycling.ui.routes.check_active_run", return_value=True),
        patch("applycling.ui.routes.jobs_service.create_job_from_url") as mock_create,
    ):
        response = client.post("/submit", data={"url": "https://example.com/jobs/test"})
    mock_create.assert_not_called()


# ── Regenerate guard rejection ────────────────────────────────────────

def test_regenerate_rejects_with_active_run(client):
    """POST /jobs/{id}/regenerate redirects with error when active run exists."""
    with (
        patch("applycling.ui.routes.check_active_run", return_value=True),
        # Prevent set_job_status from failing on nonexistent job
        patch(
            "applycling.ui.routes.jobs_service.set_job_status",
            side_effect=Exception("not found"),
        ),
    ):
        response = client.post(
            "/jobs/some-id/regenerate", follow_redirects=False
        )
    assert response.status_code == 303
    assert "error=already_running" in response.headers["location"]


def test_regenerate_does_not_change_status_when_guard_blocks(client):
    """POST /jobs/{id}/regenerate does NOT call set_job_status when active run exists."""
    with (
        patch("applycling.ui.routes.check_active_run", return_value=True),
        patch("applycling.ui.routes.jobs_service.set_job_status") as mock_set,
    ):
        response = client.post(
            "/jobs/some-id/regenerate", follow_redirects=False
        )
    mock_set.assert_not_called()


def test_submit_scopes_status_and_pipeline_to_session_user(client):
    """POST /submit keeps all follow-up work scoped to the authenticated user."""
    client.app.dependency_overrides = {}

    with (
        patch("applycling.ui.routes._current_user_id", return_value=_USER_ID),
        patch("applycling.ui.routes.check_active_run", return_value=False) as mock_active,
        patch(
            "applycling.ui.routes.jobs_service.create_job_from_url",
            return_value={"id": "job-1"},
        ) as mock_create,
        patch("applycling.ui.routes.jobs_service.set_job_status") as mock_status,
        patch("applycling.ui.routes.schedule_pipeline_run") as mock_schedule,
    ):
        response = client.post(
            "/submit",
            data={"url": "https://example.com/jobs/test"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    mock_active.assert_called_once_with(user_id=_USER_ID)
    mock_create.assert_called_once_with("https://example.com/jobs/test", user_id=_USER_ID)
    mock_status.assert_called_once_with("job-1", "generating", user_id=_USER_ID)
    mock_schedule.assert_called_once_with("job-1", user_id=_USER_ID)


def test_regenerate_scopes_status_and_pipeline_to_session_user(client):
    """POST /jobs/{id}/regenerate uses the session user for guards and updates."""
    with (
        patch("applycling.ui.routes._current_user_id", return_value=_USER_ID),
        patch("applycling.ui.routes.check_active_run", return_value=False) as mock_active,
        patch("applycling.ui.routes.jobs_service.set_job_status") as mock_status,
        patch("applycling.ui.routes.schedule_pipeline_run") as mock_schedule,
    ):
        response = client.post(
            "/jobs/job-1/regenerate",
            follow_redirects=False,
        )

    assert response.status_code == 303
    mock_active.assert_called_once_with(user_id=_USER_ID)
    mock_status.assert_called_once_with("job-1", "generating", user_id=_USER_ID)
    mock_schedule.assert_called_once_with("job-1", user_id=_USER_ID)


def test_status_update_scopes_to_session_user(client):
    """POST /jobs/{id}/status updates only the authenticated user's job."""
    with (
        patch("applycling.ui.routes._current_user_id", return_value=_USER_ID),
        patch("applycling.ui.routes.jobs_service.set_job_status") as mock_status,
    ):
        response = client.post(
            "/jobs/job-1/status",
            data={"status": "reviewed"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    mock_status.assert_called_once_with("job-1", "reviewed", user_id=_USER_ID)


def test_artifact_route_scopes_job_lookup_to_session_user(client, tmp_path):
    """Artifact serving first verifies the job belongs to the current user."""
    package = tmp_path / "pkg"
    package.mkdir()
    artifact = package / "resume.pdf"
    artifact.write_bytes(b"%PDF")

    with (
        patch("applycling.ui.routes._current_user_id", return_value=_USER_ID),
        patch(
            "applycling.ui.routes.jobs_service.get_job",
            return_value={"id": "job-1", "package_folder": str(package)},
        ) as mock_get,
    ):
        response = client.get("/artifacts/job-1/resume.pdf")

    assert response.status_code == 200
    mock_get.assert_called_once_with("job-1", user_id=_USER_ID)


def test_schedule_pipeline_run_passes_user_id_to_jobs_service(client):
    """Background work must run against the same user that created the job."""
    async def _exercise() -> None:
        ui_routes.schedule_pipeline_run("job-1", user_id=_USER_ID)
        tasks = list(ui_routes._background_tasks)
        assert len(tasks) == 1
        await tasks[0]

    with patch("applycling.ui.routes.jobs_service.run_pipeline") as mock_run:
        import anyio

        anyio.run(_exercise)

    mock_run.assert_called_once_with("job-1", user_id=_USER_ID)
# ── Auth middleware ─────────────────────────────────────────────────────

def test_session_redirects_to_login_without_cookie():
    """Unauthenticated requests redirect to /login."""
    from applycling.ui import SessionMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.add_middleware(SessionMiddleware)

    @test_app.get("/")
    def _root() -> dict:
        return {"ok": True}

    tc = TestClient(test_app)
    response = tc.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert "/login" in response.headers["location"]


def test_session_allows_with_valid_cookie(monkeypatch):
    """Requests with a valid session cookie pass through."""
    monkeypatch.setenv("APPLYCLING_SESSION_SECRET", "test-secret")

    from applycling.auth import create_session_token, verify_session_token

    token = create_session_token("test-user-id")
    assert verify_session_token(token) == "test-user-id"
    assert verify_session_token("tampered.payload") is None


def test_session_rejects_tampered_cookie(monkeypatch):
    """Tampered session cookies redirect to /login."""
    monkeypatch.setenv("APPLYCLING_SESSION_SECRET", "test-secret")

    from applycling.ui import SessionMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.add_middleware(SessionMiddleware)

    @test_app.get("/")
    def _root() -> dict:
        return {"ok": True}

    tc = TestClient(test_app)
    tc.cookies["applycling_session"] = "tampered.payload"
    response = tc.get("/", follow_redirects=False)
    assert response.status_code == 303


def test_login_next_rejects_external_redirects(client):
    """Login never redirects to an attacker-controlled absolute URL."""
    with (
        patch.dict("os.environ", {"DATABASE_URL": "postgresql://test"}, clear=False),
        patch("applycling.ui.routes.PostgresStore") as mock_store,
        patch("applycling.ui.routes.verify_password", return_value=True),
    ):
        mock_store.return_value._conn.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = {
            "id": _USER_ID,
            "password_hash": "hash",
        }
        response = client.post(
            "/login?next=https://evil.example/phish",
            data={"email": "jane@example.com", "password": "secret"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_no_auth_env_bypasses_session(monkeypatch):
    """APPLYCLING_NO_AUTH=true disables session checks."""
    monkeypatch.setenv("APPLYCLING_NO_AUTH", "true")

    from applycling.ui import SessionMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.add_middleware(SessionMiddleware)

    @test_app.get("/")
    def _root() -> dict:
        return {"ok": True}

    tc = TestClient(test_app)
    response = tc.get("/")  # no cookie, no redirect
    assert response.status_code == 200
    assert response.json() == {"ok": True}
# ── Intake endpoint (multi-tenant, secret-bound) ─────────────────────────

_VALID_INTAKE_BODY = {
    "job_url": "https://example.com/jobs/software-engineer",
    "telegram_id": 123456,
    "chat_id": 789012,
}
_INTAKE_SECRET = "test-secret-123"
_USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

_VALID_FORWARD_BODY = {
    "telegram_id": 123456,
    "chat_id": 789012,
    "first_name": "Jane",
    "message_text": "https://example.com/jobs/software-engineer",
}


def _resume_text() -> str:
    return (
        "Jane Doe jane@example.com linkedin.com/in/jane "
        "Senior software engineer with experience building distributed systems. "
        "Experience at Acme building developer platforms and production APIs. "
        "Projects include queue workers, observability, and data pipelines. "
        "Skills: Python, FastAPI, Postgres, Docker, Kubernetes, cloud services. "
        "Education: BS Computer Science. "
        + ("Delivered reliable backend systems. " * 10)
    )


@pytest.fixture
def allow_forward_localhost():
    """Bypass the localhost dependency for route-level forward tests."""
    app.dependency_overrides[ui_routes._verify_localhost] = lambda: None
    yield
    app.dependency_overrides.pop(ui_routes._verify_localhost, None)


class _FakePostgresStore:
    instances: list["_FakePostgresStore"] = []

    def __init__(self, *args, **kwargs):
        self.saved: list[dict] = []
        self.profile = {"profile": {}, "resume": "Jane Doe\nEngineer"}
        self.__class__.instances.append(self)

    def save_user_profile(self, **kwargs) -> None:
        self.saved.append(kwargs)
        if "profile" in kwargs:
            self.profile["profile"] = kwargs["profile"]

    def load_user_profile(self) -> dict:
        return dict(self.profile)


@pytest.fixture
def fake_postgres_store():
    _FakePostgresStore.instances = []
    with patch("applycling.ui.routes.PostgresStore", _FakePostgresStore):
        yield _FakePostgresStore


# ── Secret-bound auth tests ──────────────────────────────────────────

def test_intake_401_unknown_secret(client):
    """POST /api/intake returns 401 when secret hash doesn't match any user."""
    with patch(
        "applycling.ui.routes._resolve_user_by_intake_secret",
        return_value=None,
    ):
        response = client.post(
            "/api/intake",
            json=_VALID_INTAKE_BODY,
            headers={"X-Intake-Secret": "unknown-secret"},
        )
    assert response.status_code == 401


def test_intake_401_missing_secret_header(client):
    """POST /api/intake returns 401 when X-Intake-Secret header is missing."""
    with patch(
        "applycling.ui.routes._resolve_user_by_intake_secret",
        return_value=None,
    ):
        response = client.post("/api/intake", json=_VALID_INTAKE_BODY)
    assert response.status_code == 401


def test_intake_403_telegram_id_mismatch(client):
    """Valid secret but body telegram_id doesn't match the bound user → 403."""
    with patch(
        "applycling.ui.routes._resolve_user_by_intake_secret",
        return_value=(_USER_ID, 999999),  # db telegram_id differs
    ):
        response = client.post(
            "/api/intake",
            json=_VALID_INTAKE_BODY,  # body has telegram_id=123456
            headers={"X-Intake-Secret": _INTAKE_SECRET},
        )
    assert response.status_code == 403


# ── Active-run guard (restored) ──────────────────────────────────────

def test_intake_409_when_active_run_exists(client):
    """POST /api/intake returns 409 when another generation is already running."""
    with (
        patch(
            "applycling.ui.routes._resolve_user_by_intake_secret",
            return_value=(_USER_ID, 123456),
        ),
        patch(
            "applycling.ui.routes.check_active_run", return_value=True
        ),
        patch("applycling.ui.routes._update_chat_id"),
    ):
        response = client.post(
            "/api/intake",
            json=_VALID_INTAKE_BODY,
            headers={"X-Intake-Secret": _INTAKE_SECRET},
        )
    assert response.status_code == 409
    assert "already running" in response.json()["error"].lower()


# ── Daily cap tests (atomic) ─────────────────────────────────────────

def test_intake_429_daily_cap_exceeded(client):
    """Second generation in the same day returns 429."""
    with (
        patch(
            "applycling.ui.routes._resolve_user_by_intake_secret",
            return_value=(_USER_ID, 123456),
        ),
        patch(
            "applycling.ui.routes.check_active_run", return_value=False,
        ),
        patch(
            "applycling.ui.routes._try_increment_daily_generation",
            return_value=False,  # cap hit
        ),
        patch("applycling.ui.routes._update_chat_id"),
    ):
        response = client.post(
            "/api/intake",
            json=_VALID_INTAKE_BODY,
            headers={"X-Intake-Secret": _INTAKE_SECRET},
        )
    assert response.status_code == 429


def test_intake_daily_cap_not_hit_first_call(client):
    """First generation passes when cap is not exceeded."""
    with (
        patch(
            "applycling.ui.routes._resolve_user_by_intake_secret",
            return_value=(_USER_ID, 123456),
        ),
        patch(
            "applycling.ui.routes.check_active_run", return_value=False,
        ),
        patch(
            "applycling.ui.routes._try_increment_daily_generation",
            return_value=True,
        ),
        patch(
            "applycling.ui.routes.PipelineContext.from_user_id",
        ) as mock_ctx,
        patch(
            "applycling.ui.routes._run_scoped_pipeline",
        ),
        patch("applycling.ui.routes._update_chat_id"),
    ):
        response = client.post(
            "/api/intake",
            json=_VALID_INTAKE_BODY,
            headers={"X-Intake-Secret": _INTAKE_SECRET},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "generating"
    mock_ctx.assert_called_once()


def test_run_scoped_pipeline_uses_notifier_and_context():
    """Telegram background runs use run_add_notify with the scoped context."""
    ctx = SimpleNamespace(
        user_id=_USER_ID,
        job_url="https://example.com/jobs/software-engineer",
        persist_job=True,
    )

    with (
        patch("applycling.ui.routes._get_chat_id_for_user", return_value=789012),
        patch("applycling.ui.routes.TelegramNotifier") as mock_notifier_cls,
        patch("applycling.ui.routes.run_add_notify") as mock_run,
    ):
        ui_routes._run_scoped_pipeline(ctx, "telegram-token")

    mock_notifier_cls.assert_called_once_with("telegram-token", "789012")
    mock_run.assert_called_once_with(
        url=ctx.job_url,
        notifier=mock_notifier_cls.return_value,
        context=ctx,
        persist_job=True,
    )


def test_run_scoped_pipeline_falls_back_to_null_notifier_without_chat_id():
    """Missing chat_id should not crash the background worker."""
    ctx = SimpleNamespace(
        user_id=_USER_ID,
        job_url="https://example.com/jobs/software-engineer",
        persist_job=True,
    )

    with (
        patch("applycling.ui.routes._get_chat_id_for_user", return_value=None),
        patch("applycling.ui.routes.TelegramNotifier") as mock_notifier_cls,
        patch("applycling.ui.routes.run_add_notify") as mock_run,
    ):
        ui_routes._run_scoped_pipeline(ctx, "telegram-token")

    mock_notifier_cls.assert_not_called()
    assert isinstance(
        mock_run.call_args.kwargs["notifier"],
        ui_routes.jobs_service._NullNotifier,
    )
    assert mock_run.call_args.kwargs["context"] is ctx


# ── Validation tests ─────────────────────────────────────────────────

def test_intake_422_on_invalid_url(client):
    """POST /api/intake returns 422 when job_url is not a valid URL."""
    with patch(
        "applycling.ui.routes._resolve_user_by_intake_secret",
        return_value=(_USER_ID, 123456),
    ):
        response = client.post(
            "/api/intake",
            json={"job_url": "not-a-url", "telegram_id": 123456},
            headers={"X-Intake-Secret": _INTAKE_SECRET},
        )
    assert response.status_code == 422


# ── Auth exemption test ──────────────────────────────────────────────

def test_intake_exempted_from_auth(client):
    """POST /api/intake succeeds without auth headers (in _UNAUTH_ROUTES)."""

    with (
        patch(
            "applycling.ui.routes._resolve_user_by_intake_secret",
            return_value=(_USER_ID, 123456),
        ),
        patch(
            "applycling.ui.routes.check_active_run", return_value=False,
        ),
        patch(
            "applycling.ui.routes._try_increment_daily_generation",
            return_value=True,
        ),
        patch("applycling.ui.routes.PipelineContext.from_user_id"),
        patch("applycling.ui.routes._run_scoped_pipeline"),
        patch("applycling.ui.routes._update_chat_id"),
    ):
        response = client.post(
            "/api/intake",
            json=_VALID_INTAKE_BODY,
            headers={"X-Intake-Secret": _INTAKE_SECRET},
        )
    assert response.status_code == 200


# ── Forward endpoint (localhost-only Hermes relay) ─────────────────────

def test_forward_rejects_non_localhost(client):
    """TestClient is not loopback by default, so /api/forward rejects it."""
    response = client.post("/api/forward", json=_VALID_FORWARD_BODY)
    assert response.status_code == 403


def test_forward_422_on_invalid_body(client, allow_forward_localhost):
    """POST /api/forward validates required Telegram metadata."""
    response = client.post(
        "/api/forward",
        json={"telegram_id": 123456, "message_text": "hello"},
    )
    assert response.status_code == 422


def test_forward_link_code_attaches_telegram_before_user_creation(
    client,
    allow_forward_localhost,
):
    """A link code connects Telegram to an existing user without duplicate creation."""
    with (
        patch(
            "applycling.ui.routes.consume_telegram_link_code",
            return_value={
                "user_id": _USER_ID,
                "telegram_id": 123456,
                "chat_id": 789012,
                "merged_source_user_id": None,
                "moved": {"jobs": 0, "pipeline_runs": 0, "artifacts": 0},
            },
        ) as mock_consume,
        patch("applycling.ui.routes.get_or_create_user_by_telegram") as mock_get,
    ):
        response = client.post(
            "/api/forward",
            json={**_VALID_FORWARD_BODY, "message_text": "link ABC12345"},
        )

    assert response.status_code == 200
    assert response.json()["actions"] == ["linked_telegram"]
    assert response.json()["user_id"] == _USER_ID
    mock_consume.assert_called_once_with(
        "ABC12345",
        telegram_id=123456,
        chat_id=789012,
        first_name="Jane",
    )
    mock_get.assert_not_called()


def test_forward_invalid_link_code_returns_bounded_error(
    client,
    allow_forward_localhost,
):
    from applycling.user_admin import TelegramLinkError

    with (
        patch(
            "applycling.ui.routes.consume_telegram_link_code",
            side_effect=TelegramLinkError("link code is invalid or expired"),
        ),
        patch("applycling.ui.routes.get_or_create_user_by_telegram") as mock_get,
    ):
        response = client.post(
            "/api/forward",
            json={**_VALID_FORWARD_BODY, "message_text": "link ABC12345"},
        )

    assert response.status_code == 409
    assert "couldn't link" in response.json()["relay_message"].lower()
    mock_get.assert_not_called()


def test_forward_new_user_resume_moves_to_confirming(
    client,
    allow_forward_localhost,
    fake_postgres_store,
):
    """A new user's non-URL message is stored as resume text."""
    resume_text = _resume_text()
    with patch(
        "applycling.ui.routes.get_or_create_user_by_telegram",
        return_value={
            "user_id": _USER_ID,
            "telegram_id": 123456,
            "chat_id": 789012,
            "onboarding_state": "new",
            "display_name": "Jane",
        },
    ):
        response = client.post(
            "/api/forward",
            json={**_VALID_FORWARD_BODY, "message_text": resume_text},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["onboarding_state"] == "confirming"
    assert payload["trigger_pipeline"] is False
    assert fake_postgres_store.instances[-1].saved[-1]["resume"] == resume_text
    assert fake_postgres_store.instances[-1].saved[-1]["onboarding_state"] == "confirming"


def test_forward_new_user_short_text_is_not_stored_as_resume(
    client,
    allow_forward_localhost,
    fake_postgres_store,
):
    """A greeting should not move a new user into confirming state."""
    with patch(
        "applycling.ui.routes.get_or_create_user_by_telegram",
        return_value={
            "user_id": _USER_ID,
            "telegram_id": 123456,
            "chat_id": 789012,
            "onboarding_state": "new",
            "display_name": "Jane",
        },
    ):
        response = client.post(
            "/api/forward",
            json={**_VALID_FORWARD_BODY, "message_text": "salam"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["onboarding_state"] == "new"
    assert payload["trigger_pipeline"] is False
    assert "resume" in payload["relay_message"].lower()
    assert fake_postgres_store.instances == []


def test_forward_new_user_url_marks_active_and_dispatches(
    client,
    allow_forward_localhost,
    fake_postgres_store,
):
    """A new user can send a URL first and skip resume onboarding."""
    with (
        patch(
            "applycling.ui.routes.get_or_create_user_by_telegram",
            return_value={
                "user_id": _USER_ID,
                "telegram_id": 123456,
                "chat_id": 789012,
                "onboarding_state": "new",
                "display_name": "Jane",
            },
        ),
        patch("applycling.ui.routes.check_active_run", return_value=False),
        patch("applycling.ui.routes._try_increment_daily_generation", return_value=True),
        patch("applycling.ui.routes.PipelineContext.from_user_id", return_value="ctx") as mock_ctx,
        patch("applycling.ui.routes._run_scoped_pipeline") as mock_run,
    ):
        response = client.post("/api/forward", json=_VALID_FORWARD_BODY)

    assert response.status_code == 200
    payload = response.json()
    assert payload["onboarding_state"] == "active"
    assert payload["trigger_pipeline"] is True
    assert fake_postgres_store.instances[-1].saved[-1]["onboarding_state"] == "active"
    mock_ctx.assert_called_once_with(_USER_ID, _VALID_FORWARD_BODY["message_text"])
    mock_run.assert_called_once()


def test_forward_confirming_approval_marks_active(
    client,
    allow_forward_localhost,
    fake_postgres_store,
):
    """Approval text activates a confirming user."""
    with patch(
        "applycling.ui.routes.get_or_create_user_by_telegram",
        return_value={
            "user_id": _USER_ID,
            "telegram_id": 123456,
            "chat_id": 789012,
            "onboarding_state": "confirming",
            "display_name": "Jane",
        },
    ):
        response = client.post(
            "/api/forward",
            json={**_VALID_FORWARD_BODY, "message_text": "looks good"},
        )

    assert response.status_code == 200
    assert response.json()["onboarding_state"] == "active"
    assert fake_postgres_store.instances[-1].saved[-1] == {"onboarding_state": "active"}


def test_forward_confirming_correction_is_preserved(
    client,
    allow_forward_localhost,
    fake_postgres_store,
):
    """Corrections are appended to profile.pending_corrections."""
    with patch(
        "applycling.ui.routes.get_or_create_user_by_telegram",
        return_value={
            "user_id": _USER_ID,
            "telegram_id": 123456,
            "chat_id": 789012,
            "onboarding_state": "confirming",
            "display_name": "Jane",
        },
    ):
        response = client.post(
            "/api/forward",
            json={**_VALID_FORWARD_BODY, "message_text": "I am in Vancouver"},
        )

    assert response.status_code == 200
    saved_profile = fake_postgres_store.instances[-1].saved[-1]["profile"]
    assert saved_profile["pending_corrections"] == ["I am in Vancouver"]


def test_forward_confirming_corrections_are_capped(
    client,
    allow_forward_localhost,
    fake_postgres_store,
):
    """Only the most recent pending corrections are retained."""
    existing = [f"old {idx}" for idx in range(10)]
    with patch(
        "applycling.ui.routes.get_or_create_user_by_telegram",
        return_value={
            "user_id": _USER_ID,
            "telegram_id": 123456,
            "chat_id": 789012,
            "onboarding_state": "confirming",
            "display_name": "Jane",
        },
    ):
        store = fake_postgres_store
        original_init = store.__init__

        def _init_with_existing(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            self.profile = {"profile": {"pending_corrections": existing}}

        with patch.object(store, "__init__", _init_with_existing):
            response = client.post(
                "/api/forward",
                json={**_VALID_FORWARD_BODY, "message_text": "new correction"},
            )

    assert response.status_code == 200
    saved_profile = fake_postgres_store.instances[-1].saved[-1]["profile"]
    assert saved_profile["pending_corrections"] == existing[1:] + ["new correction"]


def test_forward_active_user_url_enforces_active_run_guard(
    client,
    allow_forward_localhost,
):
    """Active users get a 409 before context creation when a run is active."""
    with (
        patch(
            "applycling.ui.routes.get_or_create_user_by_telegram",
            return_value={
                "user_id": _USER_ID,
                "telegram_id": 123456,
                "chat_id": 789012,
                "onboarding_state": "active",
                "display_name": "Jane",
            },
        ),
        patch("applycling.ui.routes._update_chat_id"),
        patch("applycling.ui.routes.check_active_run", return_value=True),
        patch("applycling.ui.routes.PipelineContext.from_user_id") as mock_ctx,
    ):
        response = client.post("/api/forward", json=_VALID_FORWARD_BODY)

    assert response.status_code == 409
    assert "already running" in response.json()["relay_message"].lower()
    mock_ctx.assert_not_called()


def test_forward_active_user_url_enforces_daily_cap(
    client,
    allow_forward_localhost,
):
    """Active users get a 429 after context validation but before dispatch."""
    with (
        patch(
            "applycling.ui.routes.get_or_create_user_by_telegram",
            return_value={
                "user_id": _USER_ID,
                "telegram_id": 123456,
                "chat_id": 789012,
                "onboarding_state": "active",
                "display_name": "Jane",
            },
        ),
        patch("applycling.ui.routes._update_chat_id"),
        patch("applycling.ui.routes.check_active_run", return_value=False),
        patch("applycling.ui.routes.PipelineContext.from_user_id", return_value="ctx"),
        patch("applycling.ui.routes._try_increment_daily_generation", return_value=False),
        patch("applycling.ui.routes._run_scoped_pipeline") as mock_run,
    ):
        response = client.post("/api/forward", json=_VALID_FORWARD_BODY)

    assert response.status_code == 429
    assert "daily generation limit" in response.json()["relay_message"].lower()
    mock_run.assert_not_called()


def test_forward_unknown_onboarding_state_is_safe(
    client,
    allow_forward_localhost,
):
    """Unexpected states do not fall through to active pipeline behavior."""
    with (
        patch(
            "applycling.ui.routes.get_or_create_user_by_telegram",
            return_value={
                "user_id": _USER_ID,
                "telegram_id": 123456,
                "chat_id": 789012,
                "onboarding_state": "migrating",
                "display_name": "Jane",
            },
        ),
        patch("applycling.ui.routes.PipelineContext.from_user_id") as mock_ctx,
    ):
        response = client.post("/api/forward", json=_VALID_FORWARD_BODY)

    assert response.status_code == 409
    assert response.json()["actions"] == ["restart_onboarding"]
    mock_ctx.assert_not_called()


def test_forward_soft_deleted_user_returns_bounded_error(
    client,
    allow_forward_localhost,
):
    """Soft-deleted Telegram rows do not surface raw exceptions to Hermes."""
    with patch(
        "applycling.ui.routes.get_or_create_user_by_telegram",
        side_effect=ValueError("User with telegram_id 123456 exists but is deleted"),
    ):
        response = client.post("/api/forward", json=_VALID_FORWARD_BODY)

    assert response.status_code == 409
    assert "previously removed" in response.json()["relay_message"]


# ── Web onboarding auth/token safety ───────────────────────────────────

def test_onboarding_routes_auth_exemptions() -> None:
    """Web onboarding stays behind session auth; only API relays are public-ish."""
    from applycling.ui import _UNAUTH_ROUTES

    assert "/onboarding/submit-resume" not in _UNAUTH_ROUTES
    assert "/onboarding" not in _UNAUTH_ROUTES
    assert "/onboarding/confirm" not in _UNAUTH_ROUTES


def test_onboarding_token_round_trip(monkeypatch):
    monkeypatch.setenv("APPLYCLING_ONBOARDING_TOKEN_SECRET", "test-secret")
    token = ui_routes._sign_onboarding_user_id(_USER_ID)

    assert ui_routes._verify_onboarding_token(token) == _USER_ID


def test_onboarding_token_rejects_tampering(monkeypatch):
    monkeypatch.setenv("APPLYCLING_ONBOARDING_TOKEN_SECRET", "test-secret")
    token = ui_routes._sign_onboarding_user_id(_USER_ID)

    with pytest.raises(Exception):
        ui_routes._verify_onboarding_token(token + "tampered")


def test_onboarding_token_falls_back_to_session_secret(monkeypatch):
    """New session-auth deployments do not need the removed UI password env var."""
    monkeypatch.delenv("APPLYCLING_ONBOARDING_TOKEN_SECRET", raising=False)
    monkeypatch.delenv("APPLYCLING_UI_AUTH_PASSWORD", raising=False)
    monkeypatch.delenv("APPLYCLING_INTAKE_SECRET", raising=False)
    monkeypatch.setenv("APPLYCLING_SESSION_SECRET", "session-secret")

    token = ui_routes._sign_onboarding_user_id(_USER_ID)

    assert ui_routes._verify_onboarding_token(token) == _USER_ID


def test_onboarding_confirm_rejects_missing_or_invalid_token(client, monkeypatch):
    monkeypatch.setenv("APPLYCLING_ONBOARDING_TOKEN_SECRET", "test-secret")

    response = client.get("/onboarding/confirm?token=not-valid")
    assert response.status_code == 403


def test_onboarding_post_rejects_invalid_token(client, monkeypatch):
    monkeypatch.setenv("APPLYCLING_ONBOARDING_TOKEN_SECRET", "test-secret")

    response = client.post(
        "/onboarding/confirm",
        data={"token": "not-valid", "display_name": "Jane Doe"},
    )
    assert response.status_code == 403


def test_onboarding_confirm_rejects_empty_token(client, monkeypatch):
    monkeypatch.setenv("APPLYCLING_ONBOARDING_TOKEN_SECRET", "test-secret")

    response = client.get("/onboarding/confirm")
    assert response.status_code == 403


def test_onboarding_post_rejects_empty_token(client, monkeypatch):
    monkeypatch.setenv("APPLYCLING_ONBOARDING_TOKEN_SECRET", "test-secret")

    response = client.post(
        "/onboarding/confirm",
        data={"token": "", "display_name": "Jane Doe"},
    )
    assert response.status_code == 403


def test_profile_page_prefills_current_user_profile(
    monkeypatch,
    client,
    fake_postgres_store,
):
    """Logged-in web users see the canonical resume/profile from their row."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    store_cls = fake_postgres_store
    original_init = store_cls.__init__

    def _init_with_profile(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.profile = {
            "profile": {
                "name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "555",
                "location": "Vancouver",
                "linkedin": "https://linkedin.com/in/jane",
                "portfolio": "https://jane.example.com",
            },
            "resume": "Jane resume text",
            "display_name": "Jane Doe",
        }

    with (
        patch.object(store_cls, "__init__", _init_with_profile),
        patch("applycling.ui.routes._current_user_id", return_value=_USER_ID),
    ):
        response = client.get("/profile")

    assert response.status_code == 200
    assert "Jane resume text" in response.text
    assert "jane@example.com" in response.text


def test_profile_update_saves_current_user_profile(
    monkeypatch,
    client,
    fake_postgres_store,
):
    """Profile edits update the current canonical user row."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    with patch("applycling.ui.routes._current_user_id", return_value=_USER_ID):
        response = client.post(
            "/profile",
            data={
                "display_name": "Jane Doe",
                "email": "jane@example.com",
                "phone": "555",
                "location": "Vancouver",
                "linkedin": "https://linkedin.com/in/jane",
                "portfolio": "https://jane.example.com",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    saved = fake_postgres_store.instances[-1].saved[-1]
    assert saved["display_name"] == "Jane Doe"
    assert saved["profile"]["email"] == "jane@example.com"


def test_onboarding_submit_resume_updates_current_user_from_uploaded_file(
    monkeypatch,
    client,
    fake_postgres_store,
):
    """Uploading a resume stores extracted text on the logged-in user row."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    with patch("applycling.ui.routes._current_user_id", return_value=_USER_ID):
        response = client.post(
            "/onboarding/submit-resume",
            files={
                "resume_file": (
                    "resume.txt",
                    b"Jane Doe\nExperience: Engineer",
                    "text/plain",
                )
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    saved = fake_postgres_store.instances[-1].saved[-1]
    assert saved["resume"] == "Jane Doe\nExperience: Engineer"
    assert saved["onboarding_state"] == "confirming"
