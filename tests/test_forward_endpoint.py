"""Tests for the Hermes forwarding endpoint helpers and route behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from applycling.forward_endpoint import (
    handle_active_user_non_url,
    handle_active_user_url,
    handle_confirming_approval,
    handle_confirming_correction,
    handle_new_user_resume,
    handle_new_user_url,
    is_url_like,
    looks_like_resume_text,
)
from applycling.forward_endpoint import verify_localhost


def test_is_url_like_accepts_http_urls() -> None:
    assert is_url_like("https://jobs.example.com/123")
    assert is_url_like("  http://example.com/job/456  ")


def test_is_url_like_rejects_plain_text() -> None:
    assert not is_url_like("hello, I'm a software engineer")
    assert not is_url_like("")


def test_looks_like_resume_text_rejects_short_greetings() -> None:
    assert not looks_like_resume_text("salam")
    assert not looks_like_resume_text("hello, I am an engineer")


def test_looks_like_resume_text_accepts_resume_like_text() -> None:
    resume = (
        "Jane Doe jane@example.com linkedin.com/in/jane "
        "Senior software engineer with experience building distributed systems. "
        "Experience at Acme building developer platforms and production APIs. "
        "Projects include queue workers, observability, and data pipelines. "
        "Skills: Python, FastAPI, Postgres, Docker, Kubernetes, cloud services. "
        "Education: BS Computer Science. "
    )
    resume = resume + ("Delivered reliable backend systems. " * 10)
    assert looks_like_resume_text(resume)


def test_state_helpers_return_expected_transitions() -> None:
    resume = handle_new_user_resume("user-1", "resume", first_name="Jane")
    assert resume.onboarding_state == "confirming"
    assert resume.trigger_pipeline is False
    assert "Jane" in resume.relay_message

    skip = handle_new_user_url("user-1", "https://job.com/123", first_name="Jane")
    assert skip.onboarding_state == "active"
    assert skip.trigger_pipeline is True

    approval = handle_confirming_approval("user-1")
    assert approval.onboarding_state == "active"
    assert approval.trigger_pipeline is False

    correction = handle_confirming_correction("user-1", "I'm actually in Munich")
    assert correction.onboarding_state == "confirming"
    assert "Munich" in correction.relay_message

    active_url = handle_active_user_url("user-1", "https://job.com/456")
    assert active_url.onboarding_state == "active"
    assert active_url.trigger_pipeline is True

    active_text = handle_active_user_non_url("user-1")
    assert active_text.onboarding_state == "active"
    assert active_text.trigger_pipeline is False
    assert active_text.user_id == "user-1"


def test_verify_localhost_allows_loopback() -> None:
    request = MagicMock()
    request.client.host = "127.0.0.1"

    assert verify_localhost(request) is None


def test_verify_localhost_allows_ipv6_mapped_loopback() -> None:
    request = MagicMock()
    request.client.host = "::ffff:127.0.0.1"

    assert verify_localhost(request) is None


def test_verify_localhost_allows_configured_docker_gateway(monkeypatch) -> None:
    monkeypatch.setenv("APPLYCLING_FORWARD_ALLOWED_SOURCES", "172.30.0.1")
    request = MagicMock()
    request.client.host = "172.30.0.1"

    assert verify_localhost(request) is None


def test_verify_localhost_rejects_non_loopback() -> None:
    request = MagicMock()
    request.client.host = "192.168.1.100"

    with pytest.raises(HTTPException) as exc_info:
        verify_localhost(request)

    assert exc_info.value.status_code == 403
