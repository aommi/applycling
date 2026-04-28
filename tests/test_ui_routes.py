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
    # Simulate jobs_service.get_job raising TrackerError (or any Exception)
    with patch(
        "applycling.ui.routes.jobs_service.get_job",
        side_effect=Exception("Job not found"),
    ):
        response = client.get("/jobs/nonexistent")
    assert response.status_code == 404
