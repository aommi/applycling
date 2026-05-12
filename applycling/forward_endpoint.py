"""Pure onboarding state-machine helpers for the forwarding endpoint."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request


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
    """Allow forwarding only from the local Hermes gateway."""
    client_host = request.client.host if request.client else ""
    if client_host not in ("127.0.0.1", "::1"):
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
            f"Got it{name_part}! Reading your resume now. "
            "I'll extract what I can and show you for confirmation."
        ),
        onboarding_state="confirming",
        user_id=user_id,
    )


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
    return ForwardResponse(
        relay_message=(
            f"Got it - noted: {correction}. "
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


def handle_active_user_non_url(user_id: str = "") -> ForwardResponse:
    """Handle non-URL text from an active user."""
    return ForwardResponse(
        relay_message="Send me a job URL and I'll get to work!",
        onboarding_state="active",
        user_id=user_id,
    )
