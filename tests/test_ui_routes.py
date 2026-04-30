"""Tests for applycling UI routes — canonical state machine integration."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from applycling.ui import app


@pytest.fixture
def client():
    """Return a TestClient for the applycling workbench app."""
    return TestClient(app)


# ── Smoke tests ──────────────────────────────────────────────────────

def test_root_returns_200_and_contains_applycling(client):
    """GET / renders the job board with the applycling brand."""
    with patch("applycling.ui.routes.jobs_service.list_jobs", return_value=[]):
        response = client.get("/")
    assert response.status_code == 200
    assert "applycling" in response.text.lower()


def test_submit_form_returns_200(client):
    """GET /submit renders the URL submission form."""
    response = client.get("/submit")
    assert response.status_code == 200


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
# ── Auth middleware ─────────────────────────────────────────────────────


def test_auth_401_without_credentials(monkeypatch, client):
    """Workbench returns 401 when auth is configured and no credentials sent."""
    monkeypatch.setenv("APPLYCLING_UI_AUTH_USER", "admin")
    monkeypatch.setenv("APPLYCLING_UI_AUTH_PASSWORD", "secret")
    # Force middleware re-init by creating a fresh app.
    from applycling.ui import BasicAuthMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Build a test app with auth enabled.
    test_app = FastAPI()
    test_app.add_middleware(
        BasicAuthMiddleware,
    )

    @test_app.get("/")
    def _root() -> dict:
        return {"ok": True}

    tc = TestClient(test_app)
    response = tc.get("/")
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers


def test_auth_200_with_valid_credentials(monkeypatch):
    """Workbench returns 200 when valid Basic Auth credentials are sent."""
    monkeypatch.setenv("APPLYCLING_UI_AUTH_USER", "admin")
    monkeypatch.setenv("APPLYCLING_UI_AUTH_PASSWORD", "secret")

    from applycling.ui import BasicAuthMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.add_middleware(BasicAuthMiddleware)

    @test_app.get("/")
    def _root() -> dict:
        return {"ok": True}

    tc = TestClient(test_app)
    import base64

    creds = base64.b64encode(b"admin:secret").decode()
    response = tc.get("/", headers={"Authorization": f"Basic {creds}"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_healthz_exempted_from_auth(monkeypatch):
    """GET /healthz returns 200 without auth even when credentials are set."""
    monkeypatch.setenv("APPLYCLING_UI_AUTH_USER", "admin")
    monkeypatch.setenv("APPLYCLING_UI_AUTH_PASSWORD", "secret")

    from applycling.ui import BasicAuthMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.add_middleware(BasicAuthMiddleware)

    @test_app.get("/healthz")
    def _healthz() -> dict:
        return {"status": "ok"}

    tc = TestClient(test_app)
    response = tc.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_no_auth_env_bypasses_auth(monkeypatch):
    """APPLYCLING_NO_AUTH=1 disables auth even when credentials are configured."""
    monkeypatch.setenv("APPLYCLING_UI_AUTH_USER", "admin")
    monkeypatch.setenv("APPLYCLING_UI_AUTH_PASSWORD", "secret")
    monkeypatch.setenv("APPLYCLING_NO_AUTH", "1")

    from applycling.ui import BasicAuthMiddleware
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    test_app = FastAPI()
    test_app.add_middleware(BasicAuthMiddleware)

    @test_app.get("/")
    def _root() -> dict:
        return {"ok": True}

    tc = TestClient(test_app)
    # No auth header — should pass because NO_AUTH is set.
    response = tc.get("/")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
