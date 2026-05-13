"""Pure onboarding state-machine helpers for the forwarding endpoint."""

from __future__ import annotations

from dataclasses import dataclass
import os
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request

APPROVAL_KEYWORDS = frozenset(
    {"looks good", "approved", "looks right", "done", "yes", "confirm"}
)
_DEFAULT_ALLOWED_FORWARD_SOURCES = ("127.0.0.1", "::1", "::ffff:127.0.0.0/104")
_CORRECTION_ECHO_LIMIT = 240
_MIN_RESUME_CHARS = 500
_RESUME_SIGNALS = (
    "@",
    "linkedin.com",
    "github.com",
    "experience",
    "education",
    "skills",
    "projects",
    "engineer",
    "manager",
    "developer",
)


@dataclass
class ForwardResponse:
    """Structured response for the Hermes forwarding endpoint."""

    relay_message: str
    onboarding_state: str
    user_id: str
    trigger_pipeline: bool = False
    profile_preview: dict | None = None
    actions: list[str] | None = None


def is_url_like(text: str) -> bool:
    """Return True when *text* looks like an HTTP(S) URL."""
    return text.strip().startswith(("http://", "https://"))


def verify_localhost(request: Request) -> None:
    """Allow forwarding only from loopback or explicitly trusted host sources."""
    client_host = request.client.host if request.client else ""
    try:
        host_ip = ip_address(client_host)
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")

    raw_extra = os.environ.get("APPLYCLING_FORWARD_ALLOWED_SOURCES", "")
    allowed = list(_DEFAULT_ALLOWED_FORWARD_SOURCES)
    allowed.extend(part.strip() for part in raw_extra.split(",") if part.strip())

    for entry in allowed:
        try:
            network = ip_network(entry, strict=False)
        except ValueError:
            continue
        if host_ip in network:
            return

    raise HTTPException(status_code=403, detail="Forbidden")


def handle_new_user_resume(
    user_id: str,
    resume_text: str,
    first_name: str | None = None,
) -> ForwardResponse:
    """Handle text from a new user as resume content."""
    name_part = f" {first_name}" if first_name else ""
    return ForwardResponse(
        relay_message=(
            f"Got it{name_part}! I saved your resume. "
            "Reply 'looks good' to confirm it, or send any corrections."
        ),
        onboarding_state="confirming",
        user_id=user_id,
    )


def handle_new_user_resume_rejected(user_id: str) -> ForwardResponse:
    """Ask a new user for resume content when the message is too short."""
    return ForwardResponse(
        relay_message=(
            "I need your resume before onboarding. Paste your resume text "
            "or send a job URL if you want to skip setup for now."
        ),
        onboarding_state="new",
        user_id=user_id,
    )


def looks_like_resume_text(text: str) -> bool:
    """Return whether *text* is plausible resume content, not a greeting."""
    normalized = " ".join(text.lower().split())
    if len(normalized) < _MIN_RESUME_CHARS:
        return False
    signal_count = sum(1 for signal in _RESUME_SIGNALS if signal in normalized)
    return signal_count >= 2


def handle_new_user_url(
    user_id: str,
    url: str,
    first_name: str | None = None,
) -> ForwardResponse:
    """Handle a URL from a new user by skipping onboarding."""
    name_part = f" {first_name}" if first_name else ""
    return ForwardResponse(
        relay_message=(
            f"On it{name_part}! I'll generate your package. "
            "Consider yourself onboarded - I'll remember you."
        ),
        onboarding_state="active",
        user_id=user_id,
        trigger_pipeline=True,
    )


def handle_confirming_approval(user_id: str) -> ForwardResponse:
    """Handle profile approval from a confirming user."""
    return ForwardResponse(
        relay_message=(
            "You're all set! Send me any job URL and I'll generate your package. "
            "Resume, cover letter, intro email, positioning brief, fit summary - "
            "all done for you."
        ),
        onboarding_state="active",
        user_id=user_id,
    )


def handle_confirming_correction(
    user_id: str,
    correction: str,
) -> ForwardResponse:
    """Handle a raw correction from a confirming user."""
    echo = correction.strip()
    if len(echo) > _CORRECTION_ECHO_LIMIT:
        echo = echo[:_CORRECTION_ECHO_LIMIT].rstrip() + "..."
    return ForwardResponse(
        relay_message=(
            f"Got it - noted: {echo}. "
            "I've saved that correction. Anything else to fix, or say 'looks good'?"
        ),
        onboarding_state="confirming",
        user_id=user_id,
        actions=["more_corrections", "approve"],
    )


def handle_active_user_url(
    user_id: str,
    url: str,
) -> ForwardResponse:
    """Handle a URL from an active user."""
    return ForwardResponse(
        relay_message="On it. Generating your package now.",
        onboarding_state="active",
        user_id=user_id,
        trigger_pipeline=True,
    )


def handle_active_user_non_url(user_id: str) -> ForwardResponse:
    """Handle non-URL text from an active user."""
    return ForwardResponse(
        relay_message="Send me a job URL and I'll get to work!",
        onboarding_state="active",
        user_id=user_id,
    )
